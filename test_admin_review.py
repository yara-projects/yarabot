"""Review acceptance checks: all data synthetic, external DB connections forbidden."""
from datetime import datetime, timedelta, timezone
import json
import unittest
from unittest.mock import patch

from admin_review import project
import test_admin_workflows as workflows


def event(**values):
    return dict(id=1, created_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1), question_text='fees',
                lane='fallback', intent='fee', nlp_score=1, likely_miss=1, completed=1, rating='down') | values


class ProjectionTests(unittest.TestCase):
    def test_no_private_text_identifiers_or_complaints_in_projection(self):
        result = project([event(), event(id=2, question_text='Secret Student 123456'),
                          event(id=3, question_text='attendance', intent='complaint_feedback'),
                          event(id=4, question_text=None),
                          event(id=5, question_text='fees', intent='Secret Teacher 888', owner_hash='secret-session')], {})
        encoded = json.dumps(result)
        for value in ['Secret', '123456', '888', 'secret-session', 'owner_hash', 'latest_id', 'complaint_feedback']:
            self.assertNotIn(value, encoded)
        self.assertEqual(result['current']['requests'], 2)
        self.assertEqual({row['intent'] for row in result['rows']}, {'fee', 'unclassified'})

    def test_periods_rates_signals_and_no_false_zero(self):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        result = project([event(created_at=now - timedelta(days=1)),
                          event(id=2, created_at=now - timedelta(days=8), lane='nlp', rating='up'),
                          event(id=3, created_at=now - timedelta(days=20)),
                          event(id=4, created_at=now + timedelta(days=1))], {}, now, 'phrases')
        self.assertEqual(result['current']['requests'], 1)
        self.assertEqual(result['current']['fallback_rate'], 100)
        self.assertEqual(result['previous']['nlp_rate'], 100)
        self.assertEqual(result['previous']['up_rate'], 100)
        self.assertEqual(result['rows'][0]['near_misses'], 1)
        self.assertEqual(result['rows'][0]['repeats'], 1)
        self.assertIsNone(project([], {}, now)['current']['up_rate'])

    def test_changed_evidence_reopens_resolved_group(self):
        row = project([event()], {})['rows'][0]
        resolved = {row['key']: row['revision']}
        self.assertEqual(project([event()], resolved)['rows'], [])
        self.assertEqual(len(project([event(), event(id=2)], resolved)['rows']), 1)

    def test_topic_allowlist_and_view_specific_signals(self):
        rows = [event(question_text='fees, attendance'), event(id=2, lane='nlp', likely_miss=0, rating=None)]
        result = project(rows, {}, view='knowledge')
        self.assertEqual(len(result['rows']), 1)
        self.assertEqual(result['rows'][0]['topic'], 'attendance, fees')
        self.assertEqual(project([event(question_text='fees, fees')], {})['rows'], [])


class ReviewWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.fixture = workflows.WorkflowTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.client, self.app, self.store = self.fixture.client, self.fixture.app, self.fixture.store
        self.store.db.executescript('''
            CREATE TABLE query_log(id INTEGER PRIMARY KEY,created_at TEXT,question_text TEXT,lane TEXT,
                intent TEXT,nlp_score REAL,likely_miss INTEGER,completed INTEGER,rating TEXT);
            CREATE TABLE admin_review_resolutions(review_key TEXT PRIMARY KEY,fingerprint TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
        ''')
        self.add_event(event())
        self.add_event(event(id=2, question_text='PRIVATE COMPLAINT CANARY', intent='complaint_feedback'))
        self.add_event(event(id=3, question_text='PRIVATE STUDENT CANARY'))
        blocked = patch('mysql.connector.connect', side_effect=AssertionError('External database access forbidden'))
        blocked.start()
        self.addCleanup(blocked.stop)
        self.app.config['TESTING'] = False

    def add_event(self, item):
        keys = list(item)
        self.store.db.execute('INSERT INTO query_log (' + ','.join(keys) + ') VALUES (' + ','.join('?' for _ in keys) + ')',
                              [item[key].isoformat(' ') if isinstance(item[key], datetime) else item[key] for key in keys])
        self.store.db.commit()

    def send(self, path, payload):
        return self.fixture.send(path, payload)

    def test_production_review_is_useful_without_exposing_legacy_text(self):
        result = self.client.get('/api/review/traffic?view=phrases')
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json['rows'][0]['topic'], 'fees')
        self.assertNotIn('PRIVATE', result.get_data(as_text=True))
        self.assertNotIn('question_text', result.get_data(as_text=True))
        self.assertEqual(self.client.get('/api/records/phrases').status_code, 403)
        self.assertEqual(self.client.get('/api/records/suggestions').status_code, 403)
        self.assertEqual(self.app.test_client().get('/api/review/traffic').status_code, 401)
        self.assertEqual(self.client.get('/api/review/traffic?view=raw').status_code, 400)

    def test_mark_reviewed_is_persistent_conflict_checked_and_reopens(self):
        row = self.client.get('/api/review/traffic?view=knowledge').json['rows'][0]
        path = '/api/review/' + row['key'] + '/resolve'
        self.assertEqual(self.send(path, dict(confirmed=True, revision='stale')).status_code, 409)
        self.assertEqual(self.send(path, dict(confirmed=True, revision=row['revision'])).status_code, 200)
        self.assertEqual(self.client.get('/api/review/traffic?view=knowledge').json['rows'], [])
        self.add_event(event(id=4))
        self.assertEqual(len(self.client.get('/api/review/traffic?view=knowledge').json['rows']), 1)
        self.assertEqual(self.send(path, dict(confirmed=True, revision=row['revision'])).status_code, 409)
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM query_log').fetchone()[0], 4)

    def test_verified_answer_append_and_stale_version_protection(self):
        payload = dict(confirmed=True, topic='Synthetic school policy', answer='Verified fixture answer. Source: QA only.', version=3)
        response = self.send('/api/review/almanac', payload)
        self.assertEqual(response.status_code, 200)
        content, version = self.store.db.execute('SELECT content,version FROM school_almanac WHERE id=1').fetchone()
        self.assertTrue(content.startswith('Existing verified information'))
        self.assertIn('Source: QA only.', content)
        self.assertEqual(version, 4)
        self.assertEqual(self.send('/api/review/almanac', payload).status_code, 409)
        self.assertEqual(self.send('/api/review/almanac', dict(payload, confirmed=False)).status_code, 400)
        self.assertEqual(self.send('/api/review/almanac', dict(payload, version=True)).status_code, 400)

    def test_review_mutations_require_csrf_and_respect_read_only(self):
        row = self.client.get('/api/review/traffic').json['rows'][0]
        path = '/api/review/' + row['key'] + '/resolve'
        self.assertEqual(self.client.post(path, json=dict(confirmed=True, revision=row['revision'])).status_code, 403)
        self.app.config['ADMIN_READ_ONLY'] = True
        self.assertEqual(self.send(path, dict(confirmed=True, revision=row['revision'])).status_code, 403)
        self.assertEqual(self.send('/api/review/almanac', dict(confirmed=True)).status_code, 403)
        self.assertEqual(self.client.get('/api/review/traffic?view=knowledge').status_code, 200)


if __name__ == '__main__':
    unittest.main()
