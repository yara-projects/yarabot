"""Local-only import checks; generated content is synthetic."""

from io import BytesIO
import unittest
import zipfile

from school_imports import make_draft, syllabus_rows, timetable_rows, ImportProblem, clean
import test_admin_api as admin_tests


class SchoolImportTests(unittest.TestCase):
    def test_csv_headers_and_period_zero(self):
        draft = make_draft("timetable", "weekly.csv", b"Day,Period,Subject,Teacher,Class\nSUN,0,ACC,Example Teacher,12-F\nMON,1,B.S,Example Teacher,12-F\n")
        self.assertEqual(draft["rows"][0]["period"], "0")
        self.assertEqual(draft["rows"][0]["activity"], "Accountancy")
        self.assertEqual(draft["rows"][1]["activity"], "Business Studies")
        self.assertEqual(clean(0), "0")

    def test_weekly_grid_preserves_combined_options(self):
        rows, warnings = timetable_rows([[['Day', '0 7:00 - 7:10', '1 7:10 - 7:50'],
                                          ['SUN', 'Class teacher', 'COM / PE / MATH-PCMB'],
                                          ['MON', 'Class teacher', 'ACC']]])
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[1]["activity"], 'COM / PE / MATH-PCMB')
        self.assertEqual(rows[0]["period"], '0')
        self.assertTrue(warnings)

    def test_syllabus_continuation_retains_subject_and_book(self):
        rows = syllabus_rows([[['SUBJECT', 'PORTION'], ['Economics', 'Indian Economic Development\nChapter 4: Human Capital Format']],
                              [['', 'Chapter 5: Rural Development'], ['Computer Science', 'Chapter 8: Data Concepts\nChapter 9: Structured Query Language']]])
        self.assertEqual(rows[1], dict(subject='Economics', section='Indian Economic Development', chapter='5', topic='Rural Development'))
        self.assertEqual(rows[2]['subject'], 'Computer Science')
        self.assertEqual(rows[2]['section'], '')

    def test_wrapped_chapter_titles_join_without_extra_rows(self):
        rows = syllabus_rows([[['Fine Arts', 'Chapter 7: Modern Art and\ncontemporary artists\nChapter 8: Graphic prints']]])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['topic'], 'Modern Art and contemporary artists')

    def test_unsupported_and_fake_pdf_fail_visibly(self):
        for name, content in [('fake.pdf', b'not a pdf'), ('image.jpg', b'example'), ('macro.xlsm', b'example'), ('empty.csv', b'')]:
            with self.assertRaises(ImportProblem):
                make_draft('timetable', name, content)

    def test_excel_reads_saved_cells_without_running_formulas(self):
        from openpyxl import Workbook
        book = Workbook()
        book.active.append(['Day', 'Period', 'Subject'])
        book.active.append(['Sunday', 0, 'ACC'])
        stream = BytesIO(); book.save(stream); book.close()
        draft = make_draft('timetable', 'example.xlsx', stream.getvalue())
        self.assertEqual(draft['rows'][0]['period'], '0')
        self.assertTrue(draft['warnings'])

    def test_docx_table_and_no_html_execution(self):
        stream = BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            archive.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:tbl><w:tr><w:tc><w:p><w:r><w:t>Subject</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Portion</w:t></w:r></w:p></w:tc></w:tr><w:tr><w:tc><w:p><w:r><w:t>English</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Report Writing</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>')
        draft = make_draft('syllabus', 'example.docx', stream.getvalue())
        self.assertEqual(draft['rows'][0]['topic'], 'Report Writing')


class ImportEndpointTests(unittest.TestCase):
    setUp = admin_tests.AdminApiTests.setUp
    post = admin_tests.AdminApiTests.post
    login = admin_tests.AdminApiTests.login
    def test_preview_needs_admin_and_csrf(self):
        response = self.client.post('/api/imports/preview', data={'kind': 'timetable', 'file': (BytesIO(b'Day,Period,Subject\nSUN,0,ACC'), 'example.csv')},
                                    headers={'X-CSRF-Token': self.csrf})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.repo.writes, 0)

    def test_preview_never_writes_records(self):
        self.login()
        response = self.client.post('/api/imports/preview', data={'kind': 'timetable', 'file': (BytesIO(b'Day,Period,Subject\nSUN,0,ACC'), 'example.csv')},
                                    headers={'X-CSRF-Token': self.csrf})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['rows'][0]['activity'], 'Accountancy')
        self.assertEqual(self.repo.writes, 0)


if __name__ == '__main__':
    unittest.main()
