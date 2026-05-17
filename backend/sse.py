"""Generic SSE primitives + shared parsing helpers (PKG-12).

Re-exports ``sse_starlette.event.ServerSentEvent`` for consistency.
``extract_decision`` is shared between ``routes/debate.py`` (PKG-11) and
``routes/live.py`` (PKG-12) so the regex + parser-fallback live in one place.
"""

from __future__ import annotations

import json
import re

from sse_starlette.event import ServerSentEvent  # noqa: F401 (re-export)

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.+?\})\s*```", re.DOTALL)
_BARE_OBJECT_RE = re.compile(r"\{[^{}]*\}", re.DOTALL)


def extract_decision(text: str | None) -> dict | None:
    """Pull the first JSON object out of an LLM output. Returns the dict or
    None on any parse failure. Pure function — no env, no side effects.

    Tries a fenced ```json {...}``` block first, then a bare {...} object
    anywhere in the text. Used by PKG-11 debate route + PKG-12 live route
    to surface the portfolio_manager's weights dict in the response.
    """
    if not text:
        return None
    m = _JSON_BLOCK_RE.search(text)
    blob = m.group(1) if m else None
    if blob is None:
        m = _BARE_OBJECT_RE.search(text)
        blob = m.group(0) if m else None
    if blob is None:
        return None
    try:
        parsed = json.loads(blob)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def sse_event(event: str, data: dict | str) -> dict:
    """Build an SSE event dict consumable by EventSourceResponse.

    ``EventSourceResponse`` accepts ``{"event": str, "data": str}`` dicts;
    we serialize dict payloads to JSON here so callers can pass plain dicts.
    """
    payload = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    return {"event": event, "data": payload}
