"""Tests for backend/routes/debate.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app


def _write_transcript(
    root: Path,
    date: str,
    pm_output: str | None = '```json\n{"VCB": 0.2, "FPT": 0.2}\n```',
    transcript_extra: list[dict] | None = None,
) -> None:
    entries = transcript_extra or [
        {
            "role": "technical_analyst",
            "ts": "2026-05-16T08:30:00Z",
            "model": "gpt-4o-mini",
            "output": "RSI VCB 71 quá mua",
            "usage": {},
        },
        {
            "role": "portfolio_manager",
            "ts": "2026-05-16T08:30:30Z",
            "model": "gpt-4o",
            "output": pm_output or "",
            "usage": {},
        },
    ]
    d = root / "multi_agent" / "transcripts"
    d.mkdir(parents=True, exist_ok=True)
    payload = {
        "date": date,
        "agent": "multi_agent",
        "duration_s": 30.0,
        "debate_rounds": 2,
        "timed_out": False,
        "node_errors": [],
        "models_used": {},
        "transcript": entries,
        "portfolio_manager_output": pm_output,
    }
    (d / f"{date}.json").write_text(json.dumps(payload))


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    app = create_app()
    app.state.results_dir = tmp_path
    app.state.cache.clear()
    return TestClient(app)


def test_get_debate_returns_prd_shape(client: TestClient, tmp_path: Path) -> None:
    _write_transcript(tmp_path, "2025-05-05")
    r = client.get("/debate/multi_agent/2025-05-05")
    assert r.status_code == 200
    body = r.json()
    assert body["date"] == "2025-05-05"
    assert len(body["transcript"]) == 2
    first = body["transcript"][0]
    assert first["role"] == "technical_analyst"
    assert first["content"] == "RSI VCB 71 quá mua"
    # extras (model, ts) survive the mapping
    assert first["model"] == "gpt-4o-mini"


def test_get_debate_404_on_missing_date(client: TestClient, tmp_path: Path) -> None:
    r = client.get("/debate/multi_agent/2099-01-01")
    assert r.status_code == 404
    assert "2099-01-01" in r.json()["detail"]


def test_get_debate_400_on_non_multi_agent(client: TestClient) -> None:
    r = client.get("/debate/buy_and_hold/2025-05-05")
    assert r.status_code == 400
    assert "multi_agent" in r.json()["detail"]


def test_get_debate_injects_pm_decision(client: TestClient, tmp_path: Path) -> None:
    _write_transcript(tmp_path, "2025-05-05")
    body = client.get("/debate/multi_agent/2025-05-05").json()
    last = body["transcript"][-1]
    assert last["role"] == "portfolio_manager"
    assert last["decision"] == {"VCB": 0.2, "FPT": 0.2}


def test_get_debate_omits_decision_on_parse_failure(client: TestClient, tmp_path: Path) -> None:
    _write_transcript(
        tmp_path,
        "2025-05-05",
        pm_output="random text without any json object",
    )
    body = client.get("/debate/multi_agent/2025-05-05").json()
    last = body["transcript"][-1]
    assert "decision" not in last
