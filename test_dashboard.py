"""Dashboard UI and hosted startup checks, using synthetic data only."""

import os
import unittest
from unittest.mock import patch, MagicMock

from streamlit.testing.v1 import AppTest
from auth_helpers import hash_password
from start_dashboard import validate_environment


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {
            "DASHBOARD_HOSTED": "false", "RENDER": "false",
            "DASHBOARD_ADMIN_USERNAME": "test-admin",
            "DASHBOARD_ADMIN_PASSWORD_HASH": hash_password("test-dashboard-password"),
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def app(self):
        return AppTest.from_file("dashboard.py", default_timeout=20)

    def test_login_does_not_expose_editors(self):
        app = self.app().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.title[0].value, "Welcome back")
        self.assertFalse(app.sidebar.radio)
        app.text_input[0].set_value("test-admin")
        app.text_input[1].set_value("incorrect")
        app.button[0].click().run()
        self.assertTrue(app.error)
        self.assertFalse(app.sidebar.radio)

    def test_login_overview_and_logout_clear_editor_state(self):
        conn = MagicMock()
        conn.cursor.return_value.fetchone.return_value = (12, 4, 7, 9)
        with patch("mysql.connector.connect", return_value=conn):
            app = self.app().run()
            app.text_input[0].set_value("test-admin")
            app.text_input[1].set_value("test-dashboard-password")
            app.button[0].click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.title[0].value, "Overview")
            self.assertEqual(len(app.metric), 4)
            app.session_state["almanac_content_1"] = "private unsaved editor text"
            app.button(key="dashboard_logout").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.title[0].value, "Welcome back")
            self.assertNotIn("almanac_content_1", app.session_state.filtered_state)

    def test_almanac_first_save_and_conflict(self):
        state = {"content": "Original fact", "version": 1}

        def save(content, version):
            if version != state["version"]:
                return False
            state.update(content=content, version=version + 1)
            return True

        with patch("almanac_store.read_almanac", side_effect=lambda: (state["content"], state["version"])), \
             patch("almanac_store.save_almanac", side_effect=save) as writer:
            app = self.app()
            app.session_state["admin_logged_in"] = True
            app.session_state["dashboard_section"] = "Nova & school information"
            app.run()
            self.assertFalse(app.exception)
            app.text_area[0].set_value("Changed fact")
            next(b for b in app.button if b.label == "Save Changes").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(state["content"], "Changed fact")
            self.assertEqual(app.text_area[0].value, "Changed fact")
            self.assertTrue(app.success)
            self.assertEqual(writer.call_count, 1)
            state.update(content="Concurrent fact", version=3)
            app.text_area[0].set_value("Stale fact")
            next(b for b in app.button if b.label == "Save Changes").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(state["content"], "Concurrent fact")
            self.assertTrue(app.warning)
            self.assertFalse(app.success)

    def test_table_search_is_literal_and_preserves_original(self):
        app = AppTest.from_string('''
import pandas as pd
from dashboard_ui import searchable_table
searchable_table(pd.DataFrame({"Name": ["Alice", "Bob"], "Class": ["10-A", "8-C"]}), "test")
''').run()
        app.text_input[0].set_value("10-a").run()
        self.assertEqual(len(app.dataframe[0].value), 1)
        app.text_input[0].set_value("[").run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.dataframe[0].value), 0)
        app.text_input[0].set_value("").run()
        self.assertEqual(len(app.dataframe[0].value), 2)

    def test_hosted_configuration_rejects_defaults_and_missing_secrets(self):
        with self.assertRaises(ValueError):
            validate_environment({})
        env = {key: "configured" for key in ["DASHBOARD_ADMIN_USERNAME", "CLOUD_DB_HOST",
               "CLOUD_DB_USER", "CLOUD_DB_PASSWORD", "CLOUD_DB_NAME", "DASHBOARD_API_TOKEN"]}
        env.update(USE_CLOUD_DB="true", FLASK_APP_URL="https://example.com",
                   DASHBOARD_ADMIN_PASSWORD_HASH=hash_password("admin1234"))
        with self.assertRaises(ValueError):
            validate_environment(env)
        env["DASHBOARD_ADMIN_PASSWORD_HASH"] = hash_password("test-dashboard-password")
        validate_environment(env)
        env["USE_CLOUD_DB"] = "false"
        with self.assertRaises(ValueError):
            validate_environment(env)


if __name__ == "__main__":
    unittest.main()
