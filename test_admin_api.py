"""React admin API checks: only synthetic repositories, never school DB writes."""

from copy import deepcopy
import unittest
from unittest.mock import MagicMock, patch

from admin_app import create_app, RESOURCES, AdminError, MySQLRepository, public_row, record_revision, validate_record
from auth_helpers import hash_password


class SyntheticRepository:
    def __init__(self):
        self.rows = {key: [] for key in RESOURCES}
        self.rows["students"] = [dict(student_id=1, name="Example Student", **{"class": "12-F"}, roll_no=1,
                                      dob="2008-04-10", parent_name="Example Parent", parent_contact="+966500000000",
                                      fees_status="paid", attendance_pct=93.5)]
        self.rows["teachers"] = [dict(teacher_id=1, name="Example Teacher", contact="", classes_assigned="12-F", department_id=1)]
        self.rows["subjects"] = [dict(subject_id=1, subject_name="Accountancy", **{"class": "12-F"})]
        self.rows["departments"] = [dict(department_id=1, name="Commerce", hod_teacher_id=1)]
        self.rows["notices"] = [dict(notice_id=1, title="Synthetic notice", body="Local demonstration data only.", date_posted="2026-10-15", target_roles="all", priority="normal")]
        self.content, self.version, self.writes = "SCHOOL HOURS\nExample only.", 1, 0

    def overview(self):
        return dict(students=len(self.rows["students"]), teachers=len(self.rows["teachers"]),
                    subjects=len(self.rows["subjects"]), accounts=0, suggestions=0, attendance_risk=0, pending_fees=0)

    def records(self, resource, search, page, size):
        rows = [row for row in self.rows[resource] if search.casefold() in " ".join(str(v) for v in row.values()).casefold()]
        return dict(rows=[public_row(row) for row in rows[(page - 1) * size:page * size]], total=len(rows))

    def save_record(self, resource, data, record_id=None, revision=None, delete=False):
        key = RESOURCES[resource]["pk"]
        if record_id is not None:
            row = next((r for r in self.rows[resource] if str(r[key]) == str(record_id)), None)
            if row is None:
                raise AdminError("Record not found", 404)
            if record_revision(row) != revision:
                raise AdminError("Someone changed this record. Refresh before saving.", 409)
            if delete:
                self.rows[resource].remove(row)
            else:
                row.update(data)
        else:
            row = deepcopy(data)
            row.setdefault(key, max([r[key] for r in self.rows[resource] if isinstance(r[key], int)], default=0) + 1)
            self.rows[resource].append(row)
        self.writes += 1

    def almanac(self):
        return dict(content=self.content, version=self.version)

    def save_almanac(self, content, version):
        if version != self.version:
            return False
        self.content, self.version = content, self.version + 1
        self.writes += 1
        return True


class AdminApiTests(unittest.TestCase):
    def setUp(self):
        self.repo = SyntheticRepository()
        self.app = create_app(dict(TESTING=True, SECRET_KEY="synthetic-test-secret-not-production-123456",
                                   ADMIN_USERNAME="test-admin", ADMIN_PASSWORD_HASH=hash_password("synthetic-test-password")), self.repo)
        self.client = self.app.test_client()
        self.csrf = self.client.get("/api/session").json["csrf"]

    def post(self, path, payload=None, method="POST"):
        return self.client.open(path, method=method, json=payload, headers={"X-CSRF-Token": self.csrf})

    def login(self):
        result = self.post("/api/login", dict(username="test-admin", password="synthetic-test-password"))
        self.assertEqual(result.status_code, 200)
        self.csrf = result.json["csrf"]

    def test_read_only_mode_blocks_every_data_mutation_but_allows_login_and_reads(self):
        self.app.config['ADMIN_READ_ONLY'] = True
        self.login()
        self.assertTrue(self.client.get('/api/session').json['read_only'])
        catalog = self.client.get('/api/catalog').json
        self.assertTrue(catalog['read_only'])
        self.assertTrue(all(not spec['editable'] for spec in catalog['resources'].values()))
        self.assertEqual(self.client.get('/api/records/students').status_code, 200)
        self.assertEqual(self.client.get('/api/almanac').status_code, 200)
        for path, method in [('/api/records/students', 'POST'), ('/api/records/students/1', 'PUT'),
                             ('/api/records/students/1', 'DELETE'), ('/api/almanac', 'PUT'),
                             ('/api/relations/parent-children/1', 'PUT'), ('/api/system', 'PUT'),
                             ('/api/imports', 'POST'), ('/api/imports/test/publish', 'POST'),
                             ('/api/phrases/manual/check', 'POST')]:
            result = self.post(path, {}, method)
            self.assertEqual(result.status_code, 403, (path, result.status_code))
            self.assertIn('Read-only', result.json['error'])
        self.assertEqual(self.repo.writes, 0)
        self.assertEqual(self.post('/api/logout').status_code, 200)

    def test_read_only_repository_uses_database_read_only_transaction(self):
        repository = MySQLRepository()
        repository.read_only = True
        connection = MagicMock()
        with patch('admin_app.mysql.connector.connect', return_value=connection):
            with repository.connection():
                pass
        connection.start_transaction.assert_called_once_with(readonly=True)
        connection.close.assert_called_once_with()

    def test_login_required_for_every_data_page(self):
        for path in ["/api/overview", "/api/catalog", "/api/records/students", "/api/almanac"]:
            self.assertEqual(self.client.get(path).status_code, 401)
        self.assertEqual(self.repo.writes, 0)

    def test_csrf_required_even_for_login(self):
        result = self.client.post("/api/login", json=dict(username="test-admin", password="synthetic-test-password"))
        self.assertEqual(result.status_code, 403)

    def test_production_quarantines_historical_chat_text_and_actions(self):
        self.login()
        self.app.config['TESTING'] = False
        self.repo.rows['suggestions'] = [dict(id=1, question_text='private complaint canary')]
        self.repo.rows['phrases'] = [dict(id=1, phrase_text='private complaint canary')]
        for path in ['/api/records/suggestions', '/api/records/phrases']:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 403)
            self.assertNotIn('canary', response.get_data(as_text=True))
        for path in ['/api/suggestions/1/append', '/api/phrases/1/check', '/api/phrases/1/approve']:
            self.assertEqual(self.post(path, {'confirmed': True}).status_code, 403)
        self.assertFalse(self.client.get('/api/catalog').json['legacy_review_available'])
        self.assertEqual(self.repo.writes, 0)

    def test_failed_login_rate_limit(self):
        for _ in range(5):
            self.assertEqual(self.post("/api/login", dict(username="test-admin", password="wrong")).status_code, 401)
        self.assertEqual(self.post("/api/login", dict(username="test-admin", password="synthetic-test-password")).status_code, 429)

    def test_logout_revokes_session_and_old_cookie(self):
        self.login()
        cookie = self.client.get_cookie("yara_admin_session").value
        self.assertEqual(self.client.get("/api/overview").status_code, 200)
        self.assertEqual(self.post("/api/logout").status_code, 200)
        self.client.set_cookie("yara_admin_session", cookie)
        self.assertEqual(self.client.get("/api/overview").status_code, 401)

    def test_old_csrf_cannot_write_after_login(self):
        old = self.csrf
        self.login()
        result = self.client.put("/api/almanac", json=dict(content="changed", version=1), headers={"X-CSRF-Token": old})
        self.assertEqual(result.status_code, 403)

    def test_expired_server_session_denied(self):
        self.login()
        for info in self.app.extensions["admin_sessions"].values():
            info["seen"] -= 1801
        self.assertEqual(self.client.get("/api/records/students").status_code, 401)

    def test_record_allowlist_and_no_password_field(self):
        self.login()
        result = self.client.get("/api/catalog")
        self.assertEqual(result.status_code, 200)
        self.assertNotIn("password", str(result.json))
        self.assertEqual(self.client.get("/api/records/not-a-table").status_code, 404)
        self.assertEqual(self.client.get("/api/records/students?size=100000").status_code, 400)
        self.assertEqual(self.client.get("/api/records/students?page=-1").status_code, 400)

    def test_optimistic_update_and_delete(self):
        self.login()
        row = self.client.get("/api/records/students").json["rows"][0]
        payload = {field["key"]: row[field["key"]] for field in RESOURCES["students"]["fields"]}
        payload["name"] = "Updated Student"
        result = self.post("/api/records/students/1", dict(record=payload, revision=row["_revision"]), "PUT")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(self.post("/api/records/students/1", dict(record=payload, revision=row["_revision"]), "PUT").status_code, 409)
        self.assertEqual(self.post("/api/records/students/1", dict(revision=row["_revision"]), "DELETE").status_code, 409)
        new_row = self.client.get("/api/records/students").json["rows"][0]
        self.assertEqual(self.post("/api/records/students/1", dict(revision=new_row["_revision"]), "DELETE").status_code, 200)
        self.assertEqual(len(self.repo.rows["students"]), 0)

    def test_almanac_conflict_preserves_current_content(self):
        self.login()
        self.assertEqual(self.post("/api/almanac", dict(content="First revision", version=1), "PUT").status_code, 200)
        self.assertEqual(self.post("/api/almanac", dict(content="Stale revision", version=1), "PUT").status_code, 409)
        self.assertEqual(self.repo.content, "First revision")

    def test_readonly_cannot_be_bypassed_by_direct_post(self):
        self.login()
        self.assertEqual(self.post("/api/records/phrases", dict(record={"phrase_text": "attack"})).status_code, 405)
        self.assertEqual(self.repo.writes, 0)

    def test_validation_rejects_extra_fields_and_nonfinite_attendance(self):
        spec = RESOURCES["students"]
        valid = {f["key"]: self.repo.rows["students"][0][f["key"]] for f in spec["fields"]}
        for changes in [{"attendance_pct": "NaN"}, {"attendance_pct": 101}, {"roll_no": 1.5}, {"is_admin": True}, {"class": "99-Z"}, {"dob": "not-a-date"}]:
            with self.assertRaises(AdminError):
                validate_record(spec, {**valid, **changes})

    def test_security_headers_and_no_api_cache(self):
        result = self.app.test_client().get("/api/session")
        self.assertEqual(result.headers["Cache-Control"], "no-store")
        self.assertEqual(result.headers["X-Frame-Options"], "DENY")
        self.assertIn("frame-ancestors 'none'", result.headers["Content-Security-Policy"])
        self.assertIn("HttpOnly", result.headers["Set-Cookie"])
        self.assertIn("SameSite=Strict", result.headers["Set-Cookie"])


if __name__ == "__main__":
    unittest.main()
