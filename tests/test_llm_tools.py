"""LookaheadSafeTools invariants — strict-< asof, news visibility, dispatch."""

from __future__ import annotations

import pandas as pd
import pytest

from src import config
from src.data_pipeline.news_align import compute_available_for_session
from src.env_data_loader import MarketData
from src.llm.tools import LookaheadSafeTools


def _news_df(market_data: MarketData) -> pd.DataFrame:
    """Tiny news fixture aligned to the synthetic market calendar."""
    cal = market_data.dates
    pub = pd.to_datetime(
        [
            cal[5].strftime("%Y-%m-%d") + " 10:00",
            cal[10].strftime("%Y-%m-%d") + " 14:00",
            cal[20].strftime("%Y-%m-%d") + " 09:00",
        ]
    ).tz_localize("Asia/Ho_Chi_Minh").tz_convert("UTC")
    df = pd.DataFrame(
        {
            "published_at_utc": pub,
            "source": "cafef",
            "url": ["https://x/1", "https://x/2", "https://x/3"],
            "title": [
                "VCB earnings Q1",
                "FPT contract win",
                "VCB dividend declared",
            ],
            "summary": [None, None, None],
            "tickers": [["VCB"], ["FPT"], ["VCB"]],
        }
    )
    df["available_for_session"] = compute_available_for_session(
        df["published_at_utc"], cal
    )
    return df


def test_get_price_history_strictly_before_asof(synthetic_market_data) -> None:
    """At asof = day 30, every returned row must have date < day-30 — strict
    less-than is the lookahead invariant."""
    md = synthetic_market_data
    asof = md.dates[30]
    tools = LookaheadSafeTools(md, pd.DataFrame(), asof)
    out = tools.get_price_history("VCB", days=10)
    assert len(out["rows"]) == 10
    for row in out["rows"]:
        assert pd.Timestamp(row["date"]) < asof


def test_get_indicators_uses_last_pre_asof_session(synthetic_market_data) -> None:
    """Indicators row date < asof — env state at session T sees only T-1."""
    md = synthetic_market_data
    asof = md.dates[20]
    tools = LookaheadSafeTools(md, pd.DataFrame(), asof)
    out = tools.get_indicators("VCB")
    assert pd.Timestamp(out["as_of_date"]) < asof
    assert set(out["indicators"].keys()) >= {
        "rsi14", "macd", "sma20", "atr14"
    }


def test_get_news_filters_by_visibility(synthetic_market_data) -> None:
    """News from session 5 → available_for_session = session 7. At asof=session 6,
    not visible. At asof=session 7, visible. PRD 'D+1 close' → D+2 open."""
    md = synthetic_market_data
    news = _news_df(md)
    # asof BEFORE first news's available_for_session
    asof_early = md.dates[6]
    tools = LookaheadSafeTools(md, news, asof_early)
    early = tools.get_news()
    # asof AT first news's available_for_session
    asof_late = md.dates[7]
    tools = LookaheadSafeTools(md, news, asof_late)
    late = tools.get_news()
    assert len(late) > len(early)


def test_get_news_filters_by_ticker(synthetic_market_data) -> None:
    """Ticker filter must drop items whose tickers list excludes the request."""
    md = synthetic_market_data
    news = _news_df(md)
    asof = md.dates[40]  # well past all news
    tools = LookaheadSafeTools(md, news, asof)
    fpt_only = tools.get_news(ticker="FPT")
    assert all("FPT" in item["tickers"] for item in fpt_only)
    assert all("VCB" not in item["tickers"] or "FPT" in item["tickers"] for item in fpt_only)


def test_get_fundamentals_quarter_visibility_lag(monkeypatch, synthetic_market_data) -> None:
    """Q2 ends 2025-06-30; visible_from = 2025-07-30. asof 2025-07-15 should
    NOT see Q2; asof 2025-08-01 should see it.

    We patch fetch_fundamentals to a stub so this test stays network-free.
    """
    md = synthetic_market_data
    fake_df = pd.DataFrame(
        {
            "ticker": ["VCB"] * 4,
            "statement": ["income_statement"] * 4,
            "period": ["2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4"],
            "item": ["x"] * 4,
            "item_en": ["X"] * 4,
            "item_id": [1] * 4,
            "value": [100.0, 200.0, 300.0, 400.0],
        }
    )
    monkeypatch.setattr(
        "src.llm.tools.fetch_fundamentals", lambda ticker, refresh=False: fake_df
    )

    asof_july15 = pd.Timestamp("2025-07-15")
    tools = LookaheadSafeTools(md, pd.DataFrame(), asof_july15)
    out = tools.get_fundamentals("VCB")
    assert "2025-Q2" not in out["quarters_available"]
    assert "2025-Q1" in out["quarters_available"]  # Q1 ends Mar-31, visible by Apr-30

    asof_aug1 = pd.Timestamp("2025-08-01")
    tools = LookaheadSafeTools(md, pd.DataFrame(), asof_aug1)
    out = tools.get_fundamentals("VCB")
    assert "2025-Q2" in out["quarters_available"]


def test_dispatch_routes_to_method(synthetic_market_data) -> None:
    """dispatch must call the named method with parsed kwargs."""
    md = synthetic_market_data
    tools = LookaheadSafeTools(md, pd.DataFrame(), md.dates[20])
    out = tools.dispatch("get_price_history", {"ticker": "VCB", "days": 5})
    assert out["ticker"] == "VCB"
    assert len(out["rows"]) == 5


def test_dispatch_rejects_unknown_tool(synthetic_market_data) -> None:
    """LLMs occasionally hallucinate method names — must fail loud, not no-op."""
    md = synthetic_market_data
    tools = LookaheadSafeTools(md, pd.DataFrame(), md.dates[20])
    with pytest.raises(ValueError, match="unknown tool"):
        tools.dispatch("get_market_cap", {})


def test_tool_specs_returns_4_function_specs() -> None:
    """OpenAI tool-spec shape: each entry has type=function + function dict
    with name, description, parameters. PKG-6/7/8 will copy this directly."""
    specs = LookaheadSafeTools.tool_specs()
    assert len(specs) == 4
    names = {s["function"]["name"] for s in specs}
    assert names == {"get_price_history", "get_indicators", "get_news", "get_fundamentals"}
    for s in specs:
        assert s["type"] == "function"
        assert {"name", "description", "parameters"} <= set(s["function"])


def test_unknown_ticker_raises(synthetic_market_data) -> None:
    """Defensive: if LLM hallucinates a ticker (e.g. 'AAPL'), tools must
    raise — caller catches and reports. Silent empty would mislead the agent."""
    md = synthetic_market_data
    tools = LookaheadSafeTools(md, pd.DataFrame(), md.dates[20])
    with pytest.raises(ValueError, match="unknown ticker"):
        tools.get_price_history("AAPL")


def test_universe_tickers_match_config() -> None:
    """tool_specs ticker enum must equal config.TICKERS — single source of truth."""
    specs = LookaheadSafeTools.tool_specs()
    for s in specs:
        props = s["function"]["parameters"].get("properties", {})
        if "ticker" in props:
            assert props["ticker"]["enum"] == list(config.TICKERS)
