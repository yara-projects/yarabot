"""Content-free, fail-open chat telemetry and session-owned feedback.

Never persist input/answer text. question_text is a fixed topic label, not a
redacted copy of user input. Rephrases are approximate same-topic signals.
"""
import hashlib
import hmac
import re
import secrets

from flask import g, jsonify, request, session, stream_with_context

from log_privacy import exclude_complaint_text, safe_log


SCHEMA = """
CREATE TABLE IF NOT EXISTS query_log (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    role VARCHAR(24) NOT NULL,
    class_group VARCHAR(12) NULL,
    question_text VARCHAR(160) NULL,
    lane ENUM('nlp','classifier','gemini','fallback','clarification') NOT NULL,
    intent VARCHAR(80) NULL,
    nlp_score FLOAT NULL,
    answer_id CHAR(32) NOT NULL UNIQUE,
    owner_hash CHAR(64) NOT NULL,
    likely_miss BOOLEAN NOT NULL DEFAULT FALSE,
    rephrase_of CHAR(32) NULL,
    completed BOOLEAN NOT NULL DEFAULT FALSE,
    rating ENUM('up','down') NULL,
    reason ENUM('wrong answer','didn''t understand','too long') NULL,
    rated_at DATETIME NULL,
    INDEX traffic_week (created_at),
    INDEX traffic_owner (owner_hash, rated_at)
)
"""
ROLES = {'student', 'parent', 'guest', 'teacher', 'hod', 'vice_principal',
         'assistant_principal', 'principal'}
TOPICS = {
    'attendance': r'\b(?:attendance|absent|absence)\b',
    'fees': r'\b(?:fees?|paid|unpaid|payment)\b',
    'timetable': r'\b(?:timetable|schedule|periods?)\b',
    'exams': r'\b(?:exams?|examinations?|results)\b',
    'syllabus': r'\b(?:syllabus|portions?|curriculum)\b',
    'directory': r'\b(?:teacher|staff|department|hod)\b',
    'admissions': r'\badmissions?\b',
    'uniform': r'\buniform\b',
    'contact': r'\b(?:address|phone|contact|location)\b',
    'school hours': r'\b(?:hours|timings?|arrival)\b',
    'notices': r'\b(?:notices?|circulars?|events?)\b',
    'transport': r'\b(?:bus|transport)\b',
}


def topic_summary(text):
    """Output vocabulary is entirely static; never echo unmatched input."""
    return ', '.join(key for key, pattern in TOPICS.items()
                     if re.search(pattern, text, re.I)) or 'other'


def database(operation):
    import mysql.connector
    from config import DB_CONFIG
    connection = mysql.connector.connect(**dict(DB_CONFIG, connection_timeout=2))
    try:
        cursor = connection.cursor(dictionary=True)
        try:
            result = operation(cursor)
            connection.commit()
            return result
        finally:
            cursor.close()
    finally:
        connection.close()


def migrate():
    database(lambda cursor: cursor.execute(SCHEMA))


def save_event(event, previous=None):
    def write(cursor):
        # A bounded purge also removes feedback with its owning event.
        cursor.execute('DELETE FROM query_log WHERE created_at < UTC_TIMESTAMP() - INTERVAL 30 DAY LIMIT 1000')
        rephrase = None
        if previous and event['question_text'] not in (None, 'other'):
            cursor.execute('''SELECT answer_id FROM query_log WHERE answer_id=%s
                AND owner_hash=%s AND completed=TRUE AND question_text=%s
                AND created_at >= UTC_TIMESTAMP() - INTERVAL 30 SECOND''',
                (previous, event['owner_hash'], event['question_text']))
            if cursor.fetchone():
                rephrase = previous
                cursor.execute('UPDATE query_log SET likely_miss=TRUE WHERE answer_id=%s', (previous,))
        columns = tuple(event) + ('rephrase_of',)
        cursor.execute('INSERT INTO query_log (' + ','.join(columns) + ') VALUES ('
                       + ','.join(['%s'] * len(columns)) + ')', tuple(event.values()) + (rephrase,))
    database(write)


def record_safely(event, previous=None):
    try:
        save_event(event, previous)
    except Exception as error:
        safe_log('[TRAFFIC LOG SKIPPED] ' + type(error).__name__)


def register_feedback(app):
    @app.before_request
    def start_traffic():
        if request.path != '/api/chat':
            return
        body = request.get_json(silent=True)
        if isinstance(body, dict) and isinstance(body.get('message'), str):
            exclude_complaint_text(body['message'])
        else:
            exclude_complaint_text()
        session.setdefault('feedback_nonce', secrets.token_hex(32))
        session.setdefault('feedback_csrf', secrets.token_hex(32))
        secret = str(app.secret_key).encode()
        owner = hmac.new(secret, session['feedback_nonce'].encode(), hashlib.sha256).hexdigest()
        g.traffic = dict(role=session.get('role') if session.get('role') in ROLES else 'guest',
                         class_group=None, question_text=None, lane='fallback', intent=None,
                         nlp_score=None, answer_id=secrets.token_hex(16), owner_hash=owner,
                         completed=False)
        g.traffic_previous = session.get('feedback_previous')

    def finish_traffic(response):
        if not g.get('traffic'):
            return response
        event = dict(g.traffic)
        data = request.get_json(silent=True) or {}
        question = data.get('message', '') if isinstance(data, dict) else ''
        question = question if isinstance(question, str) else ''
        sensitive = exclude_complaint_text(question, event['intent'])
        # No complaint text, topic, grade, score or previous-turn association.
        if sensitive:
            event.update(question_text=None, intent='complaint_feedback', nlp_score=None)
        else:
            event['question_text'] = topic_summary(question)
        previous = None if sensitive else g.get('traffic_previous')
        if response.status_code != 200:
            event['lane'] = 'fallback'
        payload = response.get_json(silent=True) if response.is_json else None
        payload = payload if isinstance(payload, dict) else None
        eligible = ('user_id' in session and response.status_code == 200
                    and not sensitive and not (payload or {}).get('disabled'))
        if eligible:
            response.headers['X-Answer-ID'] = event['answer_id']
            response.headers['X-Feedback-CSRF'] = session['feedback_csrf']
            session['feedback_previous'] = event['answer_id']
        else:
            session.pop('feedback_previous', None)
        if response.mimetype == 'text/event-stream':
            original = response.response

            @stream_with_context
            def tracked():
                saved = False
                try:
                    for chunk in original:
                        if 'data: [DONE]' in (chunk.decode() if isinstance(chunk, bytes) else chunk):
                            event['completed'] = True
                            record_safely(event, previous)
                            saved = True
                        yield chunk
                finally:
                    if not saved:
                        record_safely(event, previous)
                    close = getattr(original, 'close', None)
                    if close:
                        close()
            response.response = tracked()
        else:
            event['completed'] = response.status_code == 200 and bool((payload or {}).get('reply'))
            if (payload or {}).get('choices'):
                event['lane'] = 'clarification'
            record_safely(event, previous)
        return response

    @app.after_request
    def fail_open_traffic(response):
        try:
            return finish_traffic(response)
        except Exception as error:
            safe_log('[TRAFFIC LOG SKIPPED] ' + type(error).__name__)
            return response

    @app.post('/api/feedback')
    def feedback():
        if 'user_id' not in session:
            return jsonify(error='Sign in first.'), 401
        csrf = session.get('feedback_csrf', '')
        if not csrf or not hmac.compare_digest(csrf, request.headers.get('X-Feedback-CSRF', '')):
            return jsonify(error='Refresh and try again.'), 403
        origin = request.headers.get('Origin')
        if origin and origin.rstrip('/') != request.host_url.rstrip('/'):
            return jsonify(error='Invalid origin.'), 403
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(error='Invalid feedback.'), 400
        answer = data.get('answer_id')
        rating, reason = data.get('rating'), data.get('reason')
        if (not isinstance(answer, str) or not re.fullmatch('[0-9a-f]{32}', answer)
                or rating not in ('up', 'down')
                or reason not in (None, 'wrong answer', "didn't understand", 'too long')):
            return jsonify(error='Invalid feedback.'), 400
        owner = hmac.new(str(app.secret_key).encode(), session.get('feedback_nonce', '').encode(), hashlib.sha256).hexdigest()

        def rate(cursor):
            # Serialize concurrent votes from this anonymous session across workers.
            lock = 'feedback:' + owner[:50]
            cursor.execute('SELECT GET_LOCK(%s, 0) AS acquired', (lock,))
            if cursor.fetchone()['acquired'] != 1:
                return 429
            # database() commits before closing this dedicated connection;
            # closing releases GET_LOCK, so concurrent voters see the commit.
            cursor.execute('''SELECT COUNT(*) AS count FROM query_log WHERE owner_hash=%s
                AND rated_at >= UTC_TIMESTAMP() - INTERVAL 1 MINUTE''', (owner,))
            if cursor.fetchone()['count'] >= 5:
                return 429
            cursor.execute('''UPDATE query_log SET rating=%s, reason=%s, rated_at=UTC_TIMESTAMP()
                WHERE answer_id=%s AND owner_hash=%s AND rating IS NULL AND completed=TRUE
                AND question_text IS NOT NULL AND created_at >= UTC_TIMESTAMP() - INTERVAL 30 DAY''',
                (rating, reason, answer, owner))
            return 200 if cursor.rowcount == 1 else 409
        try:
            status = database(rate)
        except Exception as error:
            safe_log('[FEEDBACK UNAVAILABLE] ' + type(error).__name__)
            return jsonify(error='Feedback is temporarily unavailable. Your chat is unaffected.'), 503
        return jsonify(ok=status == 200), status
