"""Reproductions from the 20261009-recovery-01 browser pilot."""
import unittest
from unittest.mock import patch

import app


class PilotRegressionTests(unittest.TestCase):
    def test_department_correction_retains_latest_leader_intent(self):
        with app.app.test_request_context('/'), \
             patch.object(app, '_known_departments', return_value=[(1, 'Science'), (2, 'English')]), \
             patch.object(app, '_known_subject_names', return_value=['English']), \
             patch.object(app, 'handle_department_leadership', side_effect=lambda department: department + ' leader'), \
             patch.object(app, 'handle_department_staff', side_effect=lambda department: department + ' staff'):
            app._remember_conversation_context('department_staff', 'science department', 'hod', 1, 'Science staff')
            self.assertEqual(app._resume_conversation_context('who runs it', 'hod', 1), 'Science leader')
            self.assertEqual(app._resume_conversation_context('what about English', 'hod', 1), 'English leader')
            self.assertEqual(app.session['conversation_context']['department'], 'English')

    def test_staff_followup_replaces_leader_intent(self):
        with app.app.test_request_context('/'), \
             patch.object(app, '_known_departments', return_value=[(1, 'Science'), (2, 'English')]), \
             patch.object(app, '_known_subject_names', return_value=[]), \
             patch.object(app, 'handle_department_staff', side_effect=lambda department: department + ' staff'), \
             patch.object(app, 'handle_department_leadership', side_effect=lambda department: department + ' leader'):
            app._remember_conversation_context('department_leadership', 'science department', 'hod', 1, 'Science leader')
            self.assertEqual(app._resume_conversation_context('who works there', 'hod', 1), 'Science staff')
            self.assertEqual(app._resume_conversation_context('what about English', 'hod', 1), 'English staff')

    def test_combined_report_comparison_and_breakdown_label_both_metrics(self):
        def records(sql, params=(), **kwargs):
            if 'SELECT class, school_section' in sql:
                return [('10-A', 'boys'), ('10-C', 'girls')]
            if 'st.attendance_pct' in sql:
                return [('10-A', 1, 'Fixture A', 62), ('10-C', 2, 'Fixture B', 72)]
            if 'st.fees_status' in sql:
                return [('10-A', 1, 'Fixture A')]
            return None

        client = app.app.test_client()
        with client.session_transaction() as session:
            session.update(user_id=1, role='principal', linked_id=None)
        with patch.object(app, 'query', side_effect=records), \
             patch.object(app, '_known_subject_names', return_value=[]), \
             patch.object(app, '_chatbot_enabled', return_value=True):
            client.post('/api/chat', json={'message': 'show attendance count and pending fee count'})
            for question in ['girls and boys comparison', 'section breakdown', 'class breakdown']:
                reply = client.post('/api/chat', json={'message': question}).get_json()['reply']
                self.assertIn('attendance below 75%', reply)
                self.assertIn('pending fees', reply)
                self.assertIn('| boys |' if 'class' not in question else '| 10-A |', reply)


if __name__ == '__main__':
    unittest.main()
