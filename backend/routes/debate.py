"""GET /debate/{agent}/{date} — multi-agent transcript replay (PKG-11).

Maps PKG-8 transcript schema → PRD §10 debate shape:
  {role, output, model, ts, ...} → {role, content=output, model, ts, ...}

Injects ``decision`` (parsed weights dict) on the final portfolio_manager
entry when ``portfolio_manager_output`` parses cleanly. Parse failure →
omit decision (don't crash; PKG-15 UI handles missing decision).

PKG-S S5b adds ``GET /debate/{agent}`` for date-list discovery so the
frontend can stop hardcoding ``AVAILABLE_DEBATE_DATES``.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from backend.models import DebateDatesResponse, DebateTranscript
from backend.sse import extract_decision

router = APIRouter()


@router.get("/debate/{agent}", response_model=DebateDatesResponse)
def list_debate_dates(agent: str, request: Request) -> dict:
    """List transcript dates available on disk (PKG-S S5b).

    Sorted lexicographic — YYYY-MM-DD makes that equivalent to chronological.
    Empty list (not 404) when the dir is missing so the FE can show a
    "run the backtest" empty state without an error banner.
    """
    if agent != "multi_agent":
        raise HTTPException(400, "debate only supported for agent=multi_agent")
    transcripts_dir = request.app.state.results_dir / agent / "transcripts"
    if not transcripts_dir.exists():
        return {"agent": agent, "dates": []}
    dates = sorted(p.stem for p in transcripts_dir.glob("*.json"))
    return {"agent": agent, "dates": dates}


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
    decision = extract_decision(raw.get("portfolio_manager_output"))
    if decision and mapped and mapped[-1]["role"] == "portfolio_manager":
        mapped[-1]["decision"] = decision
    return {"date": raw["date"], "transcript": mapped}
