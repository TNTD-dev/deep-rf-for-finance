"""ZeroShotTrader invariants — Protocol, weekly cadence, fallbacks, news filter.

Uses synthetic_market_data fixture from conftest + fake OpenAIClient injected
via constructor. No real OpenAI calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from src.agent_base import Agent
from src.data_pipeline.news_align import compute_available_for_session
from src.env_data_loader import MarketData
from src.llm import metrics
from src.llm.client import ChatResult
from src.llm.zero_shot import ZeroShotTrader


@dataclass
class _FakeClient:
    """Stand-in for OpenAIClient. Returns queued responses; logs calls."""

    responses: list[Any]
    raise_next: Exception | None = None

    def __post_init__(self) -> None:
        self.calls: list[dict] = []

    def chat(self, **kwargs) -> ChatResult:
        self.calls.append(kwargs)
        if self.raise_next is not None:
            err = self.raise_next
            self.raise_next = None
            raise err
        if not self.responses:
            raise RuntimeError("no fake responses queued")
        return self.responses.pop(0)


def _resp(text: str) -> ChatResult:
    return ChatResult(
        text=text,
        tool_calls=[],
        usage={"prompt_tokens": 1200, "completion_tokens": 40,
               "cached_tokens": 1024, "total_tokens": 1240},
        model="gpt-4o-mini",
        finish_reason="stop",
    )


def _info(date: str, holdings=None, pv: float = 1_000_000_000.0,
          close_t=None) -> dict:
    return {
        "date": date,
        "t": 0,
        "cash": pv * 0.05,
        "holdings": holdings or [3_200_000, 2_100_000, 6_900_000, 880_000, 3_000_000],
        "portfolio_value": pv,
        "close_t": close_t or [55.5, 90.1, 27.4, 215.2, 62.0],
    }


def _news_aligned(md: MarketData, ticker: str = "VCB") -> pd.DataFrame:
    pub = pd.to_datetime([md.dates[2].strftime("%Y-%m-%d") + " 09:00"]).tz_localize(
        "Asia/Ho_Chi_Minh"
    ).tz_convert("UTC")
    df = pd.DataFrame(
        {
            "published_at_utc": pub,
            "source": ["cafef"],
            "url": ["https://x/1"],
            "title": [f"{ticker} important news"],
            "summary": [None],
            "tickers": [[ticker]],
        }
    )
    df["available_for_session"] = compute_available_for_session(df["published_at_utc"], md.dates)
    return df


def test_protocol_runtime_check(synthetic_market_data) -> None:
    """ZeroShotTrader must satisfy Agent Protocol — keeps contract enforced."""
    fake = _FakeClient(responses=[_resp('{"VCB":0.2,"FPT":0.2,"HPG":0.2,"VIC":0.2,"VNM":0.1}')])
    agent = ZeroShotTrader(synthetic_market_data, pd.DataFrame(), client=fake)
    assert isinstance(agent, Agent)
    assert agent.name == "zero_shot"


def test_first_call_fires_llm_and_caches_weights(synthetic_market_data) -> None:
    """First decide() must call LLM once; second call SAME WEEK reuses cache.

    Without this, cost balloons 5× from daily-rebalance instead of weekly.
    """
    metrics.reset()
    fake = _FakeClient(responses=[_resp('{"VCB":0.3,"FPT":0.2,"HPG":0.1,"VIC":0.2,"VNM":0.1}')])
    agent = ZeroShotTrader(synthetic_market_data, pd.DataFrame(), client=fake)

    obs = np.zeros(56, dtype=np.float32)
    a1 = agent.decide(obs, _info(synthetic_market_data.dates[0].isoformat()))
    a2 = agent.decide(obs, _info(synthetic_market_data.dates[1].isoformat()))
    assert len(fake.calls) == 1  # only one LLM call
    np.testing.assert_allclose(a1, a2)


def test_iso_week_change_fires_new_llm_call(synthetic_market_data) -> None:
    """Date in a different ISO week triggers a fresh LLM call.

    Without this, the 248-session loop never calls LLM beyond the first week.
    """
    fake = _FakeClient(
        responses=[
            _resp('{"VCB":0.3,"FPT":0.2,"HPG":0.1,"VIC":0.2,"VNM":0.1}'),
            _resp('{"VCB":0.1,"FPT":0.3,"HPG":0.3,"VIC":0.1,"VNM":0.1}'),
        ]
    )
    agent = ZeroShotTrader(synthetic_market_data, pd.DataFrame(), client=fake)
    obs = np.zeros(56, dtype=np.float32)

    # synthetic dates start Mon 2025-01-02 = ISO week 1, business days
    # date[0] = 2025-01-02 (Thu, week 1), date[5] = 2025-01-09 (Thu, week 2)
    agent.decide(obs, _info(synthetic_market_data.dates[0].isoformat()))
    agent.decide(obs, _info(synthetic_market_data.dates[5].isoformat()))
    assert len(fake.calls) == 2


def test_parse_failure_falls_back_to_hold_shares(synthetic_market_data) -> None:
    """LLM returns garbage → parse_failure metric + hold-shares weights.

    Hold-shares = holdings × close_t / pv (approximately current portfolio
    composition), NOT zero — zero would trigger panic-sell.
    """
    metrics.reset()
    fake = _FakeClient(responses=[_resp("I cannot help with this request.")])
    agent = ZeroShotTrader(synthetic_market_data, pd.DataFrame(), client=fake)
    obs = np.zeros(56, dtype=np.float32)
    info = _info(synthetic_market_data.dates[0].isoformat())
    action = agent.decide(obs, info)
    assert action.sum() > 0.5  # significant non-zero allocation (hold-shares)
    snap = metrics.get_snapshot()
    assert snap["parse_failure"] >= 1


def test_network_failure_falls_back_to_hold_shares(synthetic_market_data) -> None:
    """RuntimeError from client (after retries exhausted) → hold-shares.

    Critical: a single network burst must not crash a 248-session backtest.
    """
    metrics.reset()
    fake = _FakeClient(responses=[], raise_next=RuntimeError("OpenAI all retries failed"))
    agent = ZeroShotTrader(synthetic_market_data, pd.DataFrame(), client=fake)
    obs = np.zeros(56, dtype=np.float32)
    info = _info(synthetic_market_data.dates[0].isoformat())
    action = agent.decide(obs, info)
    assert action.sum() > 0.5
    snap = metrics.get_snapshot()
    # network failures recorded as parse_failure with reason prefix "network_"
    reasons = snap["parse_failure_reasons"]
    assert any(r.startswith("network_") for r in reasons)


def test_weekly_rebalance_false_calls_llm_every_step(synthetic_market_data) -> None:
    """Toggle disables the weekly cache — every decide() calls LLM. Used for
    ablation studies where we want daily decisions."""
    fake = _FakeClient(
        responses=[_resp('{"VCB":0.2,"FPT":0.2,"HPG":0.2,"VIC":0.2,"VNM":0.1}') for _ in range(3)]
    )
    agent = ZeroShotTrader(
        synthetic_market_data, pd.DataFrame(), client=fake, weekly_rebalance=False
    )
    obs = np.zeros(56, dtype=np.float32)
    for i in range(3):
        agent.decide(obs, _info(synthetic_market_data.dates[i].isoformat()))
    assert len(fake.calls) == 3


def test_news_filtered_to_universe_before_prompt(synthetic_market_data) -> None:
    """Off-universe news (e.g. VCS) must NOT appear in the user message —
    we filter inside the agent, not in serialize, because serialize is generic.
    """
    md = synthetic_market_data
    # Build news with VCS-only ticker
    pub = pd.to_datetime([md.dates[1].strftime("%Y-%m-%d") + " 09:00"]).tz_localize(
        "Asia/Ho_Chi_Minh"
    ).tz_convert("UTC")
    news = pd.DataFrame(
        {
            "published_at_utc": pub,
            "source": ["cafef"], "url": ["https://x"],
            "title": ["VICOSTONE off-universe ticker"],
            "summary": [None], "tickers": [["VCS"]],
        }
    )
    news["available_for_session"] = compute_available_for_session(
        news["published_at_utc"], md.dates
    )
    fake = _FakeClient(
        responses=[_resp('{"VCB":0.2,"FPT":0.2,"HPG":0.2,"VIC":0.2,"VNM":0.1}')]
    )
    agent = ZeroShotTrader(md, news, client=fake)
    obs = np.zeros(56, dtype=np.float32)
    # Use late date so the VCS news is "visible" — we want to assert
    # filter happens DESPITE visibility
    agent.decide(obs, _info(md.dates[10].isoformat()))
    user_msg = fake.calls[0]["messages"][1]["content"]
    assert "VICOSTONE" not in user_msg


def test_decide_uses_temperature_zero(synthetic_market_data) -> None:
    """temperature=0 keeps LLM responses near-deterministic. If a future
    refactor passes temp > 0, reproducibility (PRD §15 §5) breaks."""
    fake = _FakeClient(
        responses=[_resp('{"VCB":0.2,"FPT":0.2,"HPG":0.2,"VIC":0.2,"VNM":0.1}')]
    )
    agent = ZeroShotTrader(synthetic_market_data, pd.DataFrame(), client=fake)
    agent.decide(
        np.zeros(56, dtype=np.float32),
        _info(synthetic_market_data.dates[0].isoformat()),
    )
    assert fake.calls[0]["temperature"] == 0.0
    assert fake.calls[0]["model"] == "gpt-4o-mini"


def test_model_override_respects_whitelist(synthetic_market_data, monkeypatch) -> None:
    """Custom model arg flows to client.chat. Whitelist enforcement happens
    in OpenAIClient (PKG-5), not here — agent layer trusts client."""
    fake = _FakeClient(
        responses=[_resp('{"VCB":0.2,"FPT":0.2,"HPG":0.2,"VIC":0.2,"VNM":0.1}')]
    )
    agent = ZeroShotTrader(
        synthetic_market_data, pd.DataFrame(), model="gpt-4o", client=fake
    )
    agent.decide(
        np.zeros(56, dtype=np.float32),
        _info(synthetic_market_data.dates[0].isoformat()),
    )
    assert fake.calls[0]["model"] == "gpt-4o"
