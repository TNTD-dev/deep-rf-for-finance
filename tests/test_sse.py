"""Tests for backend/sse.py — extract_decision + sse_event helpers."""

from __future__ import annotations

import json

from backend.sse import extract_decision, sse_event


def test_extract_decision_json_fence() -> None:
    text = '```json\n{"VCB": 0.2, "FPT": 0.3}\n```'
    assert extract_decision(text) == {"VCB": 0.2, "FPT": 0.3}


def test_extract_decision_bare_object() -> None:
    assert extract_decision('preamble {"VCB": 0.5} epilogue') == {"VCB": 0.5}


def test_extract_decision_returns_none_for_garbage() -> None:
    assert extract_decision("random text without any json") is None
    assert extract_decision("") is None
    assert extract_decision(None) is None


def test_extract_decision_returns_none_for_non_dict_json() -> None:
    # Regex finds `[1,2,3]`? No — pattern requires `{`. But test list-as-JSON
    # at start to confirm we don't crash on weird inputs.
    assert extract_decision("[1, 2, 3]") is None
    # Object that fails json.loads (trailing comma)
    assert extract_decision('{"VCB": 0.2,}') is None


def test_sse_event_serializes_dict() -> None:
    out = sse_event("agent_start", {"role": "trader"})
    assert out["event"] == "agent_start"
    assert json.loads(out["data"]) == {"role": "trader"}


def test_sse_event_passes_string_through() -> None:
    out = sse_event("error", "raw message")
    assert out == {"event": "error", "data": "raw message"}
