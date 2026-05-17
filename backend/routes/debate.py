"""GET /debate/{agent}/{date} — multi-agent transcript replay (PKG-11).

Maps PKG-8 transcript schema → PRD §10 debate shape:
  {role, output, model, ts, ...} → {role, content=output, model, ts, ...}

Injects ``decision`` (parsed weights dict) on the final portfolio_manager
entry when ``portfolio_manager_output`` parses cleanly. Parse failure →
omit decision (don't crash; PKG-15 UI handles missing decision).
"""

from __future__ import annotations

import json
import re

from fastapi import APIRouter, HTTPException, Request

from backend.models import DebateTranscript

router = APIRouter()

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.+?\})\s*```", re.DOTALL)
_BARE_OBJECT_RE = re.compile(r"\{[^{}]*\}", re.DOTALL)


def _extract_decision(text: str | None) -> dict | None:
    """Pull the first JSON object out of an LLM output. Returns the dict or
    None on any parse failure. Pure function — no env, no side effects."""
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


@router.get("/debate/{agent}/{date}", response_model=DebateTranscript)
def get_debate(agent: str, date: str, request: Request) -> dict:
    if agent != "multi_agent":
        raise HTTPException(400, "debate only supported for agent=multi_agent")
    path = request.app.state.results_dir / "multi_agent" / "transcripts" / f"{date}.json"
    raw = request.app.state.cache.get(path)
    if raw is None:
        raise HTTPException(404, f"no transcript for date {date!r}")
    mapped = [
        {
            "role": e["role"],
            "content": e.get("output", ""),
            "model": e.get("model"),
            "ts": e.get("ts"),
        }
        for e in raw.get("transcript", [])
    ]
    decision = _extract_decision(raw.get("portfolio_manager_output"))
    if decision and mapped and mapped[-1]["role"] == "portfolio_manager":
        mapped[-1]["decision"] = decision
    return {"date": raw["date"], "transcript": mapped}
