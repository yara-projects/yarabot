"""Phase 1: synthetic chat requests, captured output, no school writes/providers."""

from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
import time
import unittest
from unittest.mock import MagicMock, patch

import mysql.connector
import app
import gemini_rag
import test_v6_regressions as v6
from log_privacy import exclude_complaint_text, safe_log


SECRET = 'synthetic-private-canary-7932'


class PrivacyLoggingTests(unittest.TestCase):
    def setUp(self):
        v6.V6Tests.setUp(self)
        gemini_rag._cache.clear()
        self.addCleanup(gemini_rag._cache.clear)

    records = v6.V6Tests.records
    client = v6.V6Tests.client

    def capture_chat(self, routing, classifier=None):
        output = StringIO()
        with patch.object(app, 'get_routing_decision', return_value=routing), \
             patch.object(app, 'classify_personal_intent', return_value=classifier), \
             redirect_stdout(output), redirect_stderr(output):
            response = self.client('student').post('/api/chat', json={'message': 'i want to complain ' + SECRET})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(SECRET, output.getvalue())
        self.assertNotIn('i want to complain', output.getvalue())
        self.assertIn('/complaint', response.json['reply'])
        return output.getvalue()

    def test_real_chat_nlp_complaint_path_prints_only_metadata(self):
        output = self.capture_chat((True, False, 'complaint_feedback', 10, None, []))
        self.assertIn('intent=complaint_feedback', output)

    def test_complaint_intent_with_unmodified_router_has_no_text_in_output(self):
        output = StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            response = self.client('student').post('/api/chat', json={
                'message': 'i want to complain about my teacher ' + SECRET})
        self.assertEqual(response.status_code, 200)
        self.assertIn('/complaint', response.json['reply'])
        self.assertNotIn(SECRET, output.getvalue())
        self.assertNotIn('complain about my teacher', output.getvalue())

    def test_real_chat_classifier_and_tie_break_complaint_paths(self):
        for candidates in [[], [('complaint_feedback', 4), ('timetable', 4)]]:
            self.capture_chat((False, True, 'complaint_feedback', 4, 'Which intent?', candidates), 'complaint_feedback')

    def test_broken_stdout_does_not_break_complaint_chat(self):
        with patch('builtins.print', side_effect=OSError(SECRET)), \
             patch.object(app, 'get_routing_decision', return_value=(True, False, 'complaint_feedback', 10, None, [])):
            response = self.client('student').post('/api/chat', json={'message': 'i want to complain ' + SECRET})
            safe_log('metadata')
        self.assertEqual(response.status_code, 200)
        self.assertIn('/complaint', response.json['reply'])

    def test_complaint_text_never_enters_learning_or_tie_break_tables(self):
        with patch.object(gemini_rag.mysql.connector, 'connect') as connect, patch.object(app, 'query') as query:
            gemini_rag.log_learned_phrase(SECRET, 'complaint_feedback', 'student')
            gemini_rag.log_unanswered_question('my teacher is unfair ' + SECRET)
            app._log_tie_break(SECRET, 'student', [('complaint_feedback', 4)], 'timetable', False)
        connect.assert_not_called()
        query.assert_not_called()

    def test_complaint_context_excludes_implicit_followup(self):
        with app.app.test_request_context('/api/chat'):
            app.session['conversation_context'] = dict(intent='complaint_feedback', expires_at=time.time() + 60)
            self.assertTrue(exclude_complaint_text(SECRET))
            app.session.pop('conversation_context')
            with patch.object(gemini_rag.mysql.connector, 'connect') as connect:
                gemini_rag.log_unanswered_question(SECRET)
            connect.assert_not_called()
        with app.app.test_request_context('/api/chat'):
            self.assertFalse(exclude_complaint_text('what are the school hours'))

    def test_complaint_cache_is_not_shared_or_written(self):
        with patch.object(gemini_rag, 'get_almanac_snapshot', return_value=('', 1)):
            question = 'complaint ' + SECRET
            gemini_rag._cache[question] = dict(answer=SECRET, timestamp=time.time(), almanac_version=1)
            self.assertIsNone(gemini_rag.find_cached_answer(question))
            gemini_rag._cache.clear()
            gemini_rag.cache_answer(question, SECRET, 1)
            self.assertEqual(gemini_rag._cache, {})

    def test_logger_database_failures_do_not_echo_exception_text(self):
        output = StringIO()
        with patch.object(gemini_rag.mysql.connector, 'connect', side_effect=mysql.connector.Error(SECRET)), \
             redirect_stdout(output), redirect_stderr(output):
            gemini_rag.log_unanswered_question('where can i buy school uniform')
            gemini_rag.log_learned_phrase('my weekly lessons', 'timetable', 'student')
        self.assertNotIn(SECRET, output.getvalue())
        self.assertIn('LOG ERROR', output.getvalue())

    def test_complaint_write_error_does_not_echo_database_payload(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value
        cursor.fetchone.side_effect = [(1,), (0,)]
        cursor.execute.side_effect = [None, None, mysql.connector.Error(SECRET)]
        output = StringIO()
        with patch.object(app, 'get_db', return_value=connection), redirect_stdout(output), redirect_stderr(output):
            self.assertEqual(app._save_complaint(1, 7, SECRET, 'behavior', False), 'error')
        connection.rollback.assert_called_once()
        self.assertNotIn(SECRET, output.getvalue())

    def test_streaming_provider_error_does_not_echo_payload(self):
        output = StringIO()
        with patch.object(gemini_rag, 'get_almanac_snapshot', return_value=('', 1)), \
             patch.object(gemini_rag, '_documented_public_reply', return_value=None), \
             patch.object(gemini_rag, 'search_almanac', return_value='Synthetic context'), \
             patch.object(gemini_rag, 'ask_gemini_stream', side_effect=ValueError(SECRET)), \
             patch.object(gemini_rag, 'is_transient_provider_error', return_value=False), \
             redirect_stdout(output), redirect_stderr(output):
            self.assertEqual(''.join(gemini_rag.gemini_answer_stream(SECRET)), gemini_rag.API_ERROR_MESSAGE)
        self.assertNotIn(SECRET, output.getvalue())

    def test_provider_failure_and_cache_diagnostics_do_not_echo_questions(self):
        output = StringIO()
        with patch.object(gemini_rag, 'get_almanac_snapshot', return_value=('', 1)), \
             patch.object(gemini_rag, '_documented_public_reply', return_value=None), \
             patch.object(gemini_rag, 'search_almanac', return_value='Synthetic context'), \
             patch.object(gemini_rag, 'ask_gemini', side_effect=ValueError(SECRET)), \
             patch.object(gemini_rag, 'is_transient_provider_error', return_value=False), \
             redirect_stdout(output), redirect_stderr(output):
            self.assertEqual(gemini_rag.gemini_answer(SECRET), gemini_rag.API_ERROR_MESSAGE)
            gemini_rag.cache_answer(SECRET, 'Synthetic answer', 1)
            self.assertEqual(gemini_rag.find_cached_answer(SECRET), 'Synthetic answer')
        self.assertNotIn(SECRET, output.getvalue())


if __name__ == '__main__':
    unittest.main()
