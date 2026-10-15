"""Synthetic telemetry tests; no school DB or provider access."""
import unittest
from unittest.mock import MagicMock, patch

from flask import Flask, Response, g, jsonify, session

import traffic_feedback as traffic


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.secret_key = 'synthetic-test-secret'
        traffic.register_feedback(self.app)

        @self.app.post('/api/chat')
        def chat():
            from flask import request
            body = request.get_json() or {}
            if body.get('lane'):
                g.traffic.update(lane=body['lane'], intent='timetable', nlp_score=2)
            if body.get('stream'):
                return Response(iter(['data: {"chunk":"Safe answer"}\n\n', 'data: [DONE]\n\n']), mimetype='text/event-stream')
            if body.get('error'):
                return jsonify(error='Synthetic error'), 400
            if body.get('choices'):
                return jsonify(reply='Choose one', choices=['one'])
            return jsonify(reply='Safe answer')

        self.client = self.app.test_client()
        with self.client.session_transaction() as state:
            state.update(user_id=123456, role='student', linked_id=99999)
        self.events = []
        self.saved = patch.object(traffic, 'save_event', side_effect=lambda event, previous=None: self.events.append((dict(event), previous)))
        self.saved.start()
        self.addCleanup(self.saved.stop)

    def ask(self, text='my timetable', **extra):
        return self.client.post('/api/chat', json=dict(message=text, **extra), buffered=True)

    def vote(self, response, **extra):
        return self.client.post('/api/feedback', json={'answer_id': response.headers['X-Answer-ID'], 'rating': 'up', **extra},
                                headers={'X-Feedback-CSRF': response.headers['X-Feedback-CSRF']})

    def test_static_summary_never_echoes_names_ids_private_content(self):
        response = self.ask('Aryan Chopra 123456 attendance 93.61 fees unpaid private-canary')
        event = self.events[0][0]
        self.assertEqual(event['question_text'], 'attendance, fees')
        self.assertIsNone(event['class_group'])
        for secret in ('Aryan', 'Chopra', '123456', '93.61', 'private-canary', '99999'):
            self.assertNotIn(secret, str(event))
        self.assertTrue(event['completed'])
        self.assertIn('X-Answer-ID', response.headers)

    def test_complaint_only_has_intent_not_text_topic_or_feedback(self):
        response = self.ask('complaint about canary attendance', lane='classifier')
        event = self.events[0][0]
        self.assertEqual(event['intent'], 'complaint_feedback')
        self.assertIsNone(event['question_text'])
        self.assertIsNone(event['nlp_score'])
        self.assertNotIn('X-Answer-ID', response.headers)
        self.assertIsNone(self.events[0][1])

    def test_implicit_complaint_context_is_excluded(self):
        with self.client.session_transaction() as state:
            state['conversation_context'] = {'intent': 'complaint_feedback'}
        self.ask('and tomorrow')
        self.assertIsNone(self.events[0][0]['question_text'])

    def test_storage_outage_does_not_break_json(self):
        with patch.object(traffic, 'save_event', side_effect=RuntimeError('private-canary')):
            self.assertEqual(self.ask().json['reply'], 'Safe answer')

    def test_storage_outage_does_not_break_stream(self):
        with patch.object(traffic, 'save_event', side_effect=RuntimeError('private-canary')):
            self.assertIn(b'[DONE]', self.ask(stream=True).data)

    def test_telemetry_hook_exception_does_not_break_chat(self):
        with patch.object(traffic, 'topic_summary', side_effect=ValueError('private-canary')):
            self.assertEqual(self.ask().status_code, 200)

    def test_complete_stream_gets_one_event(self):
        self.ask(stream=True, lane='gemini')
        self.assertEqual(len(self.events), 1)
        self.assertTrue(self.events[0][0]['completed'])
        self.assertEqual(self.events[0][0]['lane'], 'gemini')

    def test_clarification_and_error_lane(self):
        self.ask(choices=True)
        self.assertEqual(self.events[-1][0]['lane'], 'clarification')
        response = self.ask(error=True)
        self.assertFalse(self.events[-1][0]['completed'])
        self.assertEqual(self.events[-1][0]['lane'], 'fallback')
        self.assertNotIn('X-Answer-ID', response.headers)

    def test_previous_answer_is_random_reference_not_user_id(self):
        first = self.ask()
        self.ask()
        self.assertEqual(self.events[-1][1], first.headers['X-Answer-ID'])

    def test_unauthenticated_feedback_denied(self):
        self.assertEqual(self.app.test_client().post('/api/feedback', json={}).status_code, 401)

    def test_missing_csrf_denied(self):
        self.ask()
        self.assertEqual(self.client.post('/api/feedback', json={}).status_code, 403)

    def test_cross_origin_denied(self):
        first = self.ask()
        response = self.client.post('/api/feedback', json={}, headers={
            'Origin': 'https://untrusted.invalid', 'X-Feedback-CSRF': first.headers['X-Feedback-CSRF']})
        self.assertEqual(response.status_code, 403)

    def test_invalid_rating_and_free_text_reason_denied(self):
        first = self.ask()
        self.assertEqual(self.vote(first, reason='private-canary').status_code, 400)
        self.assertEqual(self.vote(first, rating='unrecognised').status_code, 400)

    def test_feedback_db_failure_returns_503_not_chat_failure(self):
        first = self.ask()
        with patch.object(traffic, 'database', side_effect=RuntimeError('private-canary')):
            self.assertEqual(self.vote(first).status_code, 503)
        self.assertEqual(self.ask().status_code, 200)

    def test_atomic_vote_has_ownership_duplicate_completion_and_expiry_guards(self):
        first = self.ask()
        cursor = MagicMock(rowcount=1)
        cursor.fetchone.side_effect = [{'acquired': 1}, {'count': 0}, {'released': 1}]
        with patch.object(traffic, 'database', side_effect=lambda operation: operation(cursor)):
            self.assertEqual(self.vote(first).status_code, 200)
        update = next(call for call in cursor.execute.call_args_list if 'UPDATE query_log' in call.args[0])
        for guard in ('owner_hash=%s', 'rating IS NULL', 'completed=TRUE', 'INTERVAL 30 DAY'):
            self.assertIn(guard, update.args[0])
        self.assertEqual(update.args[1][3], self.events[0][0]['owner_hash'])

    def test_rate_limit_and_duplicate_status(self):
        first = self.ask()
        for count, rowcount, status in [(5, 1, 429), (0, 0, 409)]:
            cursor = MagicMock(rowcount=rowcount)
            cursor.fetchone.side_effect = [{'acquired': 1}, {'count': count}, {'released': 1}]
            with patch.object(traffic, 'database', side_effect=lambda operation: operation(cursor)):
                self.assertEqual(self.vote(first).status_code, status)

    def test_rephrase_query_is_same_owner_completed_same_topic_within_30_seconds(self):
        self.ask()
        event = self.events[0][0]
        cursor = MagicMock()
        cursor.fetchone.return_value = {'answer_id': 'a' * 32}
        with patch.object(traffic, 'database', side_effect=lambda operation: operation(cursor)):
            # Stop the event-capture mock to exercise the real persistence SQL.
            self.saved.stop()
            traffic.save_event(event, 'a' * 32)
        sql = next(call.args[0] for call in cursor.execute.call_args_list if 'SELECT answer_id' in call.args[0])
        self.assertIn('owner_hash=%s', sql)
        self.assertIn('completed=TRUE', sql)
        self.assertIn('question_text=%s', sql)
        self.assertIn('INTERVAL 30 SECOND', sql)
        self.assertIn('INTERVAL 30 DAY', cursor.execute.call_args_list[0].args[0])


if __name__ == '__main__':
    unittest.main()
