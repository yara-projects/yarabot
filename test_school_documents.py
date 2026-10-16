"""Synthetic transactions and conversation tests. Never connects to the school DB."""

from contextlib import contextmanager
from copy import deepcopy
import sqlite3
import unittest
from unittest.mock import patch

from school_documents import DocumentStore, DocumentError, checked_document
from document_chat import respond, visible
from chat_choices import consume, offer


def sample(kind='syllabus', grade='12', division='F', term='Term 2'):
    return dict(kind=kind, filename='Synthetic school document', source_text='Fixture only',
                scope=dict(year='2026-27', grade=grade, division=division, stream='Commerce', assessment=term,
                           audience='signed_in', teacher_id='7' if kind == 'teacher_timetable' else '',
                           effective_from='2020-01-01', effective_to='2099-12-31'),
                rows=[dict(subject='Accountancy', section='Book 1', chapter='4', topic='Synthetic chapter')]
                if kind == 'syllabus' else [dict(day='Sunday', period='0', start='07:00', end='07:10', activity='COM / PE / Mathematics', teacher='Example Teacher', **{'class': '12-F'})])


class Cursor:
    def __init__(self, conn):
        self.cursor = conn.cursor()

    def execute(self, sql, params=()):
        sql = sql.replace('JSON_UNQUOTE(JSON_EXTRACT', '(JSON_EXTRACT').replace(' FOR UPDATE', '').replace('INSERT IGNORE', 'INSERT OR IGNORE').replace('%s', '?')
        return self.cursor.execute(sql, params)

    def fetchone(self):
        row = self.cursor.fetchone()
        return dict(row) if row else None

    def fetchall(self):
        return [dict(row) for row in self.cursor.fetchall()]

    def close(self):
        self.cursor.close()


class Connection:
    def __init__(self, connection):
        self.connection = connection

    def cursor(self, **kwargs):
        return Cursor(self.connection)

    def commit(self):
        self.connection.commit()


class LocalStore(DocumentStore):
    def __init__(self):
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''PRAGMA foreign_keys=ON;
          CREATE TABLE school_documents(document_id TEXT PRIMARY KEY,scope_key TEXT,filename TEXT,payload TEXT,status TEXT DEFAULT 'draft',revision INTEGER DEFAULT 1,updated_by TEXT,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
          CREATE TABLE school_document_heads(scope_key TEXT PRIMARY KEY,document_id TEXT REFERENCES school_documents(document_id),version INTEGER DEFAULT 0);
        ''')

    @contextmanager
    def connection(self):
        try:
            yield Connection(self.db)
        except Exception:
            self.db.rollback()
            raise


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.store = LocalStore()
        self.addCleanup(self.store.db.close)

    def approve(self, item):
        return self.store.transition(item['document_id'], 'approve', item['revision'], None, 'Admin')

    def publish(self, item):
        return self.store.transition(item['document_id'], 'publish', item['revision'], item['publication_version'], 'Admin')

    def test_explicit_lifecycle_and_withdrawal(self):
        item = self.store.save(sample(), 'Admin')
        self.assertEqual(self.store.published('syllabus'), [])
        with self.assertRaises(DocumentError):
            self.publish(item)
        item = self.approve(item)
        self.assertEqual(self.store.published('syllabus'), [])
        item = self.publish(item)
        self.assertEqual(len(self.store.published('syllabus')), 1)
        with self.assertRaises(DocumentError):
            self.store.save(sample(), 'Admin', item['document_id'], item['revision'])
        self.store.transition(item['document_id'], 'withdraw', item['revision'], item['publication_version'], 'Admin')
        self.assertEqual(self.store.published('syllabus'), [])
        self.assertEqual(len(self.store.list()), 1)

    def test_stale_revision_rollback_and_approval_revoked_by_edit(self):
        item = self.store.save(sample(), 'Admin')
        approved = self.approve(item)
        with self.assertRaises(DocumentError):
            self.store.save(sample(), 'Admin', item['document_id'], item['revision'])
        edited = self.store.save(sample(), 'Admin', approved['document_id'], approved['revision'])
        self.assertEqual(edited['status'], 'draft')
        with self.assertRaises(DocumentError):
            self.publish(edited)

    def test_two_replacements_cannot_silently_overwrite_publication(self):
        first = self.approve(self.store.save(sample(), 'Admin'))
        second = self.approve(self.store.save(sample(), 'Admin'))
        self.publish(first)
        with self.assertRaises(DocumentError):
            self.publish(second)
        refreshed = self.store.get(second['document_id'])
        self.publish(refreshed)
        self.assertEqual(self.store.get(first['document_id'])['status'], 'superseded')
        self.assertEqual(len(self.store.published('syllabus')), 1)

    def test_scope_is_distinct_and_expiry_is_not_inferred(self):
        for term in ['Term 1', 'Term 2', 'Whole year']:
            self.publish(self.approve(self.store.save(sample(term=term), 'Admin')))
        self.assertEqual(len(self.store.published('syllabus')), 3)
        self.assertEqual(self.store.published('syllabus', '2100-01-01'), [])

    def test_incomplete_scope_and_times_cannot_be_approved(self):
        for field in ['year', 'grade', 'assessment', 'effective_from']:
            document = sample(); document['scope'][field] = ''
            checked_document(document)  # Drafts may be incomplete.
            with self.assertRaises(DocumentError):
                checked_document(document, approving=True)
        document = sample('timetable'); document['rows'][0]['end'] = '1:00 PM'
        with self.assertRaises(DocumentError):
            checked_document(document, approving=True)
        document['rows'][0]['end'] = '13:00'
        self.assertEqual(checked_document(document, approving=True)['rows'][0]['period'], '0')

    def test_validity_dates_require_canonical_iso_for_ordered_retrieval(self):
        for value in ['20260101', '2026-W01-1', '2026-02-30']:
            document = sample(); document['scope']['effective_from'] = value
            with self.assertRaises(DocumentError):
                checked_document(document, approving=True)


class DocumentChatTests(unittest.TestCase):
    def setUp(self):
        self.store = LocalStore()
        self.addCleanup(self.store.db.close)
        self.state = {}
        self.owner = (1, 'student', 2)
        self.identity = dict(role='student', classes=['12-F'], teacher_id=None)

    def publish(self, payload):
        item = self.store.save(payload, 'Admin')
        item = self.store.transition(item['document_id'], 'approve', item['revision'], None, 'Admin')
        return self.store.transition(item['document_id'], 'publish', item['revision'], item['publication_version'], 'Admin')

    def ask(self, question, selection=None):
        return respond(question, self.state, self.owner, lambda: self.identity, self.store, selection)

    def test_vague_questions_offer_only_uploaded_authorised_choices(self):
        self.publish(sample())
        self.publish(sample(grade='11', division='A', term='UT 1'))
        self.store.save(sample(term='Term 1'), 'Admin')  # Unapproved: never an option.
        reply = self.ask('what is the syllabus')
        self.assertEqual(len(reply['choices']), 1)
        self.assertNotIn('UT 1', str(reply))
        choice = consume(self.state, reply['choices'][0]['token'], self.owner)
        result = self.ask('selected document', choice)
        self.assertIn('Synthetic chapter', result['reply'])
        self.assertIn('| Subject |', result['reply'])

    def test_selected_term_is_retained_for_followup_subject(self):
        for term in ['Term 1', 'Term 2']:
            document = sample(term=term)
            document['rows'].append(dict(subject='Psychology', section='', chapter='1', topic='Topic for ' + term))
            self.publish(document)
        reply = self.ask('syllabus')
        choice = next(option for option in reply['choices'] if 'Term 2' in option['label'])
        self.ask('selected document', consume(self.state, choice['token'], self.owner))
        result = self.ask('Psychology')
        self.assertIn('Topic for Term 2', result['reply'])
        self.assertNotIn('choices', result)
        self.assertNotIn('Topic for Term 1', result['reply'])

    def test_explicit_missing_term_is_not_replaced_with_available_term(self):
        self.publish(sample())
        self.assertIn('No current', self.ask('term 1 syllabus')['reply'])
        self.assertIn('No current', self.ask('term 3 syllabus')['reply'])

    def test_scope_only_is_not_misread_as_a_subject(self):
        self.publish(sample())
        self.assertIn('Synthetic chapter', self.ask('term 2 syllabus only')['reply'])
        self.state.clear()
        self.publish(sample('timetable'))
        self.assertIn('Period 0', self.ask('my timetable sunday only')['reply'])

    def test_mixed_named_target_clarification_does_not_substitute_own(self):
        self.publish(sample())
        result = self.ask('term 2 syllabus and Omar Khan timetable')
        self.assertIn('Which request', result['reply'])
        actions = self.state['chat_choices']['options']
        self.assertEqual(actions[1]['message'], 'Omar Khan timetable')
        self.assertNotIn('my timetable', str(actions))

    def test_new_subject_and_term_corrections_are_dynamic(self):
        item = sample(); item['rows'].append(dict(subject='Psychology', section='Book', chapter='7', topic='Synthetic behaviour'))
        self.publish(item)
        self.assertIn('Synthetic chapter', self.ask('term 2 syllabus')['reply'])
        result = self.ask('Psychology')
        self.assertIn('Synthetic behaviour', result['reply'])
        self.assertNotIn('Synthetic chapter', result['reply'])
        self.assertIsNone(self.ask('what are the fees'))
        self.assertNotIn('document_context', self.state)

    def test_stale_document_and_changed_identity_deny_selection(self):
        item = self.publish(sample())
        reply = self.ask('syllabus')
        action = consume(self.state, reply['choices'][0]['token'], self.owner)
        self.store.transition(item['document_id'], 'withdraw', item['revision'], item['publication_version'], 'Admin')
        self.assertIn('no longer available', self.ask('chosen document', action)['reply'])
        self.publish(sample())
        reply = self.ask('syllabus')
        with self.assertRaises(ValueError):
            consume(self.state, reply['choices'][0]['token'], (3, 'parent', 4))

    def test_timetable_zero_alternatives_teacher_scope_and_no_model(self):
        self.publish(sample('timetable'))
        result = self.ask('my timetable')
        self.assertIn('Period 0', result['reply'])
        self.assertIn('COM / PE / Mathematics', result['reply'])
        self.assertIn('07:00', result['reply'])
        teacher = sample('teacher_timetable')
        self.assertFalse(visible(teacher, self.identity))
        self.assertFalse(visible(teacher, dict(role='teacher', teacher_id=8)))
        self.assertTrue(visible(teacher, dict(role='teacher', teacher_id=7)))

    def test_parent_guest_wrong_class_and_clear_do_not_expand_access(self):
        self.publish(sample())
        self.identity = dict(role='parent', classes=['12-F'])
        self.assertIn('No current', self.ask('grade 11 syllabus')['reply'])
        self.state.clear()
        self.identity = dict(role='guest', classes=[])
        self.assertIn('sign in', self.ask('syllabus')['reply'])

    def test_choice_nonce_expiry_and_forgery(self):
        choice = offer(self.state, [('Example', {'message': 'safe server message'})], self.owner)[0]
        with self.assertRaises(ValueError):
            consume(self.state, choice['token'] + '9', self.owner)
        choice = offer(self.state, [('Example', {'message': 'safe server message'})], self.owner, ttl=-1)[0]
        with self.assertRaises(ValueError):
            consume(self.state, choice['token'], self.owner)
        self.assertEqual(self.state, {})


if __name__ == '__main__':
    unittest.main()
