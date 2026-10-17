"""Launcher selection tests; no real server or school database is opened."""

import os
import unittest
from unittest.mock import MagicMock, patch

from auth_helpers import hash_password
from start_dashboard import main


class LauncherTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        dotenv = patch('start_dashboard.load_dotenv')
        dotenv.start()
        self.addCleanup(dotenv.stop)

    def test_default_local_launch_is_loopback_react_flask(self):
        app = MagicMock()
        with patch('admin_app.create_app', return_value=app) as factory, \
             patch('start_dashboard.Path.is_file', return_value=True), \
             patch('start_dashboard.os.execv') as execute:
            main([])
        factory.assert_called_once_with()
        app.run.assert_called_once_with(host='127.0.0.1', port=5010, debug=False, use_reloader=False)
        execute.assert_not_called()

    def test_missing_frontend_refuses_start(self):
        with patch('admin_app.create_app') as factory, \
             patch('start_dashboard.Path.is_file', return_value=False):
            with self.assertRaisesRegex(SystemExit, 'Build the dashboard first'):
                main([])
        factory.assert_not_called()

    def test_read_only_flag_is_explicit(self):
        with patch('admin_app.create_app', return_value=MagicMock()), \
             patch('start_dashboard.Path.is_file', return_value=True):
            main(['--read-only'])
        self.assertEqual(os.environ['DASHBOARD_READ_ONLY'], 'true')

    def test_legacy_streamlit_flag_is_retired(self):
        with self.assertRaises(SystemExit):
            main(['--legacy-streamlit'])

    def test_hosted_default_uses_gunicorn(self):
        os.environ.update(DASHBOARD_HOSTED='true', PORT='10001')
        with patch('start_dashboard.os.execv') as execute:
            main([])
        command = execute.call_args.args[1]
        self.assertIn('gunicorn', command)
        self.assertIn('admin_app:create_app()', command)
        self.assertIn('0.0.0.0:10001', command)
        self.assertEqual(command[command.index('--workers') + 1], '1')

    def test_local_setup_uses_user_chosen_credentials_and_real_database_mode(self):
        os.environ.update(USE_CLOUD_DB='true', DASHBOARD_READ_ONLY='true')
        app = MagicMock()
        with patch('builtins.input', return_value='private_admin'), \
             patch('start_dashboard.getpass', side_effect=['unique-local-password', 'unique-local-password']), \
             patch('admin_app.create_app', return_value=app), \
             patch('start_dashboard.Path.is_file', return_value=True):
            main(['--local-setup'])
        self.assertEqual(os.environ['DASHBOARD_ADMIN_USERNAME'], 'private_admin')
        self.assertEqual(os.environ['DASHBOARD_ADMIN_PASSWORD_HASH'], hash_password('unique-local-password'))
        self.assertEqual(os.environ['DASHBOARD_READ_ONLY'], 'false')
        self.assertEqual(os.environ['DASHBOARD_LIVE_DATA'], 'true')
        self.assertGreaterEqual(len(os.environ['DASHBOARD_SESSION_SECRET']), 32)
        app.run.assert_called_once_with(host='127.0.0.1', port=5010, debug=False, use_reloader=False)

    def test_local_setup_rejects_sample_password_and_can_preserve_read_only(self):
        os.environ['USE_CLOUD_DB'] = 'true'
        with patch('builtins.input', side_effect=['bad user', 'private_admin']), \
             patch('start_dashboard.getpass', side_effect=['synthetic-password', 'different-private-password', 'different-private-password']), \
             patch('admin_app.create_app', return_value=MagicMock()), \
             patch('start_dashboard.Path.is_file', return_value=True):
            main(['--local-setup', '--read-only'])
        self.assertEqual(os.environ['DASHBOARD_READ_ONLY'], 'true')

    def test_local_setup_refuses_hosted_and_missing_cloud_configuration(self):
        with self.assertRaisesRegex(SystemExit, 'USE_CLOUD_DB'):
            main(['--local-setup'])
        os.environ['RENDER'] = 'true'
        with self.assertRaises(SystemExit):
            main(['--local-setup'])

if __name__ == '__main__':
    unittest.main()
