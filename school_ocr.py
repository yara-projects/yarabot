"""Optional local OCR. Tesseract is a system dependency, never a remote service."""

import csv
from io import BytesIO, StringIO
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

from PIL import Image, ImageOps, UnidentifiedImageError
from school_imports import ImportProblem


def line_centres(values, threshold):
    runs, start = [], None
    for index, value in enumerate([*values, 0]):
        if value >= threshold and start is None:
            start = index
        elif value < threshold and start is not None:
            runs.append((start + index - 1) // 2)
            start = None
    return runs


def grid_edges(image):
    """Only straight full-grid boundaries; uncertain layouts remain source text."""
    small = ImageOps.grayscale(image)
    small.thumbnail((1400, 1400))
    width, height = small.size
    pixels = small.load()
    # JPEG/thumbnail antialiasing makes thin grey rules lighter than black text.
    # A 160 threshold retains those rules without treating text as a full line.
    ys = line_centres([sum(pixels[x, y] < 160 for x in range(width)) for y in range(height)], width * .60)
    if len(ys) < 3:
        return [], []
    top, bottom = ys[0], ys[-1]
    xs = line_centres([sum(pixels[x, y] < 160 for y in range(top, bottom + 1)) for x in range(width)], (bottom - top) * .60)
    return ([round(x * image.width / width) for x in xs], [round(y * image.height / height) for y in ys]) if 3 <= len(xs) <= 51 and len(ys) <= 101 else ([], [])


def extract_image(content, language=None, deadline=None):
    if deadline is not None and deadline <= time.monotonic():
        raise ImportProblem("OCR reached its document time limit. Split the scanned PDF into smaller files. Nothing was published.")
    binary = os.getenv("TESSERACT_CMD") or shutil.which("tesseract")
    if not binary or not Path(binary).is_file():
        raise ImportProblem("Local OCR runtime is unavailable. Install Tesseract on the dashboard host, or upload a text PDF/Excel file. Nothing was published.")
    language = language or os.getenv("SCHOOL_OCR_LANGUAGES", "eng")
    if not language.replace("+", "").replace("_", "").isalnum():
        raise ImportProblem("Invalid OCR language configuration.")
    try:
        with Image.open(BytesIO(content)) as original:
            if original.width * original.height > 16000000:
                raise ImportProblem("OCR images must contain at most 16 million pixels.")
            image = ImageOps.exif_transpose(original).convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ImportProblem("This image could not be decoded safely.") from None
    with tempfile.TemporaryDirectory(prefix="yara-ocr-") as folder:
        filename = Path(folder) / "page.png"
        image.save(filename)
        try:
            timeout = min(40, max(.01, deadline - time.monotonic())) if deadline is not None else 40
            result = subprocess.run([binary, str(filename), "stdout", "-l", language, "--psm", "11", "tsv"], capture_output=True, timeout=timeout, check=True)
        except subprocess.TimeoutExpired:
            if deadline is not None and deadline <= time.monotonic():
                raise ImportProblem("OCR reached its document time limit. Split the scanned PDF into smaller files. Nothing was published.") from None
            raise ImportProblem("OCR reached its 40-second page limit. Crop or split the document.") from None
        except (OSError, subprocess.CalledProcessError):
            raise ImportProblem("Local OCR failed. Check the installed language packs and use a clearer original.") from None
    if len(result.stdout) > 4 * 1024 * 1024:
        raise ImportProblem("OCR output is too large. Split the document.")
    words = [row for row in csv.DictReader(StringIO(result.stdout.decode("utf-8", errors="replace")), delimiter="\t") if row.get("text", "").strip()]
    lines = {}
    xs, ys = grid_edges(image)
    heading_cells = {}
    if len(xs) >= 3 and len(ys) >= 3:
        # Read each small header cell independently. Whole-row OCR can merge
        # the period number with its times or with an adjacent column.
        header_deadline = min(deadline, time.monotonic() + 25) if deadline is not None else time.monotonic() + 25
        for col in range(1, len(xs) - 1):
            remaining = header_deadline - time.monotonic()
            if remaining <= 0:
                break
            header = BytesIO()
            crop = image.crop((xs[col] + 3, ys[0] + 3, xs[col + 1] - 3, ys[1] - 3))
            crop = ImageOps.autocontrast(ImageOps.grayscale(crop))
            crop.resize((crop.width * 2, crop.height * 2)).save(header, format='PNG')
            try:
                heading = subprocess.run([binary, 'stdin', 'stdout', '-l', 'eng', '--psm', '6'], input=header.getvalue(), capture_output=True, timeout=min(4, remaining), check=True)
                value = heading.stdout.decode('utf-8', errors='replace').strip()
                if value and len(value) < 300:
                    heading_cells[col] = value
            except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError):
                pass  # Keep the original reviewable header when a crop fails.
    grid = [[[] for _ in range(max(0, len(xs) - 1))] for _ in range(max(0, len(ys) - 1))]
    for word in words:
        text = word["text"].strip()
        key = tuple(word.get(key, "") for key in ("block_num", "par_num", "line_num"))
        lines.setdefault(key, []).append(text)
        x, y = int(word["left"]) + int(word["width"]) / 2, int(word["top"]) + int(word["height"]) / 2
        col = next((i for i in range(len(xs) - 1) if xs[i] <= x < xs[i + 1]), None)
        row = next((i for i in range(len(ys) - 1) if ys[i] <= y < ys[i + 1]), None)
        if row is not None and col is not None:
            grid[row][col].append((int(word["top"]), int(word["left"]), text))
    table = [[" ".join(word[2] for word in sorted(cell)) for cell in row] for row in grid]
    if table:
        for col, value in heading_cells.items():
            table[0][col] = value
    return dict(text="\n".join(" ".join(line) for line in lines.values()), tables=[table] if table else [],
                warnings=["OCR is a draft, not verified school data. Review every cell; small text, merged cells, Arabic, alternatives and teacher names may be wrong. Unknown codes are preserved."])
