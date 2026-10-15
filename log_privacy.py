"""Diagnostic logging never receives chat text; sensitive turns do not train logs."""

import re

from flask import g, has_request_context, request, session


_COMPLAINT_TEXT = re.compile(
    r'\b(?:complain\w*|bully\w*|harass\w*|abus\w*|unfair|mistreat\w*|'
    r'hit me|hits me|hitting me|threaten\w*|shout\w*|rude|punish\w*)\b', re.I)


def safe_log(message):
    """Callers supply metadata only. A broken stdout must not break a response."""
    try:
        print(message)
    except Exception:
        pass


def exclude_complaint_text(question='', intent=None, candidates=()):
    """Conservative exclusion, not a classifier or a general PII redactor."""
    excluded = str(intent or '').startswith('complaint') or any(
        str(name).startswith('complaint') for name in candidates)
    excluded = excluded or bool(_COMPLAINT_TEXT.search(question))
    if has_request_context():
        excluded = excluded or request.path.startswith(('/api/complaint', '/api/vp/complaint'))
        excluded = excluded or bool(g.get('exclude_complaint_text'))
        for key in ('conversation_context', 'pending_clarification', 'privacy_context'):
            context = session.get(key) or {}
            excluded = excluded or str(context.get('intent', context.get('kind', ''))).startswith('complaint')
        if excluded:
            g.exclude_complaint_text = True
    return excluded
