"""Independent admin API and React host. Never imports the chatbot application."""

from collections import defaultdict, deque
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from functools import wraps
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import secrets
import threading
import time

from flask import Flask, jsonify, request, send_from_directory, session
import mysql.connector
from werkzeug.exceptions import HTTPException

from auth_helpers import verify_password, hash_password
from config import DB_CONFIG
from validators import validate_name, validate_class, validate_contact, validate_username, validate_classes_assigned, validate_subject_name


DIST = Path(__file__).parent / "admin_frontend" / "dist"
IDLE_SECONDS = 30 * 60
SESSION_SECONDS = 8 * 60 * 60


def field(key, label, kind="text", required=True, options=None):
    return dict(key=key, label=label, kind=kind, required=required, options=options)


# All identifiers and SQL fragments are server-owned; no client-supplied SQL.
RESOURCES = {
    "students": dict(table="students", pk="student_id", title="Students", fields=[
        field("name", "Student name"), field("class", "Class"), field("roll_no", "Roll number", "number"),
        field("dob", "Date of birth", "date", False), field("parent_name", "Parent name", required=False),
        field("parent_contact", "Parent contact", required=False),
        field("fees_status", "Fee status", "select", options=["paid", "pending"]),
        field("attendance_pct", "Attendance %", "number")]),
    "teachers": dict(table="teachers", pk="teacher_id", title="Teachers", fields=[
        field("name", "Teacher name"), field("contact", "Contact", required=False),
        field("classes_assigned", "Assigned classes", required=False), field("department_id", "Department ID", "number", False)]),
    "parents": dict(table="parents", pk="parent_id", title="Parents", fields=[
        field("name", "Parent name"), field("contact", "Contact", required=False)]),
    "departments": dict(table="departments", pk="department_id", title="Departments", fields=[
        field("name", "Department name"), field("hod_teacher_id", "HOD teacher ID", "number", False)]),
    "subjects": dict(table="subjects", pk="subject_id", title="Subjects", fields=[
        field("subject_name", "Subject name"), field("class", "Class")]),
    "class-teachers": dict(table="class_teachers", pk="class", title="Class teachers", fields=[
        field("class", "Class"), field("teacher_id", "Teacher ID", "number")]),
    "class-sections": dict(table="class_sections", pk="class", title="Class sections", fields=[
        field("class", "Class"), field("school_section", "School section", "select", options=["boys", "girls"])]),
    "timetable": dict(table="timetable", pk="entry_id", title="Timetable", fields=[
        field("class", "Class"), field("day", "Day", "select", options=["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]),
        field("period_no", "Period", "number"), field("subject_id", "Subject ID", "number"), field("teacher_id", "Teacher ID", "number")]),
    "exams": dict(table="exams", pk="exam_id", title="Exam schedules", fields=[
        field("class", "Class"), field("subject_id", "Subject ID", "number"), field("exam_date", "Exam date", "date"), field("exam_type", "Assessment")]),
    "accounts": dict(table="users", pk="user_id", title="Chatbot accounts", fields=[
        field("username", "Username"), field("role", "Role", "select", options=['student', 'parent', 'teacher', 'hod', 'vice_principal', 'assistant_principal', 'principal']), field("linked_id", "Linked record", "number", False)]),
    "notices": dict(table="notices", pk="notice_id", title="Notices", fields=[
        field("title", "Title"), field("body", "Notice", "textarea"), field("date_posted", "Published date", "date"),
        field("target_roles", "Audience", "select", options=["all", "student", "teacher", "hod", "principal"]),
        field("priority", "Priority", "select", options=["normal", "important", "urgent"])]),
    "suggestions": dict(table="unanswered_questions", pk="id", title="Unanswered questions", fields=[
        field("question_text", "Question"), field("ask_count", "Times asked", "number"), field("last_asked", "Last asked")], readonly=True),
    "phrases": dict(table="learned_phrases", pk="id", title="Phrase review", fields=[
        field("phrase_text", "Phrase"), field("resolved_intent", "Intent"), field("role", "Role"),
        field("ask_count", "Times asked", "number"), field("applied", "Applied", "number")], readonly=True),
}


CLASS_RESOURCES = {key for key, spec in RESOURCES.items() if any(item['key'] == 'class' for item in spec['fields'])}


class AdminError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def json_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def record_revision(row):
    clean = {key: json_value(value) for key, value in row.items() if key != "_revision"}
    return hashlib.sha256(json.dumps(clean, sort_keys=True).encode()).hexdigest()


def public_row(row):
    return {**{key: json_value(value) for key, value in row.items() if key != 'password_hash'}, "_revision": record_revision(row)}


def validate_record(spec, data):
    if not isinstance(data, dict):
        raise AdminError("A record object is required.")
    allowed = {item["key"] for item in spec["fields"]}
    if set(data) - allowed:
        raise AdminError("Unexpected record fields.")
    result = {}
    for item in spec["fields"]:
        key = item["key"]
        value = data.get(key)
        if value is None or value == "":
            if item["required"]:
                raise AdminError(f"{item['label']} is required.")
            result[key] = None if item["kind"] in {"number", "date"} else ""
            continue
        if item["kind"] == "number":
            try:
                if isinstance(value, bool):
                    raise ValueError
                number = float(value)
                if not math.isfinite(number):
                    raise ValueError
                minimum = 0 if key in {'period_no', 'linked_id'} else 1
                if key != "attendance_pct" and (not number.is_integer() or number < minimum or number > 2147483647):
                    raise ValueError
                if key == "attendance_pct" and not 0 <= number <= 100:
                    raise ValueError
                result[key] = number if key == "attendance_pct" else int(number)
            except (TypeError, ValueError):
                raise AdminError(f"{item['label']} is not valid.") from None
        else:
            if not isinstance(value, str):
                raise AdminError(f"{item['label']} must be text.")
            value = value.strip()
            maximum = 20000 if key == "body" else (150 if key == "title" else 100)
            if not value or len(value) > maximum:
                raise AdminError(f"{item['label']} must contain 1–{maximum} characters.")
            if item["options"] and value not in item["options"]:
                raise AdminError(f"Choose a valid {item['label'].lower()}.")
            if item["kind"] == "date":
                try:
                    date.fromisoformat(value)
                except ValueError:
                    raise AdminError(f"{item['label']} must be a valid date.") from None
            if key == "class":
                valid, message = validate_class(value)
                if not valid:
                    raise AdminError(message)
                from csv_import import normalize_class_code
                value = normalize_class_code(value)
            if key in {"name", "parent_name"}:
                valid, message = validate_name(value)
                if not valid:
                    raise AdminError(message)
            if key in {"parent_contact", "contact"}:
                valid, message = validate_contact(value)
                if not valid:
                    raise AdminError(message)
            if key == 'username':
                valid, message = validate_username(value)
                if not valid or len(value) > 50:
                    raise AdminError(message or 'Username must contain at most 50 characters.')
            if key == 'subject_name':
                valid, message = validate_subject_name(value)
                if not valid:
                    raise AdminError(message)
            if key == 'classes_assigned':
                valid, message = validate_classes_assigned(value)
                if not valid:
                    raise AdminError(message)
                from csv_import import normalize_class_code
                value = ', '.join(normalize_class_code(part.strip()) for part in value.split(','))
            result[key] = value
    return result


class MySQLRepository:
    read_only = False

    @contextmanager
    def connection(self):
        conn = mysql.connector.connect(**{**DB_CONFIG, "connection_timeout": 8})
        try:
            if self.read_only:
                conn.start_transaction(readonly=True)
            yield conn
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def overview(self):
        with self.connection() as conn:
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute("SELECT (SELECT COUNT(*) FROM students) AS students, "
                               "(SELECT COUNT(*) FROM teachers) AS teachers, "
                               "(SELECT COUNT(*) FROM subjects) AS subjects, "
                               "(SELECT COUNT(*) FROM users) AS accounts, "
                               "(SELECT COUNT(*) FROM unanswered_questions) AS suggestions, "
                               "(SELECT COUNT(*) FROM students WHERE attendance_pct < 75) AS attendance_risk, "
                               "(SELECT COUNT(*) FROM students WHERE fees_status='pending') AS pending_fees")
                return cursor.fetchone()
            finally:
                cursor.close()

    @staticmethod
    def columns(spec):
        return list(dict.fromkeys([spec["pk"], *[f["key"] for f in spec["fields"]], *(['password_hash'] if spec['table'] == 'users' else [])]))

    def student_classes(self):
        return self.record_classes('students')

    def record_classes(self, resource):
        if resource not in CLASS_RESOURCES:
            raise AdminError('This record type does not have class filters.', 400)
        table = RESOURCES[resource]['table']
        with self.connection() as conn:
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute(f"SELECT DISTINCT class FROM `{table}` WHERE class IS NOT NULL AND class <> '' ORDER BY class")
                return [row['class'] for row in cursor.fetchall()]
            finally:
                cursor.close()

    def records(self, resource, search, page, size, grade="", class_filter=""):
        spec = RESOURCES[resource]
        columns = self.columns(spec)
        # Literal substring search, including %, _ and backslashes.
        escaped = search.replace("!", "!!").replace("%", "!%").replace("_", "!_")
        conditions = ["(" + " OR ".join(f"CAST(`{col}` AS CHAR) LIKE %s ESCAPE '!'" for col in columns) + ")"] if search else []
        params = [f"%{escaped}%"] * len(columns) if search else []
        if resource in CLASS_RESOURCES:
            if grade:
                conditions.append("`class` LIKE %s")
                params.append(f"{grade}-%")
            if class_filter:
                conditions.append("`class`=%s")
                params.append(class_filter)
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        with self.connection() as conn:
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute(f"SELECT COUNT(*) AS total FROM `{spec['table']}`{where}", params)
                total = cursor.fetchone()["total"]
                cursor.execute(f"SELECT {','.join('`'+c+'`' for c in columns)} FROM `{spec['table']}`{where} "
                               f"ORDER BY `{spec['pk']}` LIMIT %s OFFSET %s", [*params, size, (page - 1) * size])
                return dict(rows=[public_row(row) for row in cursor.fetchall()], total=total)
            finally:
                cursor.close()

    def save_record(self, resource, data, record_id=None, revision=None, delete=False):
        spec = RESOURCES[resource]
        with self.connection() as conn:
            cursor = conn.cursor(dictionary=True)
            try:
                if data:
                    self.validate_links(cursor, resource, data)
                if record_id is not None:
                    cursor.execute(f"SELECT {','.join('`'+c+'`' for c in self.columns(spec))} "
                                   f"FROM `{spec['table']}` WHERE `{spec['pk']}`=%s FOR UPDATE", (record_id,))
                    existing = cursor.fetchone()
                    if existing is None:
                        raise AdminError("This record no longer exists. Refresh the list.", 404)
                    if not revision or not hmac.compare_digest(record_revision(existing), str(revision)):
                        raise AdminError("Someone changed this record. Refresh before saving.", 409)
                    if spec["pk"] == "class" and data and data.get("class") != record_id:
                        raise AdminError("A class mapping cannot be renamed. Create the correct mapping instead.")
                if delete:
                    cursor.execute(f"DELETE FROM `{spec['table']}` WHERE `{spec['pk']}`=%s", (record_id,))
                elif record_id is not None:
                    keys = list(data)
                    cursor.execute(f"UPDATE `{spec['table']}` SET " + ",".join(f"`{k}`=%s" for k in keys)
                                   + f" WHERE `{spec['pk']}`=%s", [*[data[k] for k in keys], record_id])
                else:
                    keys = list(data)
                    cursor.execute(f"INSERT INTO `{spec['table']}` ({','.join('`'+k+'`' for k in keys)}) "
                                   f"VALUES ({','.join(['%s'] * len(keys))})", [data[k] for k in keys])
                conn.commit()
            finally:
                cursor.close()

    @staticmethod
    def validate_links(cursor, resource, data):
        for key, table, pk in [('teacher_id', 'teachers', 'teacher_id'), ('hod_teacher_id', 'teachers', 'teacher_id'), ('department_id', 'departments', 'department_id'), ('subject_id', 'subjects', 'subject_id')]:
            if data.get(key):
                cursor.execute(f'SELECT * FROM `{table}` WHERE `{pk}`=%s', (data[key],))
                row = cursor.fetchone()
                if not row:
                    raise AdminError(f'The selected {key.replace("_id", "").replace("_", " ")} does not exist.')
                if key == 'subject_id' and data.get('class') and row['class'] != data['class']:
                    raise AdminError('This subject belongs to another class. Choose the matching class subject.')
        if resource == 'accounts':
            role = data['role']
            mapping = {'student': ('students', 'student_id'), 'parent': ('parents', 'parent_id'), 'teacher': ('teachers', 'teacher_id'), 'hod': ('teachers', 'teacher_id'), 'vice_principal': ('teachers', 'teacher_id')}
            if role in mapping:
                table, key = mapping[role]
                cursor.execute(f'SELECT `{key}` FROM `{table}` WHERE `{key}`=%s', (data.get('linked_id'),))
                if not cursor.fetchone():
                    raise AdminError('Link this account to an existing person of the selected role.')
            elif data.get('linked_id') not in {None, 0}:
                raise AdminError('Principal/assistant principal accounts must not be linked to a student or teacher.')
            else:
                data['linked_id'] = 0

    def almanac(self):
        from almanac_store import read_almanac
        content, version = read_almanac()
        return dict(content=content, version=version)

    def save_almanac(self, content, version):
        from almanac_store import save_almanac
        return save_almanac(content, version)

    def relationship(self, kind, entity_id, values=None, revision=None):
        table, owner_key, member_key, owner_table, member_table, label = {
            'parent-children': ('parent_student_links', 'parent_id', 'student_id', 'parents', 'students', 'name'),
            'teacher-subjects': ('teacher_subjects', 'teacher_id', 'subject_id', 'teachers', 'subjects', 'subject_name'),
        }[kind]
        with self.connection() as conn:
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute(f'SELECT `{owner_key}` FROM `{owner_table}` WHERE `{owner_key}`=%s' + (' FOR UPDATE' if values is not None else ''), (entity_id,))
                if not cursor.fetchone():
                    raise AdminError('The selected person no longer exists.', 404)
                cursor.execute(f'SELECT `{member_key}` FROM `{table}` WHERE `{owner_key}`=%s ORDER BY `{member_key}`', (entity_id,))
                old = [row[member_key] for row in cursor.fetchall()]
                current = record_revision(dict(ids=old))
                if values is not None:
                    if current != revision:
                        raise AdminError('These links changed. Reload before saving.', 409)
                    for value in values:
                        cursor.execute(f'SELECT `{member_key}` FROM `{member_table}` WHERE `{member_key}`=%s', (value,))
                        if not cursor.fetchone():
                            raise AdminError(f'Linked record {value} does not exist.')
                    cursor.execute(f'DELETE FROM `{table}` WHERE `{owner_key}`=%s', (entity_id,))
                    for value in values:
                        cursor.execute(f'INSERT INTO `{table}` (`{owner_key}`,`{member_key}`) VALUES (%s,%s)', (entity_id, value))
                    conn.commit()
                cursor.execute(f'SELECT m.`{member_key}` AS id, m.`{label}` AS label FROM `{table}` l JOIN `{member_table}` m ON m.`{member_key}`=l.`{member_key}` WHERE l.`{owner_key}`=%s ORDER BY m.`{member_key}`', (entity_id,))
                members = cursor.fetchall()
                return dict(members=members, revision=record_revision(dict(ids=[row['id'] for row in members])))
            finally:
                cursor.close()

    def prepare_import(self, resource, rows):
        spec = RESOURCES[resource]
        with self.connection() as conn:
            cursor = conn.cursor(dictionary=True)
            try:
                for row in rows:
                    if row.get('_id'):
                        cursor.execute('SELECT ' + ','.join('`' + key + '`' for key in self.columns(spec)) + f' FROM `{spec["table"]}` WHERE `{spec["pk"]}`=%s', (row['_id'],))
                        existing = cursor.fetchone()
                        if not existing:
                            raise AdminError(f'Record {row["_id"]} was not found. Existing IDs are never inferred from names.')
                        row['_revision'] = record_revision(existing)
                return rows
            finally:
                cursor.close()

    def apply_import(self, cursor, resource, rows):
        spec = RESOURCES[resource]
        for index, row in enumerate(rows, 1):
            values = validate_record(spec, {field['key']: row.get(field['key'], '') for field in spec['fields']})
            self.validate_links(cursor, resource, values)
            if row.get('_id'):
                cursor.execute('SELECT ' + ','.join('`' + key + '`' for key in self.columns(spec)) + f' FROM `{spec["table"]}` WHERE `{spec["pk"]}`=%s FOR UPDATE', (row['_id'],))
                old = cursor.fetchone()
                if not old or record_revision(old) != row.get('_revision'):
                    raise AdminError(f'Row {index}: record changed since extraction. Nothing in this import was saved.', 409)
                if spec['pk'] == 'class' and values['class'] != row['_id']:
                    raise AdminError('Class mappings cannot be renamed during import.')
                cursor.execute(f'UPDATE `{spec["table"]}` SET ' + ','.join(f'`{key}`=%s' for key in values) + f' WHERE `{spec["pk"]}`=%s', [*values.values(), row['_id']])
            else:
                cursor.execute(f'INSERT INTO `{spec["table"]}` (' + ','.join(f'`{key}`' for key in values) + ') VALUES (' + ','.join('%s' for _ in values) + ')', list(values.values()))

    def system(self, revision=None, enable=False):
        with self.connection() as conn:
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute("SELECT value FROM system_settings WHERE `key`='chatbot_enabled'" + (' FOR UPDATE' if enable else ''))
                row = cursor.fetchone()
                current = record_revision(row or {})
                if enable:
                    if current != revision:
                        raise AdminError('System status changed. Reload first.', 409)
                    cursor.execute("INSERT INTO system_settings (`key`,value) VALUES ('chatbot_enabled','true') ON DUPLICATE KEY UPDATE value='true'")
                    cursor.execute("INSERT INTO system_logs (action, performed_by) VALUES ('enable', NULL)")
                    conn.commit()
                    row = dict(value='true')
                cursor.execute('SELECT action, timestamp FROM system_logs ORDER BY log_id DESC LIMIT 10')
                logs = [{key: json_value(value) for key, value in item.items()} for item in cursor.fetchall()]
                return dict(enabled=bool(row and row['value'] == 'true'), revision=record_revision(row or {}), logs=logs)
            finally:
                cursor.close()

    def phrase(self, record_id, revision, action, actor):
        from nlp_helpers import refresh_phrase_cache
        with self.connection() as conn:
            cursor = conn.cursor(dictionary=True)
            try:
                # Serialise approval/check against the live phrase set, not a stale browser result.
                cursor.execute('SELECT id FROM intent_phrases ORDER BY id FOR UPDATE')
                cursor.fetchall()
                spec = RESOURCES['phrases']
                cursor.execute('SELECT ' + ','.join('`' + key + '`' for key in self.columns(spec)) + ' FROM learned_phrases WHERE id=%s FOR UPDATE', (record_id,))
                row = cursor.fetchone()
                if not row or record_revision(row) != revision or row['applied']:
                    raise AdminError('This candidate changed or was already resolved. Refresh the queue.', 409)
                if action == 'dismiss':
                    cursor.execute('DELETE FROM learned_phrases WHERE id=%s', (record_id,))
                else:
                    refresh_phrase_cache(force=True)
                    status, reason = phrase_safety(row['phrase_text'], row['resolved_intent'])
                    if action == 'check':
                        return dict(status=status, reason=reason)
                    if status != 'safe':
                        raise AdminError('Approval blocked: ' + reason, 409)
                    cursor.execute('SELECT id FROM intent_phrases WHERE intent_name=%s AND phrase=%s', (row['resolved_intent'], row['phrase_text']))
                    if not cursor.fetchone():
                        cursor.execute("INSERT INTO intent_phrases (intent_name, phrase, source, added_by) VALUES (%s,%s,'learned',%s)", (row['resolved_intent'], row['phrase_text'], actor))
                    cursor.execute('UPDATE learned_phrases SET applied=1 WHERE id=%s', (record_id,))
                conn.commit()
                refresh_phrase_cache(force=True)
                return dict(ok=True)
            finally:
                cursor.close()

    def manual_phrase(self, phrase, intent, actor, approve=False):
        from nlp_helpers import refresh_phrase_cache
        with self.connection() as conn:
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute('SELECT id FROM intent_phrases ORDER BY id FOR UPDATE')
                cursor.fetchall()
                refresh_phrase_cache(force=True)
                status, reason = phrase_safety(phrase, intent)
                if not approve:
                    return dict(status=status, reason=reason)
                if status != 'safe':
                    raise AdminError('Approval blocked: ' + reason, 409)
                cursor.execute('SELECT id FROM intent_phrases WHERE intent_name=%s AND phrase=%s', (intent, phrase))
                if not cursor.fetchone():
                    cursor.execute("INSERT INTO intent_phrases (intent_name,phrase,source,added_by) VALUES (%s,%s,'manual',%s)", (intent, phrase, actor))
                conn.commit()
                refresh_phrase_cache(force=True)
                return dict(ok=True)
            finally:
                cursor.close()

    def traffic_review(self, view='all'):
        from datetime import timedelta, timezone
        from admin_review import project
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        with self.connection() as conn:
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute('''SELECT id,created_at,question_text,lane,intent,nlp_score,likely_miss,completed,rating
                    FROM query_log WHERE created_at >= %s AND created_at <= %s
                    AND question_text IS NOT NULL AND COALESCE(intent,'') NOT LIKE '%%complaint%%'
                    ORDER BY created_at DESC,id DESC LIMIT 10001''', (now - timedelta(days=14), now))
                events = cursor.fetchall()
                cursor.execute('SELECT review_key,fingerprint FROM admin_review_resolutions')
                resolutions = {row['review_key']: row['fingerprint'] for row in cursor.fetchall()}
                result = project(events[:10000], resolutions, now, view)
                result['sample_limited'] = len(events) > 10000
                return result
            finally:
                cursor.close()

    def mark_reviewed(self, key, revision):
        rows = self.traffic_review()['rows']
        row = next((row for row in rows if row['key'] == key), None)
        if not row or not isinstance(revision, str) or not hmac.compare_digest(row['revision'], revision):
            raise AdminError('The review evidence changed or was already reviewed. Refresh first.', 409)
        with self.connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('SELECT review_key FROM admin_review_resolutions WHERE review_key=%s', (key,))
                if cursor.fetchone():
                    cursor.execute('UPDATE admin_review_resolutions SET fingerprint=%s,updated_at=CURRENT_TIMESTAMP WHERE review_key=%s', (revision, key))
                else:
                    cursor.execute('INSERT INTO admin_review_resolutions(review_key,fingerprint) VALUES(%s,%s)', (key, revision))
                conn.commit()
            finally:
                cursor.close()
        return dict(ok=True)

    def append_review_answer(self, topic, answer, version):
        current = self.almanac()
        if current['version'] != version:
            raise AdminError('The almanac changed. Reload before adding this answer.', 409)
        content = current['content'].rstrip() + '\n\n' + topic + '\n' + answer + '\n'
        if len(content) > 500000:
            raise AdminError('The almanac exceeds the editor limit.')
        if not self.save_almanac(content, version):
            raise AdminError('The almanac changed. Reload before adding this answer.', 409)
        return dict(ok=True, version=version + 1)

    def suggestion(self, record_id, revision, topic=None, answer=None):
        with self.connection() as conn:
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute('SELECT id,question_text,ask_count,last_asked FROM unanswered_questions WHERE id=%s FOR UPDATE', (record_id,))
                row = cursor.fetchone()
                if not row or record_revision(row) != revision:
                    raise AdminError('This question changed or was already reviewed. Refresh the queue.', 409)
                if answer is not None:
                    cursor.execute('SELECT content FROM school_almanac WHERE id=1 FOR UPDATE')
                    almanac = cursor.fetchone()
                    if not almanac:
                        raise AdminError('Seed the school almanac before adding verified information.', 409)
                    content = almanac['content'].rstrip() + '\n\n' + topic + '\n' + answer + '\n'
                    if len(content) > 500000:
                        raise AdminError('The almanac exceeds the editor limit. Organise it before appending more information.')
                    cursor.execute('UPDATE school_almanac SET content=%s,version=version+1 WHERE id=1', (content,))
                cursor.execute('DELETE FROM unanswered_questions WHERE id=%s', (record_id,))
                conn.commit()
                return dict(ok=True)
            finally:
                cursor.close()


def phrase_safety(phrase, intent):
    from nlp_helpers import check_phrase_safety, INTENT_DATA, ALWAYS_SCORED_INTENTS
    from routing_contract import ROLE_PERSONAL_INTENTS
    if intent not in INTENT_DATA or not isinstance(phrase, str) or not phrase.strip() or len(phrase) > 500:
        raise AdminError('Invalid phrase or intent.')
    if intent in ALWAYS_SCORED_INTENTS:
        raise AdminError('Greeting, thanks and help use the deliberate whole-message allowlist. They cannot be changed through phrase approval.')
    groups = [set(intents) | ALWAYS_SCORED_INTENTS for intents in ROLE_PERSONAL_INTENTS.values() if intent in intents]
    if not groups:
        raise AdminError('No active role routing group exists for this intent. Review it in code first.')
    same = {other for group in groups for other in group if other != intent}
    return check_phrase_safety(phrase, intent, same, groups)


def create_app(test_config=None, repository=None, document_store=None):
    app = Flask(__name__, static_folder=None)
    hosted = os.getenv("DASHBOARD_HOSTED") == "true" or os.getenv("RENDER") == "true"
    app.config.update(SECRET_KEY=os.getenv("DASHBOARD_SESSION_SECRET"),
                      ADMIN_READ_ONLY=os.getenv("DASHBOARD_READ_ONLY", "false").lower() == "true",
                      ADMIN_LIVE_DATA=os.getenv("DASHBOARD_LIVE_DATA", "false").lower() == "true",
                      ADMIN_USERNAME=os.getenv("DASHBOARD_ADMIN_USERNAME"),
                      ADMIN_PASSWORD_HASH=os.getenv("DASHBOARD_ADMIN_PASSWORD_HASH"),
                      SESSION_COOKIE_NAME="yara_admin_session", SESSION_COOKIE_HTTPONLY=True,
                      SESSION_COOKIE_SAMESITE="Strict", SESSION_COOKIE_SECURE=hosted,
                      MAX_CONTENT_LENGTH=8 * 1024 * 1024 + 128 * 1024)
    if test_config:
        app.config.update(test_config)
    if not all(app.config.get(key) for key in ["SECRET_KEY", "ADMIN_USERNAME", "ADMIN_PASSWORD_HASH"]):
        raise RuntimeError("Configure DASHBOARD_SESSION_SECRET, DASHBOARD_ADMIN_USERNAME and DASHBOARD_ADMIN_PASSWORD_HASH.")
    if len(app.config["SECRET_KEY"]) < 32:
        raise RuntimeError("DASHBOARD_SESSION_SECRET must contain at least 32 characters.")
    if hosted:
        from start_dashboard import validate_environment
        validate_environment(os.environ, independent_api=True)
    repo = repository or MySQLRepository()
    repo.read_only = app.config['ADMIN_READ_ONLY']
    from school_documents import DocumentStore, DocumentError
    documents = document_store or DocumentStore(record_publisher=repo.apply_import if hasattr(repo, 'apply_import') else None)
    sessions, attempts = {}, defaultdict(deque)
    lock = threading.Lock()
    import_gate = threading.BoundedSemaphore(1)
    app.extensions["admin_sessions"] = sessions

    def current_admin():
        now = time.monotonic()
        with lock:
            for token, info in list(sessions.items()):
                if now - info["seen"] > IDLE_SECONDS or now - info["created"] > SESSION_SECONDS:
                    sessions.pop(token, None)
            info = sessions.get(session.get("admin_id"))
            if info:
                info["seen"] = now
            return info

    def protected(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            if not current_admin():
                raise AdminError("Your session has ended. Please sign in again.", 401)
            # Historical stores predate complaint/PII exclusions. Do not expose
            # their raw text in production; Phase 3 uses content-free telemetry.
            legacy_text = (request.path in {'/api/records/suggestions', '/api/records/phrases'}
                           or request.path.startswith('/api/suggestions/')
                           or (request.path.startswith('/api/phrases/')
                               and not request.path.startswith('/api/phrases/manual/')))
            if legacy_text and not app.testing:
                raise AdminError('Historical raw-text review is quarantined. Privacy-safe traffic review will be enabled separately.', 403)
            return function(*args, **kwargs)
        return wrapped

    @app.before_request
    def csrf_guard():
        if (app.config['ADMIN_READ_ONLY'] and request.path.startswith('/api/')
                and request.method not in {'GET', 'HEAD', 'OPTIONS'}
                and request.path not in {'/api/login', '/api/logout'}):
            raise AdminError('Read-only validation mode: school data changes are disabled.', 403)
        if request.path.startswith("/api/") and request.method not in {"GET", "HEAD", "OPTIONS"}:
            supplied = request.headers.get("X-CSRF-Token", "")
            expected = session.get("csrf", "")
            if not supplied or not expected or not hmac.compare_digest(supplied, expected):
                raise AdminError("Security check failed. Reload this page and try again.", 403)

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(AdminError)
    def admin_error(error):
        return jsonify(error=str(error)), error.status

    @app.errorhandler(DocumentError)
    def document_error(error):
        return jsonify(error=str(error)), error.status

    @app.errorhandler(mysql.connector.Error)
    def database_error(error):
        app.logger.warning("Admin database operation failed (%s)", type(error).__name__)
        status = 409 if isinstance(error, mysql.connector.IntegrityError) else 503
        return jsonify(error="This conflicts with an existing or linked record." if status == 409 else
                       "The school database is unavailable. Nothing was saved. Please try again."), status

    @app.errorhandler(413)
    def too_large(_error):
        return jsonify(error="This upload exceeds the 8 MB limit."), 413

    @app.errorhandler(Exception)
    def unexpected_error(error):
        if isinstance(error, HTTPException):
            return jsonify(error=error.description), error.code
        app.logger.warning("Admin operation failed (%s)", type(error).__name__)
        return jsonify(error="This operation could not be completed. Please retry or contact your administrator."), 500

    @app.get("/healthz")
    def health():
        return jsonify(status="ok")

    @app.get("/api/session")
    def get_session():
        session.setdefault("csrf", secrets.token_urlsafe(32))
        info = current_admin()
        return jsonify(authenticated=bool(info), username=app.config["ADMIN_USERNAME"] if info else None,
                       csrf=session["csrf"], idle_minutes=IDLE_SECONDS // 60,
                       read_only=app.config['ADMIN_READ_ONLY'])

    @app.post("/api/login")
    def login():
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict) or not isinstance(data.get("username"), str) or not isinstance(data.get("password"), str):
            raise AdminError("Enter your username and password.")
        now, address = time.monotonic(), request.remote_addr
        with lock:
            for ip in list(attempts):
                while attempts[ip] and now - attempts[ip][0] > 300:
                    attempts[ip].popleft()
                if not attempts[ip]:
                    attempts.pop(ip, None)
            if len(attempts) >= 10000 or len(attempts[address]) >= 5:
                raise AdminError("Too many sign-in attempts. Try again in five minutes.", 429)
            attempts[address].append(now)
        valid = verify_password(data["password"], app.config["ADMIN_PASSWORD_HASH"])
        if data["username"] != app.config["ADMIN_USERNAME"] or not valid:
            raise AdminError("Incorrect username or password.", 401)
        with lock:
            attempts.pop(address, None)
            sessions.pop(session.get("admin_id"), None)
            if len(sessions) >= 1000:
                raise AdminError("Too many active sessions. Please try later.", 503)
            token = secrets.token_urlsafe(32)
            sessions[token] = dict(created=now, seen=now)
        session.clear()
        session.update(admin_id=token, csrf=secrets.token_urlsafe(32))
        return jsonify(username=app.config["ADMIN_USERNAME"], csrf=session["csrf"])

    @app.post("/api/logout")
    def logout():
        with lock:
            sessions.pop(session.get("admin_id"), None)
        session.clear()
        return jsonify(ok=True)

    @app.get("/api/overview")
    @protected
    def overview():
        return jsonify(repo.overview())

    @app.get("/api/catalog")
    @protected
    def catalog():
        return jsonify(legacy_review_available=app.testing, read_only=app.config['ADMIN_READ_ONLY'],
                       live_data=app.config['ADMIN_LIVE_DATA'],
                       resources={key: {"title": spec["title"], "pk": spec["pk"], "fields": spec["fields"],
                                         "editable": not app.config['ADMIN_READ_ONLY'] and not spec.get("readonly", False)} for key, spec in RESOURCES.items()})

    @app.get("/api/student-classes")
    @protected
    def student_classes():
        return jsonify(classes=repo.student_classes())

    @app.get("/api/records/<resource>")
    @protected
    def records(resource):
        if resource not in RESOURCES:
            raise AdminError("Unknown record type.", 404)
        try:
            page, size = int(request.args.get("page", 1)), int(request.args.get("size", 25))
            if page < 1 or size not in {25, 50, 100}:
                raise ValueError
        except ValueError:
            raise AdminError("Invalid page or page size.") from None
        search = request.args.get("q", "").strip()[:200]
        grade = request.args.get("grade", "")
        class_filter = request.args.get("class", "")
        if grade or class_filter:
            if resource not in CLASS_RESOURCES or (grade and grade not in {str(n) for n in range(1, 13)}) or len(class_filter) > 30:
                raise AdminError("Invalid grade or class filter.")
            return jsonify(repo.records(resource, search, page, size, grade, class_filter))
        return jsonify(repo.records(resource, search, page, size))

    @app.get('/api/record-classes/<resource>')
    @protected
    def record_classes(resource):
        if resource not in CLASS_RESOURCES:
            raise AdminError('This record type does not have class filters.', 400)
        return jsonify(classes=repo.record_classes(resource))

    @app.route("/api/records/<resource>", methods=["POST"])
    @app.route("/api/records/<resource>/<record_id>", methods=["PUT", "DELETE"])
    @protected
    def write_record(resource, record_id=None):
        if resource not in RESOURCES:
            raise AdminError("Unknown record type.", 404)
        spec = RESOURCES[resource]
        if spec.get("readonly"):
            raise AdminError("Editing this record type is not available in this build.", 405)
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise AdminError("A record object is required.")
        delete = request.method == "DELETE"
        data = None if delete else validate_record(spec, payload.get("record"))
        if resource == 'accounts' and not delete:
            password = payload.get('new_password', '')
            if not isinstance(password, str) or len(password) > 512 or (password and len(password) < 12) or (record_id is None and not password):
                raise AdminError('New accounts need a password of at least 12 characters. Leave it blank on edit to keep the existing password.')
            if password:
                data['password_hash'] = hash_password(password)
        repo.save_record(resource, data, record_id, payload.get("revision"), delete)
        return jsonify(ok=True), 201 if request.method == "POST" else 200

    @app.get("/api/almanac")
    @protected
    def almanac():
        return jsonify(repo.almanac())

    @app.route('/api/relations/<kind>/<int:entity_id>', methods=['GET', 'PUT'])
    @protected
    def relationships(kind, entity_id):
        if kind not in {'parent-children', 'teacher-subjects'}:
            raise AdminError('Unknown relationship type.', 404)
        if request.method == 'GET':
            return jsonify(repo.relationship(kind, entity_id))
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or payload.get('confirmed') is not True:
            raise AdminError('Confirm this link replacement.')
        ids = payload.get('ids')
        if not isinstance(ids, list) or len(ids) > 1000 or any(type(value) is not int or value < 1 for value in ids) or len(ids) != len(set(ids)):
            raise AdminError('Use unique, positive record IDs (at most 1,000).')
        return jsonify(repo.relationship(kind, entity_id, sorted(ids), payload.get('revision')))

    @app.route('/api/system', methods=['GET', 'PUT'])
    @protected
    def system_status():
        if request.method == 'GET':
            return jsonify(repo.system())
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or payload.get('enable') is not True or payload.get('confirmed') is not True:
            raise AdminError('Only a confirmed re-enable is supported. Emergency disable remains with the principal.')
        return jsonify(repo.system(payload.get('revision'), enable=True))

    @app.post('/api/phrases/<int:record_id>/<action>')
    @protected
    def phrase_action(record_id, action):
        if action not in {'check', 'approve', 'dismiss'}:
            raise AdminError('Unknown phrase action.', 404)
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or (action != 'check' and payload.get('confirmed') is not True):
            raise AdminError('Confirm this phrase action.')
        return jsonify(repo.phrase(record_id, payload.get('revision'), action, app.config['ADMIN_USERNAME']))

    @app.get('/api/phrase-intents')
    @protected
    def phrase_intents():
        from routing_contract import ROLE_PERSONAL_INTENTS
        return jsonify(intents=sorted({intent for intents in ROLE_PERSONAL_INTENTS.values() for intent in intents}))

    @app.get('/api/review/traffic')
    @protected
    def review_traffic():
        view = request.args.get('view', 'phrases')
        if view not in {'phrases', 'knowledge'}:
            raise AdminError('Choose a phrase or knowledge review.', 400)
        return jsonify(repo.traffic_review(view))

    @app.post('/api/review/<key>/resolve')
    @protected
    def resolve_review(key):
        payload = request.get_json(silent=True)
        if (len(key) != 64 or any(char not in '0123456789abcdef' for char in key)
                or not isinstance(payload, dict) or payload.get('confirmed') is not True):
            raise AdminError('Confirm a valid review item.')
        return jsonify(repo.mark_reviewed(key, payload.get('revision')))

    @app.post('/api/review/almanac')
    @protected
    def review_almanac():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or payload.get('confirmed') is not True:
            raise AdminError('Confirm adding verified school information.')
        topic, answer, version = payload.get('topic'), payload.get('answer'), payload.get('version')
        if (not isinstance(topic, str) or not 1 <= len(topic.strip()) <= 150 or '\n' in topic or '\r' in topic
                or not isinstance(answer, str) or not 1 <= len(answer.strip()) <= 20000 or type(version) is not int):
            raise AdminError('Enter a topic, verified answer and current almanac version.')
        return jsonify(repo.append_review_answer(topic.strip(), answer.strip(), version))

    @app.post('/api/phrases/manual/<action>')
    @protected
    def manual_phrase(action):
        if action not in {'check', 'approve'}:
            raise AdminError('Unknown phrase action.', 404)
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or not isinstance(payload.get('phrase'), str) or not isinstance(payload.get('intent'), str):
            raise AdminError('Enter a phrase and select an intent.')
        if action == 'approve' and payload.get('confirmed') is not True:
            raise AdminError('Confirm this manual phrase approval.')
        phrase = payload['phrase'].strip().lower()
        return jsonify(repo.manual_phrase(phrase, payload['intent'], app.config['ADMIN_USERNAME'], action == 'approve'))

    @app.post('/api/suggestions/<int:record_id>/<action>')
    @protected
    def suggestion_action(record_id, action):
        payload = request.get_json(silent=True)
        if action not in {'append', 'dismiss'} or not isinstance(payload, dict) or payload.get('confirmed') is not True:
            raise AdminError('Confirm a valid question review action.')
        topic, answer = None, None
        if action == 'append':
            topic, answer = payload.get('topic'), payload.get('answer')
            if (not isinstance(topic, str) or not 1 <= len(topic.strip()) <= 150 or '\n' in topic or '\r' in topic
                    or not isinstance(answer, str) or not 1 <= len(answer.strip()) <= 20000):
                raise AdminError('Enter a single-line topic (1–150 characters) and a verified answer (1–20,000 characters).')
            topic, answer = topic.strip(), answer.strip()
        return jsonify(repo.suggestion(record_id, payload.get('revision'), topic, answer))

    @app.post("/api/imports/preview")
    @protected
    def preview_import():
        from school_imports import make_draft, ImportProblem
        upload = request.files.get("file")
        if not upload or not upload.filename:
            raise AdminError("Choose a school document to review.")
        if not import_gate.acquire(blocking=False):
            raise AdminError("Another document is being read. Please try again shortly.", 429)
        try:
            kind = request.form.get('kind', '')
            content = upload.read()
            if kind.startswith('records/'):
                from record_imports import make_record_draft
                draft = make_record_draft(kind, upload.filename, content)
                draft['rows'] = repo.prepare_import(kind.partition('/')[2], draft['rows'])
                return jsonify(draft)
            return jsonify(make_draft(kind, upload.filename, content))
        except ImportProblem as error:
            raise AdminError(str(error)) from None
        except (ValueError, OSError, KeyError):
            raise AdminError("This document could not be read. Check its format or upload the original file.") from None
        finally:
            import_gate.release()

    @app.get("/api/imports")
    @protected
    def list_imports():
        return jsonify(documents=documents.list())

    @app.get("/api/imports/<document_id>")
    @protected
    def get_import(document_id):
        return jsonify(documents.get(document_id))

    @app.post("/api/imports")
    @app.put("/api/imports/<document_id>")
    @protected
    def save_import(document_id=None):
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise AdminError("A reviewed draft is required.")
        return jsonify(documents.save(payload.get("document"), app.config["ADMIN_USERNAME"], document_id, payload.get("revision")))

    @app.post("/api/imports/<document_id>/<action>")
    @protected
    def transition_import(document_id, action):
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or payload.get("confirmed") is not True:
            raise AdminError("Confirm that you reviewed this document and its scope.")
        return jsonify(documents.transition(document_id, action, payload.get("revision"), payload.get("publication_version"), app.config["ADMIN_USERNAME"]))

    @app.put("/api/almanac")
    @protected
    def edit_almanac():
        payload = request.get_json(silent=True) or {}
        if (not isinstance(payload, dict) or not isinstance(payload.get("content"), str)
                or not payload["content"].strip() or len(payload["content"]) > 500000
                or type(payload.get("version")) is not int):
            raise AdminError("Content and the current almanac version are required.")
        if not repo.save_almanac(payload["content"], payload["version"]):
            raise AdminError("The almanac changed. Reload it before saving your edit.", 409)
        return jsonify(ok=True, version=payload["version"] + 1)

    @app.get("/")
    @app.get("/<path:path>")
    def frontend(path=""):
        if path.startswith("api/"):
            raise AdminError("Unknown endpoint.", 404)
        if not DIST.is_dir():
            return "Build the dashboard frontend with npm run build in admin_frontend first.", 503
        if path and (DIST / path).is_file():
            return send_from_directory(DIST, path)
        if path.startswith("assets/"):
            return "Not found", 404
        return send_from_directory(DIST, "index.html")

    return app
