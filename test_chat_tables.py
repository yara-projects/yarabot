"""Table formatting and handler scope checks; synthetic results only."""

import unittest
from unittest.mock import patch

import app
from chat_tables import cell, data_table, timetable_grid
import test_v6_regressions as v6


class ChatTableTests(unittest.TestCase):
    def test_grid_keeps_period_zero_and_school_week_order(self):
        result = timetable_grid([('Monday', 2, 'English', 'Teacher'), ('Sunday', 0, 'Class teacher', 'Teacher'), ('Sunday', 2, 'Accountancy', 'Teacher')])
        self.assertIn('| Day | Period 0 | Period 2 |', result)
        self.assertLess(result.index('| Sunday |'), result.index('| Monday |'))
        self.assertIn('| Monday | — | English |', result)

    def test_options_are_preserved_not_overwritten(self):
        result = timetable_grid([('Sunday', 2, 'Computer Science'), ('Sunday', 2, 'Physical Education'), ('Sunday', 2, 'Mathematics')])
        self.assertIn('Computer Science / Physical Education / Mathematics', result)

    def test_untrusted_cells_cannot_inject_html_or_extra_columns(self):
        result = data_table(['Subject'], [['<img src=x onerror=alert(1)> | injected\nnext']])
        self.assertNotIn('<img', result)
        self.assertIn('&lt;img', result)
        self.assertIn('\\| injected<br>next', result)

    def test_empty_cell_is_not_invented_free_period(self):
        result = timetable_grid([('Sunday', 1, '12-F'), ('Monday', 2, '10-A')], teacher=True)
        self.assertIn('not confirmation of a free period', result)
        self.assertNotIn('7:10', result)

    def test_student_query_scope_is_unchanged(self):
        with patch.object(app, '_known_subject_names', return_value=[]), patch.object(app, 'query', return_value=[('Monday', 1, 'Accountancy', 'Example Teacher')]) as database:
            result = app.handle_student_timetable('my timetable monday', 42)
        self.assertIn('| Monday | Accountancy |', result)
        self.assertEqual(database.call_args.args[1], (42, 'monday'))
        self.assertNotIn('Example Teacher', result.split('\n\nCells')[0])
        self.assertIn('<summary>Subject teachers</summary>', result)

    def test_teacher_query_scope_and_class_retained(self):
        with patch.object(app, 'query', return_value=[('Monday', 1, '12-F')]) as database:
            result = app.handle_teacher_timetable('my timetable monday', 8)
        self.assertIn('| Monday | 12-F |', result)
        self.assertEqual(database.call_args.args[1], (8, 'monday'))


class TimetableRouteTests(unittest.TestCase):
    setUp = v6.V6Tests.setUp
    records = v6.V6Tests.records
    client = v6.V6Tests.client
    turns = v6.V6Tests.turns

    def test_student_monday_then_whole_week_are_tables(self):
        with patch('traffic_feedback.save_event'):
            replies = self.turns(self.client('student'), ['can i get mondays timetable?', 'can i get my whole timetable'])
        for reply in replies:
            self.assertIn('| Day | Period 1 |', reply)
            self.assertIn('| Monday | Chemistry |', reply)
            self.assertNotIn('Period 1:', reply)
        timetable_calls = [(sql, params) for sql, params in self.calls if 'FROM timetable' in sql]
        self.assertIn('monday', timetable_calls[0][1])
        self.assertNotIn('monday', timetable_calls[-1][1])

    def test_timetable_wording_does_not_replace_other_targets(self):
        for question in ['exam timetable monday', 'school hours monday', 'Other Person timetable monday']:
            self.assertNotEqual(app._explicit_lookup_intent(question, 'student'), 'timetable')

    def test_teacher_and_authorised_class_routes_are_tables(self):
        with patch('traffic_feedback.save_event'):
            teacher = self.turns(self.client('teacher'), ['my timetable monday'])[0]
            principal = self.turns(self.client('principal'), ['timetable for class 10-A monday'])[0]
        self.assertIn('| Day | Period 1 |', teacher)
        self.assertIn('Cells show class/division', teacher)
        self.assertIn('| Day | Period 1 |', principal)

    def test_parent_timetable_route_is_a_table(self):
        with patch('traffic_feedback.save_event'):
            reply = self.turns(self.client('parent'), ['my childs timetable monday'])[0]
        self.assertIn('| Monday | Chemistry |', reply)


if __name__ == '__main__':
    unittest.main()
