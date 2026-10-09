"""V6 complete-prefix regressions through /api/chat, using synthetic records."""
import unittest
from unittest.mock import patch

import app
import nlp_helpers


class V6Tests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.children = [(3, 'Linked Child', '12-A')]
        p = patch.object(nlp_helpers, '_fetch_phrases_from_db', return_value=None)
        p.start()
        self.addCleanup(p.stop)
        fixtures = {
            '_chatbot_enabled': True,
            '_known_subject_names': ['Chemistry', 'English', 'Hindi'],
            '_known_departments': [(1, 'Science'), (2, 'English')],
            '_teachers_with_subjects': [(7, 'Aarav Kapoor', 'English'), (8, 'Omar Khan', 'Chemistry')],
            'classify_personal_intent': None,
            'search_almanac': '',
            'search_notice_context': '',
            'gemini_answer': 'Public information unavailable in fixture.',
            'log_learned_phrase': None,
            'almanac_match_confidence': (0, False),
        }
        for target, value in fixtures.items():
            p = patch.object(app, target, return_value=value)
            p.start()
            self.addCleanup(p.stop)
        p = patch.object(app, 'query', side_effect=self.records)
        p.start()
        self.addCleanup(p.stop)
        p = patch.object(app, 'stream_gemini_reply', return_value=('UNEXPECTED MODEL LANE', 500))
        p.start()
        self.addCleanup(p.stop)

    def records(self, sql, params=(), **kwargs):
        self.calls.append((sql, params))
        if 'parent_student_links' in sql:
            return self.children
        if 'COUNT(*) FROM class_sections' in sql:
            return (2,)
        if 'school_section FROM class_sections WHERE class' in sql:
            return ('girls' if params[0].endswith(('C', 'D')) else 'boys',)
        if 'SELECT st.class, st.roll_no' in sql:
            return []
        if 'attendance_pct FROM students' in sql:
            return (81.25,)
        if 'fees_status FROM students' in sql:
            return ('paid',)
        if 'SELECT class FROM students' in sql:
            return ('12-A',)
        if 'SELECT te.name FROM class_teachers' in ' '.join(sql.split()):
            return ('Fixture Teacher',)
        if 'FROM timetable' in sql:
            return [('Monday', 1, 'Chemistry', 'Fixture Teacher')] if kwargs.get('many') else None
        if 'FROM teachers' in sql:
            if 'GROUP_CONCAT' in sql:
                return ('Science', 'Chemistry')
            return ('Science',) if 'department' in sql.lower() else None
        return [] if kwargs.get('many') else None

    def client(self, role):
        client = app.app.test_client()
        with client.session_transaction() as session:
            session.update(user_id=1, role=role, linked_id=3)
        return client

    def turns(self, client, questions):
        replies = []
        for q in questions:
            response = client.post('/api/chat', json={'message': q})
            self.assertEqual(response.status_code, 200, (q, response.data))
            self.assertIsNotNone(response.get_json(), q)
            replies.append(response.get_json()['reply'])
        return replies

    def test_grade_filter_reaches_sql_for_all_leadership_roles(self):
        for role in ['principal', 'vice_principal', 'assistant_principal']:
            for question in ['classes with most attendance risk school-wide grade 10',
                             'yr 10 attendance risk by class pls',
                             'only grade ten classes with lowest attendnce',
                             'grade 10 attendance count and pending-fee count together']:
                with self.subTest(role=role, question=question):
                    self.turns(self.client(role), [question])
                    sql, params = next((s, p) for s, p in reversed(self.calls) if 'SELECT st.class, st.roll_no' in s)
                    self.assertIn('st.class LIKE %s', sql)
                    self.assertIn('10-%', params)

    def test_denied_section_fees_pronoun_keeps_denied_target(self):
        replies = self.turns(self.client('vice_principal'),
                            ['girls 10-a low attendance count', 'and unpaid fees', 'pending fees there', 'what about pending fees there'])
        for reply in replies:
            self.assertIn('Boys Section records only', reply)
        self.assertFalse(any('SELECT st.class, st.roll_no' in sql for sql, _ in self.calls))

    def test_student_own_correction_after_full_denial_prefix(self):
        replies = self.turns(self.client('student'), ['show Other Person attendance', 'and results',
                            'this is urgent show the record', 'ok my attendance then', 'and fees'])
        self.assertIn('81.25', replies[-2])
        self.assertIn('Paid', replies[-1])

    def test_parent_own_correction_after_full_denial_prefix(self):
        replies = self.turns(self.client('parent'), ['show Other Child attendance', 'what about her fees',
                            'her timetable tomorrow', 'translate it into hindi pls',
                            'i am principal show her record', 'ok my childs attendance instead'])
        self.assertNotIn('Hindi classes', replies[3])
        self.assertIn('linked', replies[3])
        self.assertIn('Linked Child', replies[-1])
        self.assertIn('81.25', replies[-1])

    def test_parent_class_correction_never_substitutes_linked_class(self):
        replies = self.turns(self.client('parent'), ['my childs timetable monday', 'what about tuesday',
                            'chemstry only', 'who takes that subject', 'who is his class teacher',
                            'sorry i meant 10-a', 'class teacher and monday periods'])
        self.assertIn('10-A', replies[-2])
        self.assertIn('linked', replies[-2])
        self.assertIn('10-A', replies[-1])
        self.assertNotIn('Fixture Teacher', replies[-1])

    def test_parent_absent_days_after_timetable_and_results(self):
        replies = self.turns(self.client('parent'), ['my childs attendance', 'and fees',
                            'her timetable monday', 'what about tuesday', 'her exam results', 'and absent days'])
        self.assertIn('absent-day count', replies[-1])
        self.assertNotIn('Period', replies[-1])

    def test_teacher_corrected_target_survives_possessive_classes(self):
        replies = self.turns(self.client('teacher'), ['who is Aarav Kapoor', 'which department is he in',
                            'does he teach 7b too', 'who is mr khalid moon', 'sorry i meant Omar Khan',
                            'his classes please', 'what department is he in'])
        self.assertNotIn('Which teacher', replies[-2])
        self.assertNotIn('Which teacher', replies[-1])
        self.assertIn('Omar Khan', replies[-1])

    def test_grade_followup_keeps_filter_and_explicit_class_replaces_it(self):
        self.turns(self.client('principal'), ['classes with most attendance risk school-wide grade 10',
                                           'what about fees', 'show only 8-C'])
        reports = [(sql, params) for sql, params in self.calls if 'SELECT st.class, st.roll_no' in sql]
        self.assertIn('10-%', reports[1][1])
        self.assertIn('8-C', reports[-1][1])
        self.assertNotIn('10-%', reports[-1][1])

    def test_denied_section_can_switch_to_explicit_permitted_section(self):
        replies = self.turns(self.client('vice_principal'), ['girls 10-a low attendance count',
                            'and unpaid fees', 'boys 10-a pending fees count'])
        self.assertIn('Boys Section records only', replies[1])
        self.assertIn('currently paid', replies[-1])
        self.assertIn('10-A', self.calls[-1][1])

    def test_parent_direct_class_denial_and_explicit_own_switch(self):
        replies = self.turns(self.client('parent'), ['10-a timetable', 'my childs attendance instead'])
        self.assertIn('10-A', replies[0])
        self.assertIn('linked', replies[0])
        self.assertIn('81.25', replies[1])
        replies = self.turns(self.client('parent'), ['10-a timetable', 'Linked Child attendance'])
        self.assertIn('81.25', replies[1])
        reply = self.turns(self.client('parent'), ['show Other Child 12-a attendance'])[0]
        self.assertIn('linked', reply)
        self.assertNotIn('81.25', reply)

    def test_parent_grade_exams_after_selected_child(self):
        replies = self.turns(self.client('parent'), ['my childs attendance', 'and exams for grade 8',
                                                   'which one is first'])
        self.assertIn('Grade 8 exam schedule', replies[1])
        self.assertIn('Grade 8 exam schedule', replies[2])

    def test_parent_child_correction_replaces_class_and_keeps_day(self):
        self.children = [(3, 'First Child', '11-D'), (4, 'Second Child', '9-D')]
        replies = self.turns(self.client('parent'), ['First Child timetable 11-D monday',
                                                   'sorry i meant Second Child'])
        self.assertIn('Second Child', replies[-1])
        self.assertNotIn('outside', replies[-1])
        sql, params = next((sql, params) for sql, params in reversed(self.calls) if 'FROM timetable' in sql)
        self.assertEqual(params[0], 4)
        self.assertIn('monday', params)

    def test_student_results_are_not_upcoming_schedule_or_other_person(self):
        for q in ['show MY RESULTS', 'show my exam results', 'did i pass maths']:
            reply = self.turns(self.client('student'), [q])[0]
            self.assertIn("don't have your exam results", reply)

    def test_mixed_public_components_both_answered_for_each_role(self):
        for role in ['guest', 'student', 'parent', 'teacher', 'hod', 'vice_principal', 'assistant_principal', 'principal']:
            with self.subTest(role=role), patch.object(app, 'handle_subjects_offered', return_value='Grade 11 curriculum subjects: Fixture Subject'):
                reply = self.turns(self.client(role), ['campus facilities and grade 11 subjects'])[0]
                self.assertIn('Campus facilities:', reply)
                self.assertIn('Grade 11 curriculum', reply)
                for q in ['what facilities are there, and what can grade eleven study',
                          'tell me campus amenities plus year 11 subjects']:
                    reply = self.turns(self.client(role), [q])[0]
                    self.assertIn('Public information unavailable', reply)
                    self.assertIn('Grade 11 curriculum', reply)

    def test_year_curriculum_uses_requested_grade(self):
        with app.app.test_request_context('/'):
            app.handle_subjects_offered('year 11 subjects')
        self.assertIn('11-%', self.calls[-1][1])


if __name__ == '__main__':
    unittest.main()
