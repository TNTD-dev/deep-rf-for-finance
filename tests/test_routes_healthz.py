"""Tests for backend/routes/healthz.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    app = create_app()
    app.state.results_dir = tmp_path
    app.state.cache.clear()
    return TestClient(app)


def test_healthz_returns_ok(client: TestClient, tmp_path: Path) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["results_dir"] == str(tmp_path)
    assert body["results_dir_exists"] is True
    assert body["n_metrics_files"] == 0
    assert body["n_cached"] == 0
    assert body["uptime_s"] >= 0


def test_healthz_counts_metrics_files(client: TestClient, tmp_path: Path) -> None:
    (tmp_path / "agent_a").mkdir()
    (tmp_path / "agent_a" / "metrics.json").write_text(json.dumps({"a": 1}))
    (tmp_path / "agent_b").mkdir()
    (tmp_path / "agent_b" / "metrics.json").write_text(json.dumps({"b": 2}))
    # Nested dir (e.g. multi_agent/transcripts) should NOT count.
    (tmp_path / "agent_c" / "transcripts").mkdir(parents=True)
    (tmp_path / "agent_c" / "transcripts" / "2025-05-05.json").write_text("{}")
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["n_metrics_files"] == 2
