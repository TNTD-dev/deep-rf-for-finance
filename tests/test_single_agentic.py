"""SingleAgenticTrader invariants — tool loop, cap, audit log, fallbacks.

Uses synthetic_market_data fixture + fake OpenAIClient queue (mirror
test_zero_shot.py). No real OpenAI calls. Audit_log_path uses tmp_path or
None so the real results/single_agentic/ dir stays untouched between runs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
import pytest

from src.agent_base import Agent
from src.data_pipeline.news_align import compute_available_for_session
from src.llm import metrics
from src.llm.client import ChatResult
from src.llm.single_agentic import SingleAgenticTrader


@dataclass
class _FakeClient:
    """Stand-in for OpenAIClient. Returns queued responses; logs calls."""

    responses: list[Any]
    raise_on_call: int | None = None  # raise on the Nth call (0-indexed)
    calls: list[dict] = field(default_factory=list)

    def chat(self, **kwargs) -> ChatResult:
        idx = len(self.calls)
        self.calls.append(kwargs)
        if self.raise_on_call is not None and idx == self.raise_on_call:
            raise RuntimeError("OpenAI all retries failed")
        if not self.responses:
            raise RuntimeError("no fake responses queued")
        return self.responses.pop(0)


def _resp_tools(tool_calls: list[dict]) -> ChatResult:
    """ChatResult that asks for tool calls (no text)."""
    return ChatResult(
        text=None,
        tool_calls=tool_calls,
        usage={
            "prompt_tokens": 1200,
            "completion_tokens": 30,
            "cached_tokens": 1024,
            "total_tokens": 1230,
        },
        model="gpt-4o-mini",
        finish_reason="tool_calls",
    )


def _resp_text(text: str) -> ChatResult:
    """Final assistant text turn (no tool_calls)."""
    return ChatResult(
        text=text,
        tool_calls=[],
        usage={
            "prompt_tokens": 1500,
            "completion_tokens": 50,
            "cached_tokens": 1024,
            "total_tokens": 1550,
        },
        model="gpt-4o-mini",
        finish_reason="stop",
    )


def _tool_call(idx: int, name: str, args: dict) -> dict:
    return {"id": f"call_{idx}", "name": name, "arguments": args}


def _info(
    date: str,
    holdings=None,
    pv: float = 1_000_000_000.0,
    close_t=None,
) -> dict:
    return {
        "date": date,
        "t": 0,
        "cash": pv * 0.05,
        "holdings": holdings
        or [3_200_000, 2_100_000, 6_900_000, 880_000, 3_000_000],
        "portfolio_value": pv,
        "close_t": close_t or [55.5, 90.1, 27.4, 215.2, 62.0],
    }


def test_protocol_runtime_check(synthetic_market_data, tmp_path) -> None:
    """SingleAgenticTrader must satisfy Agent Protocol — contract enforced."""
    fake = _FakeClient(
        responses=[
            _resp_text('{"VCB":0.2,"FPT":0.2,"HPG":0.2,"VIC":0.2,"VNM":0.1}')
        ]
    )
    agent = SingleAgenticTrader(
        synthetic_market_data,
        pd.DataFrame(),
        client=fake,
        audit_log_path=tmp_path / "audit.jsonl",
    )
    assert isinstance(agent, Agent)
    assert agent.name == "single_agentic"


def test_zero_tool_calls_emits_weights_immediately(
    synthetic_market_data, tmp_path
) -> None:
    """LLM may decide it has enough info from the user message alone — then
    it emits text in turn 0 and we exit the loop without dispatching tools."""
    fake = _FakeClient(
        responses=[
            _resp_text('{"VCB":0.3,"FPT":0.2,"HPG":0.1,"VIC":0.2,"VNM":0.1}')
        ]
    )
    agent = SingleAgenticTrader(
        synthetic_market_data,
        pd.DataFrame(),
        client=fake,
        audit_log_path=tmp_path / "a.jsonl",
    )
    obs = np.zeros(56, dtype=np.float32)
    a = agent.decide(obs, _info(synthetic_market_data.dates[0].isoformat()))
    assert len(fake.calls) == 1
    # weights sum = 0.3 + 0.2 + 0.1 + 0.2 + 0.1 = 0.9
    assert a.sum() == pytest.approx(0.9, abs=0.01)


def test_tool_loop_dispatches_and_continues(
    synthetic_market_data, tmp_path
) -> None:
    """LLM asks for get_indicators(VCB) → we dispatch and feed result back →
    LLM emits weights. 2 LLM calls; 1 tool dispatch; tool_call_id round-trips."""
    tc = _tool_call(1, "get_indicators", {"ticker": "VCB"})
    fake = _FakeClient(
        responses=[
            _resp_tools([tc]),
            _resp_text('{"VCB":0.4,"FPT":0.2,"HPG":0.1,"VIC":0.2,"VNM":0.1}'),
        ]
    )
    agent = SingleAgenticTrader(
        synthetic_market_data,
        pd.DataFrame(),
        client=fake,
        audit_log_path=tmp_path / "a.jsonl",
    )
    obs = np.zeros(56, dtype=np.float32)
    a = agent.decide(obs, _info(synthetic_market_data.dates[5].isoformat()))
    assert len(fake.calls) == 2
    # 2nd call must include role=tool message with matching tool_call_id
    second_msgs = fake.calls[1]["messages"]
    tool_msgs = [m for m in second_msgs if m.get("role") == "tool"]
    assert len(tool_msgs) == 1
    assert tool_msgs[0]["tool_call_id"] == "call_1"
    payload = json.loads(tool_msgs[0]["content"])
    assert payload["ticker"] == "VCB"
    # action should be a valid weights vector
    assert 0.0 <= a.sum() <= 1.0


def test_assistant_message_wire_shape(synthetic_market_data, tmp_path) -> None:
    """Assistant turn re-sent to OpenAI must have arguments as JSON STRING
    (not dict) per OpenAI wire format. Easy-to-miss gotcha."""
    tc = _tool_call(1, "get_indicators", {"ticker": "FPT"})
    fake = _FakeClient(
        responses=[
            _resp_tools([tc]),
            _resp_text('{"VCB":0.2,"FPT":0.2,"HPG":0.2,"VIC":0.2,"VNM":0.1}'),
        ]
    )
    agent = SingleAgenticTrader(
        synthetic_market_data,
        pd.DataFrame(),
        client=fake,
        audit_log_path=tmp_path / "a.jsonl",
    )
    agent.decide(
        np.zeros(56, dtype=np.float32),
        _info(synthetic_market_data.dates[5].isoformat()),
    )
    second_msgs = fake.calls[1]["messages"]
    assistant_msgs = [m for m in second_msgs if m.get("role") == "assistant"]
    assert len(assistant_msgs) == 1
    am = assistant_msgs[0]
    assert am["tool_calls"][0]["id"] == "call_1"
    assert am["tool_calls"][0]["type"] == "function"
    args_str = am["tool_calls"][0]["function"]["arguments"]
    assert isinstance(args_str, str)  # not a dict
    assert json.loads(args_str) == {"ticker": "FPT"}


def test_iteration_cap_enforced(synthetic_market_data, tmp_path) -> None:
    """LLM that NEVER stops asking → cap fires at max_iterations.
    Issue #8 acceptance: 'không decision nào > 10 tool calls'."""
    metrics.reset()
    tc = _tool_call(99, "get_indicators", {"ticker": "VCB"})
    # Queue 15 tool-call responses — way more than cap=3
    responses = [_resp_tools([tc]) for _ in range(15)]
    fake = _FakeClient(responses=responses)
    agent = SingleAgenticTrader(
        synthetic_market_data,
        pd.DataFrame(),
        client=fake,
        max_iterations=3,
        audit_log_path=tmp_path / "a.jsonl",
    )
    obs = np.zeros(56, dtype=np.float32)
    a = agent.decide(obs, _info(synthetic_market_data.dates[5].isoformat()))
    # Exactly max_iterations LLM calls, no more
    assert len(fake.calls) == 3
    # Hold-shares fallback emits significant non-zero allocation
    assert a.sum() > 0.5
    snap = metrics.get_snapshot()
    assert snap["parse_failure_reasons"].get("iteration_cap", 0) >= 1


def test_tool_dispatch_error_fed_back_to_llm(
    synthetic_market_data, tmp_path
) -> None:
    """LLM hallucinates 'get_market_cap' → tools.dispatch raises ValueError →
    we feed {'error': ...} back; LLM recovers and emits weights."""
    tc_bad = _tool_call(1, "get_market_cap", {})
    fake = _FakeClient(
        responses=[
            _resp_tools([tc_bad]),
            _resp_text('{"VCB":0.2,"FPT":0.2,"HPG":0.2,"VIC":0.2,"VNM":0.1}'),
        ]
    )
    audit = tmp_path / "a.jsonl"
    agent = SingleAgenticTrader(
        synthetic_market_data,
        pd.DataFrame(),
        client=fake,
        audit_log_path=audit,
    )
    obs = np.zeros(56, dtype=np.float32)
    # Must NOT raise — dispatch error gets converted to tool result string
    agent.decide(obs, _info(synthetic_market_data.dates[5].isoformat()))
    assert len(fake.calls) == 2
    tool_msg = [
        m for m in fake.calls[1]["messages"] if m.get("role") == "tool"
    ][0]
    payload = json.loads(tool_msg["content"])
    assert "error" in payload
    assert "unknown tool" in payload["error"].lower()
    # Audit log must mark the errored tool_call
    lines = audit.read_text().splitlines()
    iter_recs = [
        json.loads(line)
        for line in lines
        if json.loads(line)["event"] == "iteration"
    ]
    assert any(
        tc.get("errored") for rec in iter_recs for tc in rec["tool_calls"]
    )


def test_weekly_cache_skips_llm_within_same_week(
    synthetic_market_data, tmp_path
) -> None:
    """Second decide() within same ISO week reuses cached weights → 0
    additional LLM calls. Mirror PKG-6 cost-control invariant."""
    fake = _FakeClient(
        responses=[
            _resp_text('{"VCB":0.3,"FPT":0.2,"HPG":0.1,"VIC":0.2,"VNM":0.1}')
        ]
    )
    agent = SingleAgenticTrader(
        synthetic_market_data,
        pd.DataFrame(),
        client=fake,
        audit_log_path=tmp_path / "a.jsonl",
    )
    obs = np.zeros(56, dtype=np.float32)
    a1 = agent.decide(obs, _info(synthetic_market_data.dates[0].isoformat()))
    a2 = agent.decide(obs, _info(synthetic_market_data.dates[1].isoformat()))
    assert len(fake.calls) == 1
    np.testing.assert_allclose(a1, a2)


def test_iso_week_change_triggers_new_decision(
    synthetic_market_data, tmp_path
) -> None:
    """Date in a different ISO week triggers a fresh decision."""
    fake = _FakeClient(
        responses=[
            _resp_text('{"VCB":0.3,"FPT":0.2,"HPG":0.1,"VIC":0.2,"VNM":0.1}'),
            _resp_text('{"VCB":0.1,"FPT":0.3,"HPG":0.3,"VIC":0.1,"VNM":0.1}'),
        ]
    )
    agent = SingleAgenticTrader(
        synthetic_market_data,
        pd.DataFrame(),
        client=fake,
        audit_log_path=tmp_path / "a.jsonl",
    )
    obs = np.zeros(56, dtype=np.float32)
    agent.decide(obs, _info(synthetic_market_data.dates[0].isoformat()))
    # synthetic dates start Thu 2025-01-02 = ISO week 1; date[5] = 2025-01-09 = week 2
    agent.decide(obs, _info(synthetic_market_data.dates[5].isoformat()))
    assert len(fake.calls) == 2


def test_parse_failure_falls_back_to_hold_shares(
    synthetic_market_data, tmp_path
) -> None:
    """LLM emits garbage → parser falls back to hold-shares + metric recorded."""
    metrics.reset()
    fake = _FakeClient(responses=[_resp_text("I refuse to give weights.")])
    agent = SingleAgenticTrader(
        synthetic_market_data,
        pd.DataFrame(),
        client=fake,
        audit_log_path=tmp_path / "a.jsonl",
    )
    obs = np.zeros(56, dtype=np.float32)
    a = agent.decide(obs, _info(synthetic_market_data.dates[0].isoformat()))
    assert a.sum() > 0.5
    snap = metrics.get_snapshot()
    assert snap["parse_failure"] >= 1


def test_network_failure_falls_back_to_hold_shares(
    synthetic_market_data, tmp_path
) -> None:
    """RuntimeError from client (after retries exhausted) → hold-shares + metric."""
    metrics.reset()
    fake = _FakeClient(responses=[], raise_on_call=0)
    agent = SingleAgenticTrader(
        synthetic_market_data,
        pd.DataFrame(),
        client=fake,
        audit_log_path=tmp_path / "a.jsonl",
    )
    obs = np.zeros(56, dtype=np.float32)
    a = agent.decide(obs, _info(synthetic_market_data.dates[0].isoformat()))
    assert a.sum() > 0.5
    snap = metrics.get_snapshot()
    # network failures recorded as parse_failure with reason prefix "network_"
    assert any(
        k.startswith("network_") for k in snap["parse_failure_reasons"]
    )


def test_audit_log_contains_iteration_and_decision_records(
    synthetic_market_data, tmp_path
) -> None:
    """JSONL must contain ≥ 1 'iteration' and exactly 1 'decision' record
    per decide() call, with iterations_used + cap_hit + tool_name_counts."""
    tc = _tool_call(1, "get_indicators", {"ticker": "VCB"})
    fake = _FakeClient(
        responses=[
            _resp_tools([tc]),
            _resp_text('{"VCB":0.4,"FPT":0.2,"HPG":0.1,"VIC":0.2,"VNM":0.1}'),
        ]
    )
    audit = tmp_path / "audit.jsonl"
    agent = SingleAgenticTrader(
        synthetic_market_data,
        pd.DataFrame(),
        client=fake,
        audit_log_path=audit,
    )
    obs = np.zeros(56, dtype=np.float32)
    agent.decide(obs, _info(synthetic_market_data.dates[5].isoformat()))

    records = [json.loads(line) for line in audit.read_text().splitlines()]
    events = [r["event"] for r in records]
    assert events.count("iteration") >= 1
    assert events.count("decision") == 1
    decision = next(r for r in records if r["event"] == "decision")
    assert decision["iterations_used"] == 1
    assert decision["cap_hit"] is False
    assert decision["tool_name_counts"] == {"get_indicators": 1}
    assert decision["parse_ok"] is True


def test_audit_log_can_be_disabled(synthetic_market_data, tmp_path) -> None:
    """audit_log_path=None must NOT create any files."""
    fake = _FakeClient(
        responses=[
            _resp_text('{"VCB":0.2,"FPT":0.2,"HPG":0.2,"VIC":0.2,"VNM":0.1}')
        ]
    )
    agent = SingleAgenticTrader(
        synthetic_market_data,
        pd.DataFrame(),
        client=fake,
        audit_log_path=None,
    )
    obs = np.zeros(56, dtype=np.float32)
    agent.decide(obs, _info(synthetic_market_data.dates[0].isoformat()))
    assert not list(tmp_path.glob("**/*.jsonl"))


def test_news_not_pre_injected_into_user_message(
    synthetic_market_data, tmp_path
) -> None:
    """PKG-7 leaves news for the LLM to fetch via get_news tool. The user
    message must NOT mention 'Recent news' section.

    Differs from PKG-6 which pre-filters and serializes news into the prompt.
    """
    md = synthetic_market_data
    pub = (
        pd.to_datetime([md.dates[1].strftime("%Y-%m-%d") + " 09:00"])
        .tz_localize("Asia/Ho_Chi_Minh")
        .tz_convert("UTC")
    )
    news = pd.DataFrame(
        {
            "published_at_utc": pub,
            "source": ["cafef"],
            "url": ["https://x"],
            "title": ["VCB earnings beat"],
            "summary": [None],
            "tickers": [["VCB"]],
        }
    )
    news["available_for_session"] = compute_available_for_session(
        news["published_at_utc"], md.dates
    )
    fake = _FakeClient(
        responses=[
            _resp_text('{"VCB":0.2,"FPT":0.2,"HPG":0.2,"VIC":0.2,"VNM":0.1}')
        ]
    )
    agent = SingleAgenticTrader(
        md, news, client=fake, audit_log_path=tmp_path / "a.jsonl"
    )
    obs = np.zeros(56, dtype=np.float32)
    agent.decide(obs, _info(md.dates[10].isoformat()))
    user_msg = fake.calls[0]["messages"][1]["content"]
    assert "Recent news" not in user_msg
    assert "VCB earnings beat" not in user_msg


def test_weekly_rebalance_false_calls_llm_every_step(
    synthetic_market_data, tmp_path
) -> None:
    """Ablation: disable weekly cache → every decide() calls the LLM."""
    fake = _FakeClient(
        responses=[
            _resp_text(
                '{"VCB":0.2,"FPT":0.2,"HPG":0.2,"VIC":0.2,"VNM":0.1}'
            )
            for _ in range(3)
        ]
    )
    agent = SingleAgenticTrader(
        synthetic_market_data,
        pd.DataFrame(),
        client=fake,
        weekly_rebalance=False,
        audit_log_path=tmp_path / "a.jsonl",
    )
    obs = np.zeros(56, dtype=np.float32)
    for i in range(3):
        agent.decide(
            obs, _info(synthetic_market_data.dates[i].isoformat())
        )
    assert len(fake.calls) == 3
