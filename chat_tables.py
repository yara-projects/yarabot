"""Presentation only: callers must resolve scope and authorise data first."""

from collections import defaultdict
from html import escape
import re


DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


def cell(value):
    text = escape(str(value if value is not None else "—"), quote=False)
    text = re.sub(r"([\\`*_[\]])", r"\\\1", text)
    return text.replace("|", "\\|").replace("\r", "").replace("\n", "<br>")


def data_table(headers, rows):
    lines = ["| " + " | ".join(cell(header) for header in headers) + " |",
             "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(cell(value) for value in row) + " |" for row in rows)
    return "\n".join(lines)


def timetable_grid(rows, teacher=False):
    """Day/period grid. Repeated entries are alternatives, never overwritten."""
    grouped = defaultdict(list)
    periods, days = set(), set()
    for row in rows:
        day, period, label = row[:3]
        day = str(day).capitalize()
        periods.add(int(period)); days.add(day)
        if label not in grouped[(day, int(period))]:
            grouped[(day, int(period))].append(label)
    periods = sorted(periods)
    days = sorted(days, key=lambda day: (DAYS.index(day) if day in DAYS else 7, day))
    output = []
    for day in days:
        values = []
        for period in periods:
            labels = grouped.get((day, period), [])
            values.append(" / ".join(str(label) for label in labels) if labels else "—")
        output.append([day, *values])
    table = data_table(["Day", *[f"Period {period}" for period in periods]], output)
    note = "Cells show class/division." if teacher else "Cells show subjects; alternatives in the same period are separated by / ."
    result = table + "\n\n" + note + " — means no entry was returned; it is not confirmation of a free period. Times and breaks are shown only when recorded."
    # Preserve existing staff information without cluttering the basic grid.
    if not teacher:
        staff = list(dict.fromkeys((str(row[2]), str(row[3])) for row in rows if len(row) > 3 and row[3]))
        if staff:
            result += '\n\n<details><summary>Subject teachers</summary><ul>'
            result += ''.join(f'<li>{escape(subject)} — {escape(name)}</li>' for subject, name in staff)
            result += '</ul></details>'
    return result
