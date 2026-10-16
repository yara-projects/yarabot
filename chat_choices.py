"""Reusable, short-lived clarification choices. Labels never grant authority."""

import secrets
import time


def offer(state, options, owner, ttl=300):
    """Options are server-built (label, action) pairs, not arbitrary client commands."""
    nonce = secrets.token_urlsafe(18)
    options = options[:12]
    state["chat_choices"] = dict(nonce=nonce, options=[action for _, action in options], owner=list(owner), expires=time.time() + ttl)
    return [dict(label=label, token=f"{nonce}.{index}") for index, (label, _) in enumerate(options)]


def consume(state, token, owner):
    pending = state.pop("chat_choices", None)
    if not isinstance(token, str) or len(token) > 100 or not pending or pending.get("owner") != list(owner) or time.time() > pending.get("expires", 0):
        raise ValueError("Those options expired. Please ask your question again.")
    nonce, _, index = token.partition(".")
    if not secrets.compare_digest(nonce, pending["nonce"]) or not index.isdigit() or int(index) >= len(pending["options"]):
        raise ValueError("That option is no longer available. Please ask again.")
    return pending["options"][int(index)]


def legacy_options(state, role, reply):
    """Expose existing server clarification state across topics, without parsing user authority."""
    pending = state.get("pending_clarification") or {}
    if pending.get("role") != role or time.time() > pending.get("expires_at", 0):
        return []
    if pending.get("intent") == "class_teacher_choice" and 'Do you mean' in reply and 'class teacher' in reply and 'subject teachers' in reply:
        return [("Class teacher", {"message": "class teacher"}), ("Subject teachers", {"message": "all subject teachers"})]
    # Other slots (person/class/subject) are not invented here. Their providers must
    # supply actual authorised values, using offer(), just like document choices.
    return []
