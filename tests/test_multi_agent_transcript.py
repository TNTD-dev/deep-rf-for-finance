"""Transcript writer invariants — JSON write, JSONL append, error swallowing."""

from __future__ import annotations

import json

from src.llm.multi_agent.transcript import (
    append_decision_log,
    now_iso,
    write_transcript,
)


def test_now_iso_returns_utc_iso_string():
    s = now_iso()
    # ISO-8601 UTC ends with +00:00
    assert s.endswith("+00:00")
    assert "T" in s


def test_write_transcript_creates_json_file(tmp_path):
    d = tmp_path / "transcripts"
    payload = {"date": "2025-05-05", "transcript": [{"role": "technical_analyst"}]}
    write_transcript(d, "2025-05-05", payload)
    p = d / "2025-05-05.json"
    assert p.exists()
    assert json.loads(p.read_text())["date"] == "2025-05-05"


def test_write_transcript_overwrites_existing(tmp_path):
    """Same date → second call replaces first. Decisions are atomic per date;
    a retry of the same date should produce ONE transcript, not append/dup."""
    d = tmp_path / "transcripts"
    write_transcript(d, "2025-05-05", {"v": 1})
    write_transcript(d, "2025-05-05", {"v": 2})
    assert json.loads((d / "2025-05-05.json").read_text())["v"] == 2


def test_append_decision_log_creates_jsonl(tmp_path):
    p = tmp_path / "decisions.jsonl"
    append_decision_log(p, {"date": "2025-05-05", "parse_ok": True})
    lines = p.read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["date"] == "2025-05-05"


def test_append_decision_log_appends_across_calls(tmp_path):
    """Second call adds a line, doesn't truncate. Decisions log is the
    backtest-level audit trail and must persist all decisions."""
    p = tmp_path / "decisions.jsonl"
    append_decision_log(p, {"date": "2025-05-05"})
    append_decision_log(p, {"date": "2025-05-12"})
    lines = p.read_text().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[1])["date"] == "2025-05-12"


def test_write_transcript_swallows_filesystem_error(tmp_path, monkeypatch, caplog):
    """A filesystem failure during a write MUST NOT raise — backtest is the
    priority. We log a warning and move on."""
    # Make the dir non-writable by patching Path.mkdir to raise
    import logging
    from pathlib import Path

    def boom(self, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "mkdir", boom)
    with caplog.at_level(logging.WARNING):
        write_transcript(tmp_path / "x", "2025-05-05", {"v": 1})
    assert any("transcript write failed" in r.message for r in caplog.records)


def test_append_decision_log_swallows_filesystem_error(tmp_path, monkeypatch, caplog):
    import logging
    from pathlib import Path

    def boom(self, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "mkdir", boom)
    with caplog.at_level(logging.WARNING):
        append_decision_log(tmp_path / "x" / "d.jsonl", {"date": "2025-05-05"})
    assert any("decisions log append failed" in r.message for r in caplog.records)


def test_write_transcript_handles_non_ascii_and_objects(tmp_path):
    """Vietnamese strings + pd.Timestamp-like objects must serialize cleanly
    via default=str."""
    import datetime as dt
    payload = {
        "date": "2025-05-05",
        "title_vn": "Lợi nhuận Vietcombank tăng mạnh",
        "ts": dt.datetime(2025, 5, 5, 9, 0),
    }
    d = tmp_path / "transcripts"
    write_transcript(d, "2025-05-05", payload)
    text = (d / "2025-05-05.json").read_text(encoding="utf-8")
    assert "Lợi nhuận Vietcombank" in text  # non-ASCII preserved
    assert "2025-05-05" in text
