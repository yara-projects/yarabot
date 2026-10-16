"""Synthetic DB-backed admin workflows, including transactional record imports."""

from contextlib import contextmanager
from io import BytesIO
import sqlite3
import unittest
from unittest.mock import patch

from admin_app import create_app, MySQLRepository, AdminError, phrase_safety
from auth_helpers import hash_password
from record_imports import make_record_draft
from test_school_documents import LocalStore


class Repository(MySQLRepository):
    def __init__(self, store):
        self.store = store

    @contextmanager
    def connection(self):
        with self.store.connection() as conn:
            yield conn

    def almanac(self):
        row = self.store.db.execute('SELECT content,version FROM school_almanac WHERE id=1').fetchone()
        return dict(content=row[0], version=row[1])

    def save_almanac(self, content, version):
        result = self.store.db.execute('UPDATE school_almanac SET content=?,version=version+1 WHERE id=1 AND version=?', (content, version))
        self.store.db.commit()
        return result.rowcount == 1


class WorkflowTests(unittest.TestCase):
    def fixture_phrases(self):
        grouped = {}
        for intent, phrase in self.store.db.execute('SELECT intent_name,phrase FROM intent_phrases'):
            grouped.setdefault(intent, []).append(phrase)
        return grouped

    def setUp(self):
        self.store = LocalStore()
        self.addCleanup(self.store.db.close)
        self.store.db.executescript('''
          CREATE TABLE students(student_id INTEGER PRIMARY KEY, name TEXT,class TEXT,roll_no INTEGER,dob TEXT,parent_name TEXT,parent_contact TEXT,fees_status TEXT,attendance_pct REAL,UNIQUE(class,roll_no));
          INSERT INTO students VALUES(1,'Example Student','12-F',1,NULL,'Example Parent','123456789','paid',90);
          CREATE TABLE parents(parent_id INTEGER PRIMARY KEY,name TEXT,contact TEXT);
          INSERT INTO parents VALUES(1,'Example Parent','123456789');
          CREATE TABLE parent_student_links(parent_id INTEGER,student_id INTEGER,PRIMARY KEY(parent_id,student_id),FOREIGN KEY(student_id) REFERENCES students(student_id));
          CREATE TABLE teachers(teacher_id INTEGER PRIMARY KEY,name TEXT,contact TEXT,classes_assigned TEXT,department_id INTEGER);
          INSERT INTO teachers VALUES(7,'Example Teacher','','12-F',NULL);
          CREATE TABLE subjects(subject_id INTEGER PRIMARY KEY,subject_name TEXT,class TEXT);
          INSERT INTO subjects VALUES(8,'Accountancy','12-F');
          CREATE TABLE teacher_subjects(teacher_id INTEGER,subject_id INTEGER,PRIMARY KEY(teacher_id,subject_id));
          CREATE TABLE users(user_id INTEGER PRIMARY KEY,username TEXT UNIQUE,password_hash TEXT,role TEXT,linked_id INTEGER);
          CREATE TABLE intent_phrases(id INTEGER PRIMARY KEY,intent_name TEXT,phrase TEXT,source TEXT,added_by TEXT);
          CREATE TABLE learned_phrases(id INTEGER PRIMARY KEY,phrase_text TEXT,resolved_intent TEXT,role TEXT,ask_count INTEGER,applied INTEGER);
          INSERT INTO learned_phrases VALUES(1,'synthetic safe phrase','timetable','student',1,0);
          CREATE TABLE departments(department_id INTEGER PRIMARY KEY,name TEXT,hod_teacher_id INTEGER);
          INSERT INTO departments VALUES(1,'Example Department',7);
          CREATE TABLE class_teachers(class TEXT PRIMARY KEY,teacher_id INTEGER);
          CREATE TABLE class_sections(class TEXT PRIMARY KEY,school_section TEXT);
          CREATE TABLE timetable(entry_id INTEGER PRIMARY KEY,class TEXT,day TEXT,period_no INTEGER,subject_id INTEGER,teacher_id INTEGER);
          CREATE TABLE exams(exam_id INTEGER PRIMARY KEY,class TEXT,subject_id INTEGER,exam_date TEXT,exam_type TEXT);
          CREATE TABLE notices(notice_id INTEGER PRIMARY KEY,title TEXT,body TEXT,date_posted TEXT,target_roles TEXT,priority TEXT);
          CREATE TABLE unanswered_questions(id INTEGER PRIMARY KEY,question_text TEXT,ask_count INTEGER,last_asked TEXT);
          INSERT INTO unanswered_questions VALUES(1,'Synthetic school question',1,'2026-10-15');
          CREATE TABLE school_almanac(id INTEGER PRIMARY KEY,content TEXT,version INTEGER);
          INSERT INTO school_almanac VALUES(1,'Existing verified information',3);
          CREATE TABLE system_settings(`key` TEXT PRIMARY KEY,value TEXT);
          INSERT INTO system_settings VALUES('chatbot_enabled','true');
          CREATE TABLE system_logs(log_id INTEGER PRIMARY KEY,action TEXT,performed_by INTEGER,timestamp TEXT DEFAULT CURRENT_TIMESTAMP);
        ''')
        self.repo = Repository(self.store)
        phrases = patch('nlp_helpers._fetch_phrases_from_db', side_effect=self.fixture_phrases)
        phrases.start()
        self.addCleanup(phrases.stop)
        self.store.record_publisher = self.repo.apply_import
        self.app = create_app(dict(TESTING=True, SECRET_KEY='synthetic-workflow-not-production-secret-1234',
                                   ADMIN_USERNAME='test-admin', ADMIN_PASSWORD_HASH=hash_password('synthetic-password')), self.repo, self.store)
        self.client = self.app.test_client()
        self.csrf = self.client.get('/api/session').json['csrf']
        response = self.send('/api/login', dict(username='test-admin', password='synthetic-password'))
        self.csrf = response.json['csrf']

    def send(self, path, payload, method='POST'):
        return self.client.open(path, method=method, json=payload, headers={'X-CSRF-Token': self.csrf})

    def test_parent_links_require_exact_ids_confirmation_and_revision(self):
        path = '/api/relations/parent-children/1'
        snapshot = self.client.get(path).json
        self.assertEqual(snapshot['members'], [])
        payload = dict(ids=[1], revision=snapshot['revision'], confirmed=True)
        result = self.send(path, payload, 'PUT')
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json['members'][0]['label'], 'Example Student')
        self.assertEqual(self.send(path, payload, 'PUT').status_code, 409)
        payload.update(revision=result.json['revision'], ids=[999])
        self.assertEqual(self.send(path, payload, 'PUT').status_code, 400)
        self.assertEqual(len(self.client.get(path).json['members']), 1)

    def test_preview_almanac_never_uses_global_database_helpers(self):
        with patch('almanac_store.read_almanac', side_effect=AssertionError('Must remain isolated')), patch('almanac_store.save_almanac', side_effect=AssertionError('Must remain isolated')):
            snapshot = self.client.get('/api/almanac').json
            self.assertEqual(snapshot['version'], 3)
            result = self.send('/api/almanac', dict(content='Synthetic updated content', version=3), 'PUT')
            self.assertEqual(result.status_code, 200)
            self.assertEqual(self.repo.almanac(), dict(content='Synthetic updated content', version=4))

    def test_preview_manual_phrase_safety_never_connects_to_school_storage(self):
        with patch('mysql.connector.connect', side_effect=AssertionError('No school DB in preview')):
            result = self.send('/api/phrases/manual/check', dict(phrase='hi', intent='attendance'))
        self.assertEqual(result.status_code, 200)
        self.assertIn(result.json['status'], {'safe', 'needs_review'})
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM intent_phrases').fetchone()[0], 0)

    def test_teacher_subject_links_and_unknown_types(self):
        path = '/api/relations/teacher-subjects/7'
        snapshot = self.client.get(path).json
        result = self.send(path, dict(ids=[8], revision=snapshot['revision'], confirmed=True), 'PUT')
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json['members'][0]['label'], 'Accountancy')
        self.assertEqual(self.client.get('/api/relations/injected/7').status_code, 404)

    def test_account_creation_reset_never_returns_hash_and_links_are_checked(self):
        record = dict(username='example_user', role='student', linked_id='1')
        self.assertEqual(self.send('/api/records/accounts', dict(record=record)).status_code, 400)
        result = self.send('/api/records/accounts', dict(record=record, new_password='synthetic-secure-password'))
        self.assertEqual(result.status_code, 201)
        listing = self.client.get('/api/records/accounts').json
        self.assertNotIn('password', str(listing))
        row = listing['rows'][0]
        record['linked_id'] = '999'
        self.assertEqual(self.send('/api/records/accounts/1', dict(record=record, revision=row['_revision']), 'PUT').status_code, 400)
        record['linked_id'] = '1'
        self.assertEqual(self.send('/api/records/accounts/1', dict(record=record, revision=row['_revision'], new_password='new-synthetic-password'), 'PUT').status_code, 200)
        self.assertEqual(self.send('/api/records/accounts/1', dict(record=record, revision=row['_revision']), 'PUT').status_code, 409)

    def test_record_batch_preview_save_approve_publish_atomic_and_stale(self):
        csv = b'Student ID,Student name,Class,Roll number,Parent name,Parent contact,Fee status,Attendance percentage\n1,Example Student,12-F,1,Example Parent,123456789,paid,95\n'
        preview = self.client.post('/api/imports/preview', data=dict(kind='records/students', file=(BytesIO(csv), 'synthetic.csv')), headers={'X-CSRF-Token': self.csrf})
        self.assertEqual(preview.status_code, 200, preview.json)
        document = {key: preview.json[key] for key in ['kind', 'filename', 'source_text', 'rows']}
        document['scope'] = {}
        saved = self.send('/api/imports', dict(document=document))
        self.assertEqual(saved.status_code, 200, saved.json)
        item = saved.json
        self.assertEqual(self.store.db.execute('SELECT attendance_pct FROM students').fetchone()[0], 90)
        item = self.send(f'/api/imports/{item["document_id"]}/approve', dict(revision=item['revision'], confirmed=True)).json
        result = self.send(f'/api/imports/{item["document_id"]}/publish', dict(revision=item['revision'], publication_version=item['publication_version'], confirmed=True))
        self.assertEqual(result.status_code, 200, result.json)
        self.assertEqual(self.store.db.execute('SELECT attendance_pct FROM students').fetchone()[0], 95)
        self.assertEqual(self.send(f'/api/imports/{item["document_id"]}/publish', dict(revision=item['revision'], publication_version=item['publication_version'], confirmed=True)).status_code, 409)

    def test_record_batch_failure_rolls_back_all_prior_rows(self):
        draft = make_record_draft('records/students', 'example.csv', b'ID,Student name,Class,Roll number,Fee status,Attendance percentage\n1,Example Student,12-F,1,paid,91\n,Another Student,12-F,1,paid,90\n')
        draft['rows'] = self.repo.prepare_import('students', draft['rows'])
        document = {key: draft[key] for key in ['kind', 'filename', 'source_text', 'rows']}
        document['scope'] = {}
        item = self.store.save(document, 'Admin')
        item = self.store.transition(item['document_id'], 'approve', item['revision'], None, 'Admin')
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.transition(item['document_id'], 'publish', item['revision'], item['publication_version'], 'Admin')
        self.assertEqual(self.store.db.execute('SELECT attendance_pct FROM students').fetchone()[0], 90)
        self.assertEqual(self.store.get(item['document_id'])['status'], 'approved')

    def test_phrase_rechecks_safety_and_preserves_unsafe_candidate(self):
        row = self.client.get('/api/records/phrases').json['rows'][0]
        payload = dict(revision=row['_revision'], confirmed=True)
        with patch('nlp_helpers.refresh_phrase_cache'), patch('admin_app.phrase_safety', return_value=('needs_review', 'Synthetic collision')):
            self.assertEqual(self.send('/api/phrases/1/approve', payload).status_code, 409)
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM intent_phrases').fetchone()[0], 0)
        with patch('nlp_helpers.refresh_phrase_cache'), patch('admin_app.phrase_safety', return_value=('safe', '')):
            self.assertEqual(self.send('/api/phrases/1/approve', payload).status_code, 200)
            self.assertEqual(self.send('/api/phrases/1/approve', payload).status_code, 409)
        self.assertEqual(self.store.db.execute('SELECT applied FROM learned_phrases').fetchone()[0], 1)

    def test_core_greeting_phrase_cannot_be_promoted(self):
        with self.assertRaises(AdminError):
            phrase_safety('hello synthetic', 'greeting')

    def test_manual_phrase_confirmation_safety_and_deduplication(self):
        payload = dict(phrase=' Synthetic phrase ', intent='timetable')
        self.assertEqual(self.send('/api/phrases/manual/approve', payload).status_code, 400)
        with patch('nlp_helpers.refresh_phrase_cache'), patch('admin_app.phrase_safety', return_value=('needs_review', 'Synthetic conflict')):
            self.assertEqual(self.send('/api/phrases/manual/check', payload).json['status'], 'needs_review')
            self.assertEqual(self.send('/api/phrases/manual/approve', dict(payload, confirmed=True)).status_code, 409)
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM intent_phrases').fetchone()[0], 0)
        with patch('nlp_helpers.refresh_phrase_cache'), patch('admin_app.phrase_safety', return_value=('safe', '')):
            for _ in range(2):
                self.assertEqual(self.send('/api/phrases/manual/approve', dict(payload, confirmed=True)).status_code, 200)
        rows = self.store.db.execute('SELECT phrase,source FROM intent_phrases').fetchall()
        self.assertEqual([tuple(row) for row in rows], [('synthetic phrase', 'manual')])

    def test_suggestion_append_is_confirmed_versioned_and_not_repeatable(self):
        row = self.client.get('/api/records/suggestions').json['rows'][0]
        payload = dict(revision=row['_revision'], topic='Synthetic topic', answer='Verified synthetic answer')
        self.assertEqual(self.send('/api/suggestions/1/append', payload).status_code, 400)
        payload['confirmed'] = True
        self.assertEqual(self.send('/api/suggestions/1/append', dict(payload, topic='bad\ntopic')).status_code, 400)
        self.assertEqual(self.send('/api/suggestions/1/append', payload).status_code, 200)
        almanac = self.store.db.execute('SELECT content,version FROM school_almanac').fetchone()
        self.assertEqual(almanac[1], 4)
        self.assertIn('Existing verified information\n\nSynthetic topic\nVerified synthetic answer\n', almanac[0])
        self.assertEqual(self.send('/api/suggestions/1/append', payload).status_code, 409)

    def test_suggestion_conflict_and_missing_almanac_preserve_queue(self):
        row = self.client.get('/api/records/suggestions').json['rows'][0]
        payload = dict(revision='stale', confirmed=True)
        self.assertEqual(self.send('/api/suggestions/1/dismiss', payload).status_code, 409)
        payload.update(revision=row['_revision'], topic='Synthetic', answer='Verified')
        self.store.db.execute('DELETE FROM school_almanac')
        self.store.db.commit()
        self.assertEqual(self.send('/api/suggestions/1/append', payload).status_code, 409)
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM unanswered_questions').fetchone()[0], 1)
        self.assertEqual(self.send('/api/suggestions/1/dismiss', payload).status_code, 200)

    def test_document_endpoints_fail_closed_after_logout(self):
        self.send('/api/logout', {})
        for path in ['/api/imports', '/api/imports/example', '/api/relations/parent-children/1', '/api/system', '/api/phrase-intents']:
            self.assertEqual(self.client.get(path).status_code, 401)


if __name__ == '__main__':
    unittest.main()
