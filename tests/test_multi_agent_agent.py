"""MultiAgentTrader invariants — Protocol, weekly, timeout, validation, fallbacks."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
import pytest

from src.agent_base import Agent
from src.llm import metrics
from src.llm.client import ChatResult
from src.llm.multi_agent.agent import MultiAgentTrader
from src.llm.multi_agent.nodes import (
    analysts,
    portfolio_manager,
    researchers,
    risk_manager,
    trader,
)


@dataclass
class _FakeClient:
    responses: list[Any]
    calls: list[dict] = field(default_factory=list)

    def chat(self, **kwargs) -> ChatResult:
        self.calls.append(kwargs)
        if not self.responses:
            raise RuntimeError("queue empty")
        return self.responses.pop(0)


def _resp(text: str) -> ChatResult:
    return ChatResult(
        text=text,
        tool_calls=[],
        usage={
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "cached_tokens": 0,
            "total_tokens": 120,
        },
        model="gpt-4o-mini",
        finish_reason="stop",
    )


@pytest.fixture(autouse=True)
def _stub_prompts(monkeypatch):
    for mod in (analysts, researchers, trader, risk_manager, portfolio_manager):
        monkeypatch.setattr(mod, "_prompt", lambda role: f"STUB: {role}")


def _info(md, idx: int = 5) -> dict:
    return {
        "date": str(md.dates[idx]),
        "t": idx,
        "cash": 5e7,
        "holdings": [3_200_000, 2_100_000, 6_900_000, 880_000, 3_000_000],
        "portfolio_value": 1_000_000_000.0,
        "close_t": [55.5, 90.1, 27.4, 215.2, 62.0],
    }


def _good_responses() -> list[ChatResult]:
    """10 responses for a happy-path full traversal (cap=2)."""
    return [_resp(f"out_{i}") for i in range(9)] + [
        _resp('{"VCB":0.2,"FPT":0.2,"HPG":0.2,"VIC":0.2,"VNM":0.1}')
    ]


def test_protocol_runtime_check(synthetic_market_data, tmp_path):
    fake = _FakeClient(responses=_good_responses())
    agent = MultiAgentTrader(
        synthetic_market_data,
        pd.DataFrame(),
        client=fake,
        transcript_dir=tmp_path / "transcripts",
        decisions_log_path=tmp_path / "decisions.jsonl",
    )
    assert isinstance(agent, Agent)
    assert agent.name == "multi_agent"


def test_invalid_model_raises_loud_in_constructor(synthetic_market_data, tmp_path):
    """Model not in whitelist → ValueError BEFORE any backtest step."""
    fake = _FakeClient(responses=[])
    with pytest.raises(ValueError, match="not in whitelist"):
        MultiAgentTrader(
            synthetic_market_data,
            pd.DataFrame(),
            client=fake,
            models={"trader": "gpt-3.5-turbo"},  # forbidden
            transcript_dir=tmp_path / "transcripts",
            decisions_log_path=tmp_path / "decisions.jsonl",
        )


def test_weekly_cache_skips_graph_within_same_week(synthetic_market_data, tmp_path):
    """Second decide() within same ISO week reuses cached weights → graph
    not invoked again → fake.calls count unchanged."""
    fake = _FakeClient(responses=_good_responses())
    agent = MultiAgentTrader(
        synthetic_market_data,
        pd.DataFrame(),
        client=fake,
        transcript_dir=tmp_path / "t",
        decisions_log_path=tmp_path / "d.jsonl",
    )
    obs = np.zeros(56, dtype=np.float32)
    a1 = agent.decide(obs, _info(synthetic_market_data, 0))
    n1 = len(fake.calls)
    a2 = agent.decide(obs, _info(synthetic_market_data, 1))  # same ISO week
    assert len(fake.calls) == n1  # no new LLM calls
    np.testing.assert_allclose(a1, a2)


def test_iso_week_change_triggers_new_decision(synthetic_market_data, tmp_path):
    """New ISO week → graph re-invoked → fresh LLM calls."""
    fake = _FakeClient(responses=_good_responses() + _good_responses())
    agent = MultiAgentTrader(
        synthetic_market_data,
        pd.DataFrame(),
        client=fake,
        transcript_dir=tmp_path / "t",
        decisions_log_path=tmp_path / "d.jsonl",
    )
    obs = np.zeros(56, dtype=np.float32)
    agent.decide(obs, _info(synthetic_market_data, 0))  # week 1
    n1 = len(fake.calls)
    agent.decide(obs, _info(synthetic_market_data, 5))  # week 2 of synthetic fixture
    assert len(fake.calls) > n1


def test_timeout_falls_back_to_hold_shares(synthetic_market_data, tmp_path):
    """If graph exceeds decision_timeout_s → hold-shares + metric recorded."""
    metrics.reset()
    fake = _FakeClient(responses=_good_responses())
    agent = MultiAgentTrader(
        synthetic_market_data,
        pd.DataFrame(),
        client=fake,
        decision_timeout_s=0.05,  # absurdly small
        transcript_dir=tmp_path / "t",
        decisions_log_path=tmp_path / "d.jsonl",
    )

    # Replace compiled graph with a slow-invoke stub
    class _SlowApp:
        def invoke(self, *a, **kw):
            time.sleep(0.5)
            return {"portfolio_manager_output": "{}", "transcript": []}

    agent._app = _SlowApp()
    obs = np.zeros(56, dtype=np.float32)
    a = agent.decide(obs, _info(synthetic_market_data, 0))
    assert a.sum() > 0.5  # hold-shares (significant non-zero)
    snap = metrics.get_snapshot()
    assert snap["parse_failure_reasons"].get("multi_agent_timeout", 0) >= 1


def test_transcript_dir_none_disables_writes(synthetic_market_data, tmp_path):
    fake = _FakeClient(responses=_good_responses())
    agent = MultiAgentTrader(
        synthetic_market_data,
        pd.DataFrame(),
        client=fake,
        transcript_dir=None,
        decisions_log_path=None,
    )
    obs = np.zeros(56, dtype=np.float32)
    agent.decide(obs, _info(synthetic_market_data, 0))
    assert not list(tmp_path.glob("**/*.json"))
    assert not list(tmp_path.glob("**/*.jsonl"))


def test_decisions_log_appends_per_decision(synthetic_market_data, tmp_path):
    """2 decisions across 2 weeks → JSONL has 2 lines, each parsing valid JSON."""
    fake = _FakeClient(responses=_good_responses() + _good_responses())
    log = tmp_path / "decisions.jsonl"
    agent = MultiAgentTrader(
        synthetic_market_data,
        pd.DataFrame(),
        client=fake,
        transcript_dir=tmp_path / "t",
        decisions_log_path=log,
    )
    obs = np.zeros(56, dtype=np.float32)
    agent.decide(obs, _info(synthetic_market_data, 0))
    agent.decide(obs, _info(synthetic_market_data, 5))
    lines = log.read_text().splitlines()
    assert len(lines) == 2
    recs = [json.loads(line) for line in lines]
    assert all(r["agent"] == "multi_agent" for r in recs)
    assert all(r["parse_ok"] for r in recs)
    assert all(r["debate_rounds"] == 2 for r in recs)
    assert all(r["timed_out"] is False for r in recs)


def test_transcript_file_written_per_date(synthetic_market_data, tmp_path):
    """1 decision → 1 transcript JSON named by date."""
    fake = _FakeClient(responses=_good_responses())
    tdir = tmp_path / "transcripts"
    agent = MultiAgentTrader(
        synthetic_market_data,
        pd.DataFrame(),
        client=fake,
        transcript_dir=tdir,
        decisions_log_path=tmp_path / "d.jsonl",
    )
    obs = np.zeros(56, dtype=np.float32)
    info = _info(synthetic_market_data, 0)
    agent.decide(obs, info)
    files = list(tdir.glob("*.json"))
    assert len(files) == 1
    payload = json.loads(files[0].read_text())
    assert payload["agent"] == "multi_agent"
    assert payload["debate_rounds"] == 2
    assert len(payload["transcript"]) == 10
    # Synthesis chain outputs present
    assert "trader_proposal" in payload
    assert "risk_review" in payload
    assert "portfolio_manager_output" in payload
    assert payload["portfolio_manager_output"].startswith("{")


def test_portfolio_manager_parse_failure_falls_back_to_hold_shares(
    synthetic_market_data, tmp_path
):
    """Portfolio manager returns garbage → parse_weights_json hold-shares."""
    metrics.reset()
    # 9 OK responses + 1 garbage from portfolio_manager
    bad = [_resp(f"out_{i}") for i in range(9)] + [_resp("I refuse to give weights.")]
    fake = _FakeClient(responses=bad)
    agent = MultiAgentTrader(
        synthetic_market_data,
        pd.DataFrame(),
        client=fake,
        transcript_dir=tmp_path / "t",
        decisions_log_path=tmp_path / "d.jsonl",
    )
    obs = np.zeros(56, dtype=np.float32)
    a = agent.decide(obs, _info(synthetic_market_data, 0))
    assert a.sum() > 0.5  # hold-shares
    snap = metrics.get_snapshot()
    assert snap["parse_failure"] >= 1
