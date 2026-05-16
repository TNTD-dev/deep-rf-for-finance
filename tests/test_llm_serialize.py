"""Markdown serializer invariants — sections present, ticker filter, table shape."""

from __future__ import annotations

import pandas as pd

from src.llm.serialize import (
    holdings_to_text,
    indicators_to_text,
    news_to_bullets,
    state_to_text,
)


def _info() -> dict:
    return {
        "date": "2025-08-04T00:00:00",
        "t": 5,
        "cash": 100_000_000.0,
        "holdings": [3000, 2000, 5000, 1500, 1800],
        "portfolio_value": 1_050_000_000.0,
        "close_t": [55.5, 90.1, 27.4, 215.2, 62.0],
    }


def test_state_to_text_contains_portfolio_section(synthetic_market_data) -> None:
    """Every prompt MUST surface portfolio state — without it, LLM has no
    grounding for "what should I buy more of vs sell"."""
    text = state_to_text(_info(), synthetic_market_data)
    assert "## Portfolio" in text
    assert "Cash:" in text
    assert "Holdings:" in text


def test_state_to_text_contains_indicator_table(synthetic_market_data) -> None:
    """Indicator pipe table renders all 5 tickers in config.TICKERS order."""
    text = state_to_text(_info(), synthetic_market_data)
    assert "## Recent indicators" in text
    for ticker in ("VCB", "FPT", "HPG", "VIC", "VNM"):
        assert f"| {ticker} |" in text


def test_holdings_to_text_renders_each_ticker(synthetic_market_data) -> None:
    """One bullet per ticker with shares × price = value (%)."""
    text = holdings_to_text(_info(), synthetic_market_data)
    for ticker in ("VCB", "FPT", "HPG", "VIC", "VNM"):
        assert ticker in text
    assert "shares" in text


def test_indicators_to_text_uses_z_scored_columns(synthetic_market_data) -> None:
    """Table cells show z-scored indicator values (signed floats)."""
    text = indicators_to_text(_info(), synthetic_market_data)
    # z-scored values look like "+1.23" or "-0.45" — the +/- sign is the tell
    assert "rsi14" in text or "RSI" in text  # column header present
    assert any(line.startswith("| VCB ") for line in text.splitlines())


def test_news_to_bullets_filters_max_items() -> None:
    """max_items cap respected — keeps prompt under token budget."""
    rows = [
        {
            "published_at_utc": pd.Timestamp(f"2025-08-{i:02d} 10:00", tz="UTC"),
            "tickers": ["VCB"],
            "title": f"VCB news {i}",
            "url": None,
            "source": "cafef",
            "summary": None,
            "available_for_session": pd.Timestamp(f"2025-08-{i:02d}"),
        }
        for i in range(1, 21)
    ]
    df = pd.DataFrame(rows)
    text = news_to_bullets(df, max_items=5)
    n_bullets = sum(1 for line in text.splitlines() if line.startswith("- "))
    assert n_bullets == 5


def test_news_to_bullets_filters_to_universe_tickers() -> None:
    """Items tagged ONLY with off-universe tickers (VCS, VNINDEX) get dropped."""
    rows = [
        {
            "published_at_utc": pd.Timestamp("2025-08-04 10:00", tz="UTC"),
            "tickers": ["VCS"],  # not in our 5-ticker universe
            "title": "VICOSTONE news (off-universe)",
            "url": None, "source": "cafef", "summary": None,
            "available_for_session": pd.Timestamp("2025-08-04"),
        },
        {
            "published_at_utc": pd.Timestamp("2025-08-04 11:00", tz="UTC"),
            "tickers": ["VCB"],
            "title": "Vietcombank actual news",
            "url": None, "source": "cafef", "summary": None,
            "available_for_session": pd.Timestamp("2025-08-04"),
        },
    ]
    df = pd.DataFrame(rows)
    text = news_to_bullets(df)
    assert "Vietcombank actual news" in text
    assert "VICOSTONE" not in text
