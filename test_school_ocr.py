"""Bounded OCR adapter and grid tests. No network/native OCR needed for this unit suite."""
from io import BytesIO
from types import SimpleNamespace
import subprocess
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw
from school_imports import ImportProblem
from school_ocr import grid_edges, line_centres, extract_image


class OCRTests(unittest.TestCase):
    def image(self):
        image = Image.new('RGB', (600, 400), 'white')
        draw = ImageDraw.Draw(image)
        for x in [20, 130, 340, 580]:
            draw.line((x, 40, x, 380), fill=(140, 140, 140), width=1)
        for y in [40, 100, 240, 380]:
            draw.line((20, y, 580, y), fill=(140, 140, 140), width=1)
        draw.text((30, 20), 'Synthetic only', fill='black')
        return image

    def content(self):
        output = BytesIO(); self.image().save(output, 'PNG'); return output.getvalue()

    def test_grey_rules_are_not_lost_and_text_is_not_a_rule(self):
        xs, ys = grid_edges(self.image())
        self.assertEqual(xs, [20, 130, 340, 580])
        self.assertEqual(ys, [40, 100, 240, 380])
        self.assertEqual(line_centres([0, 8, 9, 0, 7, 0], 7), [1, 4])

    def test_missing_runtime_is_explicit_not_fake_extraction(self):
        with patch('school_ocr.shutil.which', return_value=None), patch.dict('os.environ', {}, clear=True):
            with self.assertRaisesRegex(ImportProblem, 'runtime is unavailable'):
                extract_image(self.content())

    def test_timeout_is_bounded_and_does_not_publish(self):
        with patch('school_ocr.shutil.which', return_value=__file__), patch('school_ocr.subprocess.run', side_effect=subprocess.TimeoutExpired('tesseract', 40)):
            with self.assertRaisesRegex(ImportProblem, '40-second'):
                extract_image(self.content())

    def test_expired_document_budget_does_not_start_another_page(self):
        with patch('school_ocr.subprocess.run') as runner:
            with self.assertRaisesRegex(ImportProblem, 'document time limit'):
                extract_image(self.content(), deadline=0)
            runner.assert_not_called()

    def test_words_are_assigned_to_detected_cells_not_adjacent_days(self):
        tsv = 'level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n'
        tsv += '5\t1\t1\t1\t1\t1\t30\t130\t50\t20\t90\tSUN\n'
        tsv += '5\t1\t2\t1\t1\t1\t150\t130\t50\t20\t90\tACC\n'
        tsv += '5\t1\t3\t1\t1\t1\t30\t260\t50\t20\t90\tMON\n'
        with patch('school_ocr.shutil.which', return_value=__file__), patch('school_ocr.subprocess.run', side_effect=[SimpleNamespace(stdout=tsv.encode()), SimpleNamespace(stdout=b''), SimpleNamespace(stdout=b'')]) as runner:
            result = extract_image(self.content(), language='eng')
        self.assertEqual(result['tables'][0][1][:2], ['SUN', 'ACC'])
        self.assertEqual(result['tables'][0][2][0], 'MON')
        self.assertEqual(runner.call_args_list[0].kwargs['timeout'], 40)
        self.assertTrue(all(not call.kwargs.get('shell', False) for call in runner.call_args_list))


if __name__ == '__main__':
    unittest.main()
