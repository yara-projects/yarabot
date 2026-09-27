"""Regressions for the low-latency RAG path."""

import unittest
from unittest.mock import MagicMock, patch

import app
import gemini_rag


class RagRoutingTests(unittest.TestCase):
    def _decision(self, ranked, confidence=(0, False), context='', question='test question'):
        with patch.object(app, 'is_pure_greeting', return_value=False), \
             patch.object(app, 'is_policy_framed', return_value=False), \
             patch.object(app, '_explicit_lookup_intent', return_value=None), \
             patch.object(app, 'is_personal_question', return_value=False), \
             patch.object(app, 'is_general_knowledge_question', return_value=False), \
             patch.object(app, 'rank_intents', return_value=ranked), \
             patch.object(app, '_apply_subject_scoring_adjustment', side_effect=lambda value, *_: value), \
             patch.object(app, 'almanac_match_confidence', return_value=confidence), \
             patch.object(app, 'search_almanac', return_value=context):
            return app.get_routing_decision(question, 'student')

    def test_public_retrieval_skips_classifier_when_nlp_has_no_match(self):
        decision = self._decision([], confidence=(2.5, False), context='SCHOOL CAMPUS')
        self.assertEqual(decision[:2], (False, False))

    def test_genuine_miss_still_uses_classifier(self):
        decision = self._decision([], confidence=(0, False), context='')
        self.assertEqual(decision[:2], (False, True))

    def test_vague_one_word_retrieval_still_uses_classifier(self):
        decision = self._decision([], confidence=(2, False), context='TEACHERS', question='teacher')
        self.assertEqual(decision[:2], (False, True))

    def test_strict_almanac_win_skips_classifier(self):
        decision = self._decision([('attendance', 2)], confidence=(8, True), context='POLICY')
        self.assertEqual(decision[:2], (False, False))

    def test_weak_personal_match_keeps_existing_nlp_route(self):
        decision = self._decision([('attendance', 2)], confidence=(1, False), context='POLICY')
        self.assertEqual(decision[:2], (True, False))


class RagCacheTests(unittest.TestCase):
    def setUp(self):
        gemini_rag._notice_rows_cache.clear()
        gemini_rag._cached_almanac_index.cache_clear()
        gemini_rag._cache.clear()

    def tearDown(self):
        gemini_rag._notice_rows_cache.clear()
        gemini_rag._cached_almanac_index.cache_clear()
        gemini_rag._gemini_client = None
        gemini_rag._gemini_client_key = None
        gemini_rag._groq_client = None
        gemini_rag._groq_client_key = None
        gemini_rag._cache.clear()

    def test_notice_rows_are_reused_within_ttl(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = [('Sports Day', 'Friday')]
        connection = MagicMock()
        connection.cursor.return_value = cursor
        with patch.object(gemini_rag.mysql.connector, 'connect', return_value=connection) as connect:
            first = gemini_rag._notice_rows({'student'})
            second = gemini_rag._notice_rows({'student'})
        self.assertEqual(first, second)
        self.assertEqual(connect.call_count, 1)

    def test_expired_notice_cache_fails_open_to_last_good_rows(self):
        roles = ('student',)
        gemini_rag._notice_rows_cache[roles] = {
            'rows': (('Sports Day', 'Friday'),),
            'loaded_at': 0,
        }
        with patch.object(gemini_rag.mysql.connector, 'connect', side_effect=OSError('offline')):
            self.assertEqual(gemini_rag._notice_rows(roles), (('Sports Day', 'Friday'),))

    def test_provider_clients_are_reused(self):
        with patch.dict(gemini_rag.os.environ, {'GEMINI_API_KEY': 'test-gemini', 'GROQ_API_KEY': 'test-groq'}), \
             patch.object(gemini_rag.genai, 'Client', return_value=object()) as gemini_client, \
             patch.object(gemini_rag, 'OpenAI', return_value=object()) as groq_client:
            self.assertIs(gemini_rag._get_gemini_client(), gemini_rag._get_gemini_client())
            self.assertIs(gemini_rag._get_groq_client(), gemini_rag._get_groq_client())
        self.assertEqual(gemini_client.call_count, 1)
        self.assertEqual(groq_client.call_count, 1)

    def test_gemini_timeout_falls_back_to_grounded_groq_answer(self):
        with patch.object(gemini_rag, 'search_notice_context', return_value=''), \
             patch.object(gemini_rag, 'get_almanac_snapshot', return_value=('SCHOOL HOURS', 1)), \
             patch.object(gemini_rag, 'search_almanac', return_value='SCHOOL HOURS'), \
             patch.object(gemini_rag, 'ask_gemini_stream', side_effect=TimeoutError('timed out')), \
             patch.object(gemini_rag, 'ask_groq', return_value='School starts at 7 AM.') as groq:
            answer = ''.join(gemini_rag.gemini_answer_stream('when does school start'))
        self.assertEqual(answer, 'School starts at 7 AM.')
        groq.assert_called_once_with('when does school start', 'SCHOOL HOURS')

    def test_almanac_index_is_reused_for_same_revision(self):
        text = 'SCHOOL HOURS\nOpening time is 7 AM.'
        gemini_rag._score_almanac_sections('school hours', text)
        gemini_rag._score_almanac_sections('opening time', text)
        info = gemini_rag._cached_almanac_index.cache_info()
        self.assertEqual(info.misses, 1)
        self.assertEqual(info.hits, 1)


if __name__ == '__main__':
    unittest.main()
