"""Tests for backend/routes/live.py with a stub StateGraph (no real LLM).

Strategy: monkeypatch backend.routes.live's references (build_app,
make_initial_state, LookaheadSafeTools, OpenAIClient, load_live_inputs)
to inject a tiny fake graph that emits 2 nodes — technical_analyst and
portfolio_manager. Verifies event ordering, decision payload, error path,
and request body validation. ZERO real OpenAI calls.
"""

from __future__ import annotations

import json
from operator import add
from typing import Annotated, TypedDict

import pytest
from fastapi.testclient import TestClient
from langgraph.graph import END, START, StateGraph

from backend.main import create_app


class _StubState(TypedDict, total=False):
    transcript: Annotated[list[dict], add]
    portfolio_manager_output: str
    technical_brief: str


def _build_stub_app():
    def technical_analyst(_s):
        return {"technical_brief": "stub tech brief"}

    def portfolio_manager(_s):
        return {"portfolio_manager_output": '```json\n{"VCB": 0.2, "FPT": 0.2}\n```'}

    g = StateGraph(_StubState)
    g.add_node("technical_analyst", technical_analyst)
    g.add_node("portfolio_manager", portfolio_manager)
    g.add_edge(START, "technical_analyst")
    g.add_edge("technical_analyst", "portfolio_manager")
    g.add_edge("portfolio_manager", END)
    return g.compile()


def _stub_initial_state(**_kw):
    return {
        "transcript": [],
        "portfolio_manager_output": "",
        "technical_brief": "",
    }


class _StubMD:
    """Minimal MarketData stub for load_live_inputs's return."""

    dates = [None]
    tickers: tuple[str, ...] = ()


def _stub_load_live_inputs(**_kw):
    return _StubMD(), None, {}


@pytest.fixture
def patched_live(monkeypatch):
    """Monkeypatch all of routes.live's heavy deps to fake equivalents."""
    from backend.routes import live as live_mod

    monkeypatch.setattr(live_mod, "build_app", _build_stub_app)
    monkeypatch.setattr(live_mod, "make_initial_state", _stub_initial_state)
    monkeypatch.setattr(live_mod, "LookaheadSafeTools", lambda *a, **kw: object())
    monkeypatch.setattr(live_mod, "OpenAIClient", lambda *a, **kw: object())
    monkeypatch.setattr(live_mod, "load_live_inputs", _stub_load_live_inputs)
    return live_mod


@pytest.fixture
def client(patched_live):
    return TestClient(create_app())


def _parse_sse(raw: str) -> list[dict]:
    """Tiny SSE parser. Each event is a blank-line-delimited block of
    `key: value` lines; lines starting with `:` are SSE comments (heartbeats)."""
    events: list[dict] = []
    current: dict = {}
    for line in raw.splitlines():
        if not line.strip():
            if current:
                events.append(current)
                current = {}
            continue
        if line.startswith(":"):
            continue
        if ":" in line:
            k, _, v = line.partition(":")
            current[k.strip()] = v.lstrip()
    if current:
        events.append(current)
    return events


def test_live_run_emits_agent_start_then_complete_then_decision(client):
    r = client.post("/live/run", json={})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse(r.text)
    types = [e["event"] for e in events if "event" in e]
    # First event is agent_start for the first node.
    assert types[0] == "agent_start"
    # Decision fires last.
    assert types[-1] == "decision"
    # Each node yields start + complete; with 2 nodes we have 4 + 1 decision.
    assert types.count("agent_start") == 2
    assert types.count("agent_complete") == 2


def test_live_run_decision_payload_carries_parsed_weights(client):
    r = client.post("/live/run", json={})
    events = _parse_sse(r.text)
    dec = next(e for e in events if e.get("event") == "decision")
    payload = json.loads(dec["data"])
    assert payload["weights"] == {"VCB": 0.2, "FPT": 0.2}
    assert "rationale" in payload


def test_live_run_agent_complete_includes_summary(client):
    r = client.post("/live/run", json={})
    events = _parse_sse(r.text)
    tech_complete = next(
        e
        for e in events
        if e.get("event") == "agent_complete"
        and json.loads(e["data"])["role"] == "technical_analyst"
    )
    data = json.loads(tech_complete["data"])
    assert data["summary"] == "stub tech brief"


def test_live_run_emits_error_event_on_upstream_exception(monkeypatch):
    from backend.routes import live as live_mod

    def boom(**_kw):
        raise RuntimeError("simulated upstream failure")

    monkeypatch.setattr(live_mod, "load_live_inputs", boom)
    monkeypatch.setattr(live_mod, "build_app", _build_stub_app)
    monkeypatch.setattr(live_mod, "make_initial_state", _stub_initial_state)
    monkeypatch.setattr(live_mod, "LookaheadSafeTools", lambda *a, **kw: object())
    monkeypatch.setattr(live_mod, "OpenAIClient", lambda *a, **kw: object())

    client = TestClient(create_app())
    r = client.post("/live/run", json={})
    assert r.status_code == 200  # error inside stream, not at handshake
    events = _parse_sse(r.text)
    err = next(e for e in events if e.get("event") == "error")
    data = json.loads(err["data"])
    assert "simulated upstream failure" in data["message"]


def test_live_run_accepts_optional_request_body(client):
    r = client.post(
        "/live/run",
        json={"tickers": ["VCB", "FPT"], "debate_rounds": 1, "use_realtime": False},
    )
    assert r.status_code == 200
    events = _parse_sse(r.text)
    assert any(e.get("event") == "agent_start" for e in events)
    assert any(e.get("event") == "decision" for e in events)
