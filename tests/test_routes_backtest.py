"""Tests for backend/routes/backtest.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app


def _write_backtest(root: Path, name: str, **metric_extras: float) -> None:
    payload = {
        "agent": name,
        "portfolio_curve": [{"date": "2025-05-05", "value": 1_000_000_000}],
        "holdings": [
            {
                "date": "2025-05-05",
                "VCB": 100,
                "FPT": 0,
                "HPG": 0,
                "VIC": 0,
                "VNM": 0,
            }
        ],
        "metrics": {
            "cumulative_return": 0.1,
            "sharpe": 1.0,
            "sortino": 1.5,
            "max_drawdown": 0.05,
            "turnover": 0.02,
            "total_cost": 1_500_000,
            "n_steps": 247,
            **metric_extras,
        },
        "provenance": {
            "ts": "2026-05-17T00:00:00+00:00",
            "seed": 42,
            "test_window": ["2025-05-05", "2026-04-30"],
            "n_steps": 247,
        },
    }
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "metrics.json").write_text(json.dumps(payload))


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    app = create_app()
    app.state.results_dir = tmp_path
    app.state.cache.clear()
    return TestClient(app)


def test_get_backtest_returns_pkg10_payload(client: TestClient, tmp_path: Path) -> None:
    _write_backtest(tmp_path, "buy_and_hold")
    r = client.get("/backtest/buy_and_hold")
    assert r.status_code == 200
    body = r.json()
    assert body["agent"] == "buy_and_hold"
    assert body["metrics"]["cumulative_return"] == 0.1
    assert body["metrics"]["sharpe"] == 1.0
    assert body["holdings"][0]["VCB"] == 100
    assert body["provenance"]["seed"] == 42


def test_get_backtest_404_on_missing_agent(client: TestClient) -> None:
    r = client.get("/backtest/nonexistent")
    assert r.status_code == 404
    assert "nonexistent" in r.json()["detail"]


def test_get_backtest_500_on_schema_drift(tmp_path: Path) -> None:
    # PKG-10 drift surfacing as Pydantic response validation error.
    # raise_server_exceptions=False to observe the HTTP 500 a real client
    # would see, rather than re-raising the exception in-process.
    app = create_app()
    app.state.results_dir = tmp_path
    app.state.cache.clear()
    drift_client = TestClient(app, raise_server_exceptions=False)
    d = tmp_path / "broken"
    d.mkdir()
    (d / "metrics.json").write_text(
        json.dumps(
            {
                "agent": "broken",
                "portfolio_curve": [],
                "holdings": [],
                "metrics": {"sharpe": 1.0},  # missing cumulative_return etc.
                "provenance": {
                    "ts": "x",
                    "seed": 42,
                    "test_window": None,
                    "n_steps": 0,
                },
            }
        )
    )
    r = drift_client.get("/backtest/broken")
    assert r.status_code == 500


def test_get_backtest_extra_metrics_pass_through(client: TestClient, tmp_path: Path) -> None:
    _write_backtest(
        tmp_path,
        "multi_agent",
        llm_cost_usd=12.4,
        n_decisions=44,
        avg_latency_s=6.2,
    )
    r = client.get("/backtest/multi_agent")
    assert r.status_code == 200
    m = r.json()["metrics"]
    assert m["llm_cost_usd"] == 12.4
    assert m["n_decisions"] == 44
    assert m["avg_latency_s"] == 6.2


def test_get_backtest_cache_hit_on_second_call(client: TestClient, tmp_path: Path) -> None:
    _write_backtest(tmp_path, "ppo")
    assert client.app.state.cache.size() == 0
    client.get("/backtest/ppo")
    assert client.app.state.cache.size() == 1
    client.get("/backtest/ppo")
    # Still 1 — cached, no new entries.
    assert client.app.state.cache.size() == 1
