"""Privacy-safe review projections. Raw chat history is never an input source."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import math

from routing_contract import ROLE_PERSONAL_INTENTS
from traffic_feedback import TOPICS

SCHEMA = """
CREATE TABLE IF NOT EXISTS admin_review_resolutions (
    review_key CHAR(64) PRIMARY KEY,
    fingerprint CHAR(64) NOT NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""
INTENTS = {intent for group in ROLE_PERSONAL_INTENTS.values() for intent in group}
LANES = {'nlp', 'classifier', 'gemini', 'fallback', 'clarification'}


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def safe_topic(value):
    if not isinstance(value, str):
        return None
    if value == 'other':
        return value
    parts = value.split(', ')
    if not parts or len(set(parts)) != len(parts) or not set(parts) <= set(TOPICS):
        return None
    return ', '.join(topic for topic in TOPICS if topic in parts)


def timestamp(value):
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def project(events, resolutions, now=None, view='all'):
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff = now - timedelta(days=7)
    periods = [dict(requests=0, nlp=0, up=0, down=0, fallback=0),
               dict(requests=0, nlp=0, up=0, down=0, fallback=0)]
    groups = {}
    for event in events:
        topic = safe_topic(event.get('question_text'))
        raw_intent = event.get('intent')
        if not topic or (isinstance(raw_intent, str) and 'complaint' in raw_intent.lower()):
            continue
        created = timestamp(event.get('created_at'))
        lane = event.get('lane')
        if not created or not now - timedelta(days=14) <= created <= now or lane not in LANES:
            continue
        intent = raw_intent if isinstance(raw_intent, str) and raw_intent in INTENTS else 'unclassified'
        index = 0 if created >= cutoff else 1
        period = periods[index]
        period['requests'] += 1
        period['nlp'] += int(lane == 'nlp')
        period['up'] += int(event.get('rating') == 'up')
        period['down'] += int(event.get('rating') == 'down')
        period['fallback'] += int(lane == 'fallback')
        if index:
            continue
        key = fingerprint([topic, intent])
        group = groups.setdefault(key, dict(key=key, topic=topic, intent=intent, requests=0,
                                            up=0, down=0, fallback=0, repeats=0, near_misses=0,
                                            incomplete=0, latest_id=0))
        group['requests'] += 1
        group['up'] += int(event.get('rating') == 'up')
        group['down'] += int(event.get('rating') == 'down')
        group['fallback'] += int(lane == 'fallback')
        group['repeats'] += int(event.get('likely_miss') in (True, 1))
        group['incomplete'] += int(event.get('completed') not in (True, 1))
        score = event.get('nlp_score')
        group['near_misses'] += int(lane in {'gemini', 'fallback'} and isinstance(score, (int, float, Decimal))
                                    and math.isfinite(score) and 0 < score < 3)
        # Internal telemetry row IDs detect fresh evidence; never return them.
        if type(event.get('id')) is int:
            group['latest_id'] = max(group['latest_id'], event['id'])
    rows = []
    for group in groups.values():
        revision = fingerprint(group)
        if resolutions.get(group['key']) == revision:
            continue
        if view == 'phrases' and not (group['down'] or group['repeats'] or group['near_misses']):
            continue
        if view == 'knowledge' and not (group['fallback'] or group['down'] or group['incomplete']):
            continue
        rows.append({key: value for key, value in group.items() if key != 'latest_id'} | {'revision': revision})
    rows.sort(key=lambda row: (-row['down'], -row['fallback'], -row['repeats'], -row['requests'], row['topic']))
    for period in periods:
        total, votes = period['requests'], period['up'] + period['down']
        period['nlp_rate'] = round(100 * period['nlp'] / total, 1) if total else None
        period['up_rate'] = round(100 * period['up'] / votes, 1) if votes else None
        period['fallback_rate'] = round(100 * period['fallback'] / total, 1) if total else None
    return dict(current=periods[0], previous=periods[1], rows=rows if view == 'all' else rows[:100],
                more_groups=len(rows) > 100, window_days=7,
                definitions='UTC rolling weeks. Repeats are same-topic signals, not exact rephrases. Near-miss means Gemini/fallback with NLP score above 0 and below 3. Fallback is a routing signal, not proof that an answer was wrong.')
