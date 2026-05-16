"""Persist multi-agent transcripts + per-decision summaries.

Two outputs:
- ``results/multi_agent/transcripts/<YYYY-MM-DD>.json`` — full per-decision detail
- ``results/multi_agent/decisions.jsonl`` — append-only one-line summary

Both writes are best-effort: failures are logged warnings, never raised,
so a filesystem hiccup never crashes a 248-session backtest. PKG-15
(debate replay UI) consumes the JSON; PKG-10 (metrics) consumes the JSONL.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

log = logging.getLogger(__name__)


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def write_transcript(
    transcript_dir: Path, date_str: str, payload: dict
) -> None:
    """Write payload as ``<date_str>.json`` under transcript_dir. Overwrites."""
    try:
        transcript_dir.mkdir(parents=True, exist_ok=True)
        p = transcript_dir / f"{date_str}.json"
        p.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    except OSError as e:
        log.warning("transcript write failed for %s: %s", date_str, e)


def append_decision_log(decisions_log_path: Path, record: dict) -> None:
    """Append one JSON line to decisions_log_path."""
    try:
        decisions_log_path.parent.mkdir(parents=True, exist_ok=True)
        with decisions_log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except OSError as e:
        log.warning("decisions log append failed: %s", e)
