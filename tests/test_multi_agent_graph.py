"""Graph wiring + node invocation invariants.

Uses _FakeClient (mirror PKG-7) + stubbed prompt loader. No real OpenAI
calls. No real disk writes (every test passes tmp_path-ish paths).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd
import pytest

from src.llm.client import ChatResult
from src.llm.multi_agent.graph import build_app
from src.llm.multi_agent.nodes import analysts as A
from src.llm.multi_agent.state import ROLE_NAMES, make_initial_state
from src.llm.tools import LookaheadSafeTools


@dataclass
class _FakeClient:
    responses: list[Any]
    raise_at: int | None = None  # raise on the Nth call (0-indexed)
    calls: list[dict] = field(default_factory=list)

    def chat(self, **kwargs) -> ChatResult:
        idx = len(self.calls)
        self.calls.append(kwargs)
        if self.raise_at is not None and idx == self.raise_at:
            raise RuntimeError("simulated network failure")
        if not self.responses:
            raise RuntimeError("no fake responses queued")
        return self.responses.pop(0)


def _resp(text: str, model: str = "gpt-4o-mini") -> ChatResult:
    return ChatResult(
        text=text,
        tool_calls=[],
        usage={
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "cached_tokens": 0,
            "total_tokens": 120,
        },
        model=model,
        finish_reason="stop",
    )


@pytest.fixture(autouse=True)
def _stub_prompts(monkeypatch):
    """Stub the prompt loader so missing-prompt files don't fail tests.

    NOTE: prompts exist on disk in the repo, but stubbing keeps tests
    fast + isolated from prompt-content drift.
    """
    monkeypatch.setattr(A, "_prompt", lambda role: f"STUB SYSTEM PROMPT: {role}")
    # Researchers/trader/risk/portfolio import _prompt via `from analysts import _prompt`;
    # they captured a reference at import time, so we patch each module's bound name.
    from src.llm.multi_agent.nodes import (
        portfolio_manager,
        researchers,
        risk_manager,
        trader,
    )
    monkeypatch.setattr(
        researchers, "_prompt", lambda role: f"STUB: {role}"
    )
    monkeypatch.setattr(trader, "_prompt", lambda role: f"STUB: {role}")
    monkeypatch.setattr(
        risk_manager, "_prompt", lambda role: f"STUB: {role}"
    )
    monkeypatch.setattr(
        portfolio_manager, "_prompt", lambda role: f"STUB: {role}"
    )


def _info(md, idx: int = 5) -> dict:
    return {
        "date": str(md.dates[idx]),
        "t": idx,
        "cash": 5e7,
        "holdings": [3_200_000, 2_100_000, 6_900_000, 880_000, 3_000_000],
        "portfolio_value": 1_000_000_000.0,
        "close_t": [55.5, 90.1, 27.4, 215.2, 62.0],
    }


def _initial(md, client, debate_rounds_max: int = 2):
    tools = LookaheadSafeTools(md, pd.DataFrame(), md.dates[5])
    models = {role: "gpt-4o-mini" for role in ROLE_NAMES}
    return make_initial_state(
        market_data=md,
        news_data=pd.DataFrame(),
        info=_info(md),
        client=client,
        models=models,
        tools=tools,
        debate_rounds_max=debate_rounds_max,
    )


def test_graph_compiles():
    app = build_app()
    assert app is not None


def test_full_traversal_happy_path(synthetic_market_data):
    """All 8 roles execute in order; 10 LLM calls fire (3 analysts + 4 debate
    + trader + risk + portfolio_manager); final state has portfolio_manager_output."""
    md = synthetic_market_data
    responses = [_resp(f"out_{i}") for i in range(9)] + [
        _resp('{"VCB":0.2,"FPT":0.2,"HPG":0.2,"VIC":0.2,"VNM":0.1}')
    ]
    fake = _FakeClient(responses=responses)
    app = build_app()
    final = app.invoke(_initial(md, fake))
    assert len(fake.calls) == 10
    assert final["debate_round"] == 2
    assert len(final["transcript"]) == 10
    assert final["portfolio_manager_output"].startswith("{")
    assert final.get("node_errors", []) == []


def test_debate_cap_2_rounds_default(synthetic_market_data):
    """Over-supply queue with 15 responses; verify only 10 consumed (cap fires)."""
    md = synthetic_market_data
    fake = _FakeClient(responses=[_resp(f"out_{i}") for i in range(15)])
    app = build_app()
    final = app.invoke(_initial(md, fake, debate_rounds_max=2))
    assert len(fake.calls) == 10  # not 12, 14, etc.
    assert final["debate_round"] == 2


def test_debate_cap_1_round_when_configured(synthetic_market_data):
    """debate_rounds_max=1 → 2 debate calls only → 3+2+3 = 8 total LLM calls."""
    md = synthetic_market_data
    fake = _FakeClient(responses=[_resp(f"out_{i}") for i in range(15)])
    app = build_app()
    final = app.invoke(_initial(md, fake, debate_rounds_max=1))
    assert len(fake.calls) == 8  # 3 analysts + 2 debate + 3 synthesis
    assert final["debate_round"] == 1


def test_node_failure_records_error_and_continues(synthetic_market_data):
    """Bullish round 0 fails (call idx=3); downstream nodes still run + final state has portfolio_manager_output."""
    md = synthetic_market_data
    # Queue 10 responses but raise on idx=3 (bullish round 0)
    fake = _FakeClient(
        responses=[_resp(f"out_{i}") for i in range(10)],
        raise_at=3,
    )
    app = build_app()
    final = app.invoke(_initial(md, fake))
    # Bull-r0 failed but graph continued; bearish r0 ran, then loop, then trader chain
    errors = final.get("node_errors", [])
    assert any(e["role"] == "bullish_researcher" for e in errors)
    # debate_round still advances (bearish increments unconditionally)
    assert final["debate_round"] == 2
    # Portfolio manager still ran (queue had 10 responses; raise_at=3 means
    # idx=3 raises and pops nothing → 9 responses consumed by the other 9 successful calls)
    assert "portfolio_manager_output" in final


def test_streaming_yields_one_event_per_node_visit(synthetic_market_data):
    """app.stream(stream_mode='updates') yields one event per node execution.
    For cap=2: 3 analysts + 4 debate + 3 synthesis = 10 events."""
    md = synthetic_market_data
    fake = _FakeClient(responses=[_resp(f"out_{i}") for i in range(10)])
    app = build_app()
    events = list(app.stream(_initial(md, fake), stream_mode="updates"))
    assert len(events) == 10
    visited = [list(e.keys())[0] for e in events]
    assert visited == [
        "technical_analyst",
        "news_sentiment_analyst",
        "fundamental_analyst",
        "bullish_researcher",
        "bearish_researcher",
        "bullish_researcher",
        "bearish_researcher",
        "trader",
        "risk_manager",
        "portfolio_manager",
    ]


def test_analysts_use_their_configured_models(synthetic_market_data):
    """Each analyst LLM call must use the model assigned in state['models']
    for that role — verifies the mixed-model lineup wiring."""
    md = synthetic_market_data
    fake = _FakeClient(responses=[_resp(f"out_{i}") for i in range(10)])
    tools = LookaheadSafeTools(md, pd.DataFrame(), md.dates[5])
    # Custom assignment to detect mis-wiring
    models = {
        "technical_analyst": "gpt-4o-mini",
        "news_sentiment_analyst": "gpt-4o-mini",
        "fundamental_analyst": "gpt-4o-mini",
        "bullish_researcher": "gpt-4o",
        "bearish_researcher": "gpt-4o",
        "trader": "gpt-4o",
        "risk_manager": "gpt-4o",
        "portfolio_manager": "gpt-4o",
    }
    initial = make_initial_state(
        market_data=md, news_data=pd.DataFrame(),
        info=_info(md), client=fake, models=models, tools=tools,
        debate_rounds_max=2,
    )
    build_app().invoke(initial)
    # Calls 0,1,2 = analysts (mini); 3-6 = debate (4o); 7,8,9 = trader/risk/portfolio (4o)
    assert fake.calls[0]["model"] == "gpt-4o-mini"
    assert fake.calls[1]["model"] == "gpt-4o-mini"
    assert fake.calls[2]["model"] == "gpt-4o-mini"
    assert fake.calls[3]["model"] == "gpt-4o"
    assert fake.calls[7]["model"] == "gpt-4o"
    assert fake.calls[9]["model"] == "gpt-4o"


def test_nodes_pass_max_retries_2(synthetic_market_data):
    """Each node calls client.chat with max_retries=2 (advisor: cap per-call
    wallclock so 10 sequential calls fit in 30s decision budget)."""
    md = synthetic_market_data
    fake = _FakeClient(responses=[_resp(f"out_{i}") for i in range(10)])
    build_app().invoke(_initial(md, fake))
    for i, call in enumerate(fake.calls):
        assert call.get("max_retries") == 2, f"call {i} missing max_retries=2"


def test_portfolio_manager_output_is_raw_string(synthetic_market_data):
    """portfolio_manager_output must be raw text (not pre-parsed) so
    MultiAgentTrader owns the parser interaction (D9)."""
    md = synthetic_market_data
    responses = [_resp(f"out_{i}") for i in range(9)] + [
        _resp('{"VCB": 0.2, "FPT": 0.2, "HPG": 0.2, "VIC": 0.2, "VNM": 0.1}')
    ]
    fake = _FakeClient(responses=responses)
    final = build_app().invoke(_initial(md, fake))
    assert isinstance(final["portfolio_manager_output"], str)
    assert "VCB" in final["portfolio_manager_output"]


def test_tools_pre_fetched_python_side(synthetic_market_data):
    """Analyst nodes call LookaheadSafeTools methods directly (D8: Python-side,
    not LLM tool_calls). Wrap tools to track method calls."""
    md = synthetic_market_data
    real_tools = LookaheadSafeTools(md, pd.DataFrame(), md.dates[5])
    call_log: list[str] = []

    class _SpyTools:
        def __init__(self, inner):
            self._inner = inner

        def __getattr__(self, name):
            attr = getattr(self._inner, name)
            if callable(attr):
                def spy(*a, **kw):
                    call_log.append(name)
                    return attr(*a, **kw)
                return spy
            return attr

    fake = _FakeClient(responses=[_resp(f"out_{i}") for i in range(10)])
    models = {role: "gpt-4o-mini" for role in ROLE_NAMES}
    initial = make_initial_state(
        market_data=md, news_data=pd.DataFrame(),
        info=_info(md), client=fake, models=models,
        tools=_SpyTools(real_tools),
        debate_rounds_max=2,
    )
    build_app().invoke(initial)
    # Technical analyst should have called get_indicators 5x, get_price_history 5x
    assert call_log.count("get_indicators") == 5
    assert call_log.count("get_price_history") == 5
    # News analyst calls get_news once (single call, all tickers in 1 LLM call)
    assert call_log.count("get_news") == 1
    # Fundamental analyst calls get_fundamentals 5x
    assert call_log.count("get_fundamentals") == 5
