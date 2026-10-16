"""Published-only retrieval and data-driven document clarification.

Identity comes from authenticated server records. It is never inferred from names,
division letters, typed authority or document instructions.
"""

from datetime import datetime, timedelta
import re
import time
from zoneinfo import ZoneInfo

from chat_choices import offer
from chat_tables import data_table, cell
from school_imports import DAYS, subject_label


TTL = 600


def assessment(value):
    value = value.casefold().strip()
    value = re.sub(r"\bii\b", "2", re.sub(r"\bi\b", "1", value))
    value = re.sub(r"unit\s*test", "ut", value)
    return re.sub(r"\W+", "", value)


def visible(document, identity):
    scope, role = document["scope"], identity["role"]
    if role == "guest":
        return False
    if document["kind"] == "teacher_timetable":
        return role in {"teacher", "hod", "vice_principal", "principal", "assistant_principal", "admin"} and str(identity.get("teacher_id")) == scope["teacher_id"]
    classes = identity.get("classes", [])
    if role in {"student", "parent"}:
        return any(cls.split("-")[0] == scope["grade"] and (not scope["division"] or cls == f"{scope['grade']}-{scope['division']}") for cls in classes)
    return role in {"teacher", "hod", "vice_principal", "principal", "assistant_principal", "admin"}


def document_grid(rows, teacher=False):
    days = sorted({row["day"] for row in rows}, key=lambda day: list(DAYS.values()).index(day))
    periods = list(dict.fromkeys(row['period'] for row in rows))
    if all(any(row['period'] == period and row['start'] for row in rows) for period in periods):
        periods.sort(key=lambda period: min(row['start'].zfill(5) for row in rows if row['period'] == period and row['start']))
    elif all(period.isdigit() for period in periods):
        periods.sort(key=int)
    # With incomplete times and named breaks, retain the reviewed source order.
    headers = []
    for period in periods:
        times = sorted({f"{row['start']}–{row['end']}" for row in rows if row["period"] == period and row["start"] and row["end"]})
        headers.append(f"{'Period ' if period.isdigit() else ''}{period}" + ("\n" + " / ".join(times) if times else ""))
    values = []
    for day in days:
        cells = []
        for period in periods:
            entries = [row for row in rows if row["day"] == day and row["period"] == period]
            labels = [f"{row['class']} · {row['activity']}" if teacher else row["activity"] for row in entries]
            cells.append(" / ".join(dict.fromkeys(labels)) or "—")
        values.append([day, *cells])
    return data_table(["Day", *headers], values) + "\n\n— means no entry was returned, not a confirmed free period. Optional subjects are shown together; choose your own option."


def respond(question, state, owner, identity_loader, store, selection=None):
    q = question.casefold().strip()
    previous = state.get("document_context") or {}
    if time.time() > previous.get("expires", 0):
        previous = {}
    syllabus = bool(re.search(r"\b(?:syllabus|portions?|curriculum)\b", q))
    timetable = bool(re.search(r"\b(?:timetable|time table|schedule)\b", q)) and not re.search(r"\b(?:exam|test|event|meeting|bus)\b", q)
    if syllabus and timetable and not selection:
        parts = re.split(r'\s+(?:and|plus)\s+', question, maxsplit=1, flags=re.I)
        if len(parts) == 2 and all(bool(re.search(r'\b(?:syllabus|portions?|curriculum)\b', part, re.I)) != bool(re.search(r'\b(?:timetable|time table|schedule)\b', part, re.I)) for part in parts):
            replies, options = [], []
            for part in parts:
                component_state = {}
                result = respond(part, component_state, owner, identity_loader, store)
                if result is None:
                    break  # Named third-person targets still use the established router.
                replies.append(result['reply'])
                pending = component_state.get('chat_choices', {})
                options.extend((choice['label'], action) for choice, action in zip(result.get('choices', []), pending.get('options', [])))
            else:
                state.pop('document_context', None)
                result = dict(reply='\n\n'.join(replies))
                if options:
                    result['choices'] = offer(state, options, owner)
                return result
        if len(parts) == 2:
            return {'reply': 'You asked for both syllabus and timetable information. Which request should I handle first?',
                    'choices': offer(state, [(part, dict(message=part)) for part in parts], owner)}
        return {'reply': 'You asked for both syllabus and timetable information. Please ask for each separately so I can retain the right class, person and dates.'}
    day_words = '|'.join(name.casefold() for name in DAYS.values()) + '|today|tomorrow'
    own_timetable = bool(re.search(r'\b(?:my|mine|i|own)\b', q) or re.fullmatch(r'(?:show )?(?:the )?(?:timetable|schedule)\??', q)
                         or re.fullmatch(rf'(?:{day_words}) (?:timetable|schedule)\??', q))
    if timetable and not own_timetable and not re.search(r'\b(?:1[0-2]|[1-9])\s*[- ]?\s*[a-h]\b', q) and not previous:
        return None  # Named staff and ambiguous third-person targets stay on existing identity resolution.
    followup = bool(previous and re.match(r"^(?:and\b|what about\b|only\b|sorry\b|actually\b|term\s*\w|ut\s*\d|whole\b|full\b|tomorrow\b|today\b|sun|mon|tue|wed|thu|fri|sat)", q))
    subject_followup = bool(previous and re.fullmatch(r"[\w -]{2,40}\??", q))
    if not (syllabus or timetable or followup or subject_followup or selection):
        state.pop("document_context", None)
        return None
    # Existing handlers split mixed questions; never silently drop a second intent.
    if re.search(r"\b(?:attendance|fees?|address|phone|results?|notices?)\b", q):
        state.pop("document_context", None)
        return None
    identity = identity_loader()
    if identity["role"] == "guest":
        return {"reply": "Please sign in to view school syllabus documents and personal timetables."}
    kind = "syllabus" if syllabus else "teacher_timetable" if timetable and own_timetable and identity.get("teacher_id") and not re.search(r"\bclass\b|\d{1,2}\s*[- ]?\s*[a-z]\b", q) else "timetable" if timetable else previous.get("kind", "syllabus")
    today = datetime.now(ZoneInfo("Asia/Riyadh")).date().isoformat()
    documents = [item for item in store.published(kind, today) if visible(item, identity)]
    if not documents and kind != "syllabus" and not selection:
        state.pop("document_context", None)
        return None  # Existing authorised timetable storage remains usable.
    filters = dict(previous.get("filters", {})) if previous.get("kind") == kind else {}
    cls = re.search(r"\b(1[0-2]|[1-9])\s*[- ]?\s*([a-h])\b", q)
    grade = re.search(r"\b(?:grade|class|year|yr)\s+(1[0-2]|[1-9])\b", q)
    if cls:
        filters.update(grade=cls[1], division=cls[2].upper())
        filters.pop("stream", None)
    elif grade:
        filters.update(grade=grade[1]); filters.pop("division", None); filters.pop("stream", None)
    year = re.search(r"\b20\d{2}-\d{2,4}\b", q)
    if year:
        filters["year"] = year[0]
    exam = re.search(r"\b(?:term\s*(?:\d+|i{1,3})|(?:ut|unit\s*test)\s*\d+)\b", q)
    if exam:
        filters["assessment"] = assessment(exam[0])
    elif re.search(r"\b(?:whole|full|entire|curriculum)\b", q):
        filters["assessment"] = assessment("Whole year")
    subjects = {row.get("subject", row.get("activity", "")) for item in documents for row in item["rows"]}
    named = [name for name in subjects if re.search(r"(?<!\w)" + re.escape(name.casefold()) + r"(?!\w)", q)]
    alias = subject_label(re.sub(r"^(?:and|what about|only)\s+", "", q).strip(" ?"))
    if alias in subjects:
        named.append(alias)
    if named:
        filters["subject"] = max(named, key=len)
    elif (re.fullmatch(r"[\w -]+ only\??", q) and not (syllabus or timetable or exam or grade or cls or year)
          and not re.search(r'\b(?:today|tomorrow|sunday|monday|tuesday|wednesday|thursday|friday|saturday)\b', q)):
        filters["subject"] = q.removesuffix('?').removesuffix(' only')
    elif re.search(r"\ball subjects?\b|\bwhole syllabus\b", q):
        filters.pop("subject", None)
    day = next((name for short, name in DAYS.items() if re.search(r"\b" + short + r"(?:day|sday|nesday|rsday|urday)?\b", q)), None)
    if day:
        filters["day"] = day
    if 'tomorrow' in q or 'today' in q:
        when = datetime.now(ZoneInfo('Asia/Riyadh')) + timedelta(days=1 if 'tomorrow' in q else 0)
        filters['day'] = when.strftime('%A')
    if re.search(r'\b(?:whole|full) week\b', q):
        filters.pop('day', None)
    if subject_followup and not (named or syllabus or timetable or followup or selection):
        state.pop('document_context', None)
        return None
    if selection:
        selected = next((item for item in documents if item["document_id"] == selection.get("document_id") and item["revision"] == selection.get("revision")), None)
        if not selected:
            return {"reply": "That document changed or is no longer available to your account. Please ask again."}
        documents = [selected]
        filters = selection.get("filters", {})
    else:
        documents = [item for item in documents if all(not filters.get(key) or (assessment(item["scope"][key]) == filters[key] if key == "assessment" else item["scope"][key].casefold() == filters[key].casefold()) for key in ("grade", "division", "stream", "year", "assessment"))]
    state["document_context"] = dict(kind=kind, filters=filters, expires=time.time() + TTL)
    if not documents:
        return {"reply": "No current, approved and published document matches that request for your account. It may not have been uploaded yet. I won’t substitute another class, term or year."}
    if (followup and not selection and not (syllabus or timetable or named or exam or cls or grade or year or day)
            and not re.search(r'\b(?:today|tomorrow|whole|full|all subjects?)\b', q)):
        values = sorted({row.get('subject', row.get('activity', '')) for item in documents for row in item['rows']})
        return {'reply': 'I could not match that follow-up to a subject or document filter. Which available subject do you mean? You can also ask a new school question.',
                'choices': offer(state, [(name, dict(message=f'{name} only')) for name in values if name], owner)}
    # Even a single upload needs explicit confirmation on a vague syllabus question.
    vague = kind == "syllabus" and not filters.get("assessment") and not selection
    if len(documents) > 1 or vague:
        options = []
        for item in documents[:12]:
            scope = item["scope"]
            label = " · ".join(part for part in [scope["year"], scope["grade"] + ("-" + scope["division"] if scope["division"] else ""), scope["stream"], scope["assessment"]] if part)
            options.append((label, dict(document_id=item["document_id"], revision=item["revision"], filters=filters, document=True)))
        return {"reply": "Which published document do you need? Only current documents available to your account are listed." + (" Narrow the year/class if your document is not among these 12." if len(documents) > 12 else ""), "choices": offer(state, options, owner)}
    item = documents[0]
    # Once a choice is resolved, retain its real scope for subsequent subject/day
    # follow-ups. A later explicit class/term correction still replaces these slots.
    for key in ('year', 'grade', 'division', 'stream', 'assessment'):
        filters[key] = assessment(item['scope'][key]) if key == 'assessment' else item['scope'][key]
    state['document_context'] = dict(kind=kind, filters=filters, expires=time.time() + TTL)
    rows = [row for row in item["rows"] if (not filters.get("subject") or row.get("subject", row.get("activity", "")).casefold() == filters["subject"].casefold()) and (not filters.get("day") or row.get("day") == filters["day"])]
    if not rows:
        return {"reply": "The published document has no entries matching that subject/day. I won’t infer missing lessons or portions."}
    scope = item["scope"]
    heading = " · ".join(part for part in [scope["year"], "Grade " + scope["grade"] if scope["grade"] else "Teacher timetable", scope["division"], scope["stream"], scope["assessment"]] if part)
    table = data_table(["Subject", "Book / section", "Chapter", "Portions"], [[row[key] for key in ("subject", "section", "chapter", "topic")] for row in rows]) if kind == "syllabus" else document_grid(rows, kind == "teacher_timetable")
    # Keep large syllabuses local and structured: no prompt construction or model tokens.
    return {"reply": cell(heading) + "\n\n" + table + "\n\n" + data_table(['Source document', 'Revision'], [[item['filename'], item['revision']]]) + f"\n\nValid {scope['effective_from']} to {scope['effective_to']}."}
