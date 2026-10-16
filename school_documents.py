"""Reviewed school documents. No schema creation, file writes or AI calls at runtime."""

from contextlib import contextmanager
from datetime import date, datetime
import hashlib
import json
import re
import uuid

import mysql.connector
from config import DB_CONFIG
from school_imports import DAYS, MAX_ROWS, subject_label


class DocumentError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


SCOPE_FIELDS = ("year", "grade", "division", "stream", "assessment", "audience", "teacher_id", "effective_from", "effective_to")
ROW_FIELDS = {
    "syllabus": ("subject", "section", "chapter", "topic"),
    "timetable": ("day", "period", "start", "end", "activity", "teacher", "class"),
    "teacher_timetable": ("day", "period", "start", "end", "activity", "teacher", "class"),
}


def checked_document(payload, approving=False):
    if isinstance(payload, dict) and isinstance(payload.get('kind'), str) and payload['kind'].startswith('records/'):
        return checked_records(payload, approving)
    if not isinstance(payload, dict) or payload.get("kind") not in ROW_FIELDS:
        raise DocumentError("Choose a supported document type.")
    kind = payload["kind"]
    scope = payload.get("scope")
    rows = payload.get("rows")
    if not isinstance(scope, dict) or set(scope) - set(SCOPE_FIELDS):
        raise DocumentError("Invalid document scope.")
    if not isinstance(rows, list) or not rows or len(rows) > MAX_ROWS:
        raise DocumentError("Include 1–1,000 reviewed entries.")
    scope = {key: scope.get(key, "") for key in SCOPE_FIELDS}
    if any(not isinstance(value, str) or len(value) > 80 for value in scope.values()):
        raise DocumentError("Scope values must be text of at most 80 characters.")
    scope = {key: value.strip() for key, value in scope.items()}
    scope["audience"] = scope["audience"] or "signed_in"
    if scope["audience"] != "signed_in":
        raise DocumentError("School documents currently require an authorised sign-in.")
    roman = {"VI": "6", "VII": "7", "VIII": "8", "IX": "9", "X": "10", "XI": "11", "XII": "12"}
    scope["grade"] = roman.get(scope["grade"].upper(), scope["grade"])
    scope["division"] = scope["division"].upper()
    from document_chat import assessment
    canonical = assessment(scope['assessment'])
    labels = {'term1': 'Term 1', 'term2': 'Term 2', 'ut1': 'UT 1', 'ut2': 'UT 2', 'wholeyear': 'Whole year'}
    scope['assessment'] = labels.get(canonical, scope['assessment'])
    if kind == 'teacher_timetable':
        # Teacher identity, not arbitrary class labels, defines this document's scope.
        scope['grade'] = scope['division'] = scope['stream'] = scope['assessment'] = ''
    elif kind == 'timetable':
        scope['assessment'] = scope['teacher_id'] = ''
    else:
        scope['teacher_id'] = ''
    if approving:
        year = re.fullmatch(r"(20\d{2})-(\d{2}|20\d{2})", scope["year"])
        if not year or int(year[2][-2:]) != (int(year[1]) + 1) % 100:
            raise DocumentError("Confirm the academic year, for example 2026-27.")
        if kind != "teacher_timetable" and not re.fullmatch(r"[1-9]|1[0-2]", scope["grade"]):
            raise DocumentError("Confirm a grade from 1 to 12.")
        if kind == "timetable" and not re.fullmatch(r"[A-Z]", scope["division"]):
            raise DocumentError("Confirm the class division separately from the stream or room code.")
        if kind == "syllabus" and not scope["assessment"]:
            raise DocumentError("Confirm the assessment, or use Whole year for the full syllabus.")
        if kind == "teacher_timetable" and not re.fullmatch(r"[1-9]\d*", scope["teacher_id"]):
            raise DocumentError("Link this timetable to the confirmed teacher ID; names are not guessed.")
        for key in ("effective_from", "effective_to"):
            try:
                if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', scope[key]):
                    raise ValueError
                date.fromisoformat(scope[key])
            except ValueError:
                raise DocumentError("Confirm both validity dates. Generated/printed dates are not effective dates.") from None
        if scope["effective_from"] > scope["effective_to"]:
            raise DocumentError("The end date must not precede the start date.")
    clean_rows = []
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict) or set(row) - set(ROW_FIELDS[kind]):
            raise DocumentError(f"Entry {index} has unexpected fields.")
        entry = {key: row.get(key, "") for key in ROW_FIELDS[kind]}
        if any(not isinstance(value, str) or len(value) > 10000 for value in entry.values()):
            raise DocumentError(f"Entry {index} contains invalid or oversized text.")
        entry = {key: value.strip().replace("\x00", "") for key, value in entry.items()}
        if approving:
            if kind == "syllabus":
                if not entry["subject"] or not entry["topic"]:
                    raise DocumentError(f"Entry {index} needs a subject and topic.")
                entry["subject"] = subject_label(entry["subject"])
            else:
                if entry["day"] not in DAYS.values() or not re.fullmatch(r"\d{1,2}|Break[ _-]?\d{1,2}", entry["period"], re.I):
                    raise DocumentError(f"Entry {index} needs a weekday and period (including 0 or Break 1).")
                if not entry["activity"] or (kind == "teacher_timetable" and not entry["class"]):
                    raise DocumentError(f"Entry {index} needs an activity and, for teachers, the class/division.")
                for key in ("start", "end"):
                    if entry[key] and not re.fullmatch(r"(?:[01]?\d|2[0-3]):[0-5]\d", entry[key]):
                        raise DocumentError(f"Entry {index}: confirm times in 24-hour HH:MM format, or leave both blank.")
                if bool(entry["start"]) != bool(entry["end"]) or (entry["start"] and entry["start"].zfill(5) >= entry["end"].zfill(5)):
                    raise DocumentError(f"Entry {index}: confirm a start time before the end time.")
        clean_rows.append(entry)
    title = payload.get("filename", "School document")
    source = payload.get("source_text", "")
    if not isinstance(title, str) or len(title) > 180 or not isinstance(source, str) or len(source) > 150000:
        raise DocumentError("Invalid document name or extracted source text.")
    return dict(kind=kind, scope=scope, rows=clean_rows, filename=title, source_text=source)


def checked_records(payload, approving=False):
    # Imported lazily: the independent admin module does not load the chatbot/AI.
    from admin_app import RESOURCES, validate_record, AdminError
    resource = payload['kind'].partition('/')[2]
    if resource not in {'students', 'parents', 'teachers', 'departments', 'subjects', 'exams', 'timetable', 'class-teachers', 'class-sections'}:
        raise DocumentError('This record type cannot be bulk imported.')
    spec = RESOURCES[resource]
    fields = {field['key'] for field in spec['fields']}
    rows = payload.get('rows')
    if not isinstance(rows, list) or not 1 <= len(rows) <= 1000:
        raise DocumentError('Include 1–1,000 reviewable record rows.')
    result = []
    seen = set()
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict) or set(row) - (fields | {'_id', '_revision'}):
            raise DocumentError(f'Row {index} has unexpected fields.')
        if any(not isinstance(value, str) or len(value) > 20000 for value in row.values()):
            raise DocumentError(f'Row {index} values must be bounded text.')
        record_id, revision = row.get('_id', '').strip(), row.get('_revision', '').strip()
        if record_id and (record_id in seen or not revision):
            raise DocumentError(f'Row {index}: duplicate ID or missing revision. Extract again to refresh existing records.')
        seen.add(record_id) if record_id else None
        values = {key: row.get(key, '') for key in fields}
        if approving:
            try:
                validate_record(spec, values)
            except AdminError as error:
                raise DocumentError(f'Row {index}: {error}') from None
        result.append({**values, '_id': record_id, '_revision': revision})
    name, source = payload.get('filename'), payload.get('source_text', '')
    if not isinstance(name, str) or not 1 <= len(name) <= 180 or not isinstance(source, str) or len(source) > 150000:
        raise DocumentError('Invalid record-import source.')
    return dict(kind=payload['kind'], scope={key: '' for key in SCOPE_FIELDS}, rows=result, filename=name, source_text=source)


def scope_key(document):
    # Dates are validity, not identity: a replacement must explicitly supersede the same scope.
    identity = {key: document["scope"][key].casefold() for key in SCOPE_FIELDS if not key.startswith("effective_")}
    return hashlib.sha256(json.dumps([document["kind"], identity], sort_keys=True).encode()).hexdigest()


class DocumentStore:
    def __init__(self, record_publisher=None):
        self.record_publisher = record_publisher

    @contextmanager
    def connection(self):
        conn = mysql.connector.connect(**{**DB_CONFIG, "connection_timeout": 8})
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def decode(row):
        body = json.loads(row["payload"])
        return {**body, **{key: value.isoformat() if isinstance(value, datetime) else value for key, value in row.items() if key != "payload"}}

    def list(self):
        with self.connection() as conn:
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute("SELECT document_id, status, revision, filename, updated_at FROM school_documents ORDER BY updated_at DESC LIMIT 100")
                return [{key: value.isoformat() if isinstance(value, datetime) else value for key, value in row.items()} for row in cursor.fetchall()]
            finally:
                cursor.close()

    def get(self, document_id):
        with self.connection() as conn:
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute("SELECT * FROM school_documents WHERE document_id=%s", (document_id,))
                row = cursor.fetchone()
                if not row:
                    raise DocumentError("This document no longer exists.", 404)
                result = self.decode(row)
                cursor.execute("SELECT version FROM school_document_heads WHERE scope_key=%s", (row["scope_key"],))
                head = cursor.fetchone()
                result["publication_version"] = head["version"] if head else 0
                return result
            finally:
                cursor.close()

    def save(self, payload, actor, document_id=None, revision=None):
        document = checked_document(payload)
        document_id = document_id or str(uuid.uuid4())
        key = scope_key(document)
        with self.connection() as conn:
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute("SELECT revision, status FROM school_documents WHERE document_id=%s FOR UPDATE", (document_id,))
                old = cursor.fetchone()
                if old:
                    if old["revision"] != revision:
                        raise DocumentError("This draft changed. Reload before saving.", 409)
                    if old["status"] not in {"draft", "approved"}:
                        raise DocumentError("Published/history records are immutable. Create a new draft to replace them.", 409)
                    cursor.execute("UPDATE school_documents SET payload=%s, filename=%s, scope_key=%s, status='draft', revision=revision+1, updated_by=%s WHERE document_id=%s",
                                   (json.dumps(document), document["filename"], key, actor, document_id))
                else:
                    if revision is not None:
                        raise DocumentError("The draft no longer exists.", 404)
                    cursor.execute("INSERT INTO school_documents (document_id, scope_key, filename, payload, updated_by) VALUES (%s,%s,%s,%s,%s)",
                                   (document_id, key, document["filename"], json.dumps(document), actor))
                conn.commit()
            finally:
                cursor.close()
        return self.get(document_id)

    def transition(self, document_id, action, revision, publication_version, actor):
        if action not in {"approve", "publish", "withdraw"} or type(revision) is not int:
            raise DocumentError("Choose an explicit approval/publication action and current revision.")
        with self.connection() as conn:
            cursor = conn.cursor(dictionary=True)
            try:
                # Head first on publishing/withdrawal: serialize all writers of the same scope.
                cursor.execute("SELECT scope_key FROM school_documents WHERE document_id=%s", (document_id,))
                initial = cursor.fetchone()
                if not initial:
                    raise DocumentError("Document not found.", 404)
                if action != "approve":
                    cursor.execute("INSERT IGNORE INTO school_document_heads (scope_key, version) VALUES (%s,0)", (initial["scope_key"],))
                    cursor.execute("SELECT * FROM school_document_heads WHERE scope_key=%s FOR UPDATE", (initial["scope_key"],))
                    head = cursor.fetchone()
                    if type(publication_version) is not int or head["version"] != publication_version:
                        raise DocumentError("The published version changed. Reload and review before replacing it.", 409)
                cursor.execute("SELECT * FROM school_documents WHERE document_id=%s FOR UPDATE", (document_id,))
                old = cursor.fetchone()
                if old["revision"] != revision or old["scope_key"] != initial["scope_key"]:
                    raise DocumentError("This document changed. Reload it first.", 409)
                expected = {"approve": "draft", "publish": "approved", "withdraw": "published"}[action]
                if old["status"] != expected:
                    raise DocumentError(f"Only a {expected} document can be {action}ed.", 409)
                checked_document(json.loads(old["payload"]), approving=True)
                if action == 'withdraw' and json.loads(old['payload'])['kind'].startswith('records/'):
                    raise DocumentError('Applied record edits cannot be undone by withdrawing an import. Review and publish a correction batch instead.', 409)
                if action == "publish":
                    document = json.loads(old['payload'])
                    if document['kind'].startswith('records/'):
                        if not self.record_publisher:
                            raise DocumentError('Record publication is not configured on this service.', 503)
                        self.record_publisher(cursor, document['kind'].partition('/')[2], document['rows'])
                    if head.get("document_id"):
                        cursor.execute("UPDATE school_documents SET status='superseded', revision=revision+1 WHERE document_id=%s", (head["document_id"],))
                    cursor.execute("UPDATE school_document_heads SET document_id=%s, version=version+1 WHERE scope_key=%s", (document_id, old["scope_key"]))
                elif action == "withdraw":
                    if head.get("document_id") != document_id:
                        raise DocumentError("This is not the current published version.", 409)
                    cursor.execute("UPDATE school_document_heads SET document_id=NULL, version=version+1 WHERE scope_key=%s", (old["scope_key"],))
                cursor.execute("UPDATE school_documents SET status=%s, revision=revision+1, updated_by=%s WHERE document_id=%s",
                               ({"approve": "approved", "publish": "published", "withdraw": "withdrawn"}[action], actor, document_id))
                conn.commit()
            finally:
                cursor.close()
        return self.get(document_id)

    def published(self, kind, today=None):
        today = today or date.today().isoformat()
        try:
            with self.connection() as conn:
                cursor = conn.cursor(dictionary=True)
                try:
                    cursor.execute("SELECT d.document_id,d.revision,d.filename,JSON_REMOVE(d.payload,'$.source_text') AS payload FROM school_documents d JOIN school_document_heads h ON h.document_id=d.document_id WHERE d.status='published' AND JSON_UNQUOTE(JSON_EXTRACT(d.payload,'$.kind'))=%s LIMIT 501", (kind,))
                    result = [self.decode(row) for row in cursor.fetchall()]
                    if len(result) > 500:
                        raise DocumentError('Too many active school documents. Archive obsolete scopes before retrieving this collection.', 503)
                finally:
                    cursor.close()
            return [item for item in result if item["kind"] == kind and item["scope"]["effective_from"] <= today <= item["scope"]["effective_to"]]
        except mysql.connector.Error as error:
            if error.errno == 1146:  # Additive migration not installed. Never pretend drafts are published.
                return []
            raise
