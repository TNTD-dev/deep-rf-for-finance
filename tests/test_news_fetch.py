"""vnstock news wrapper — schema lock + empty/error handling."""

from __future__ import annotations

import pandas as pd
import pytest

from src.data_pipeline.news_fetch import (
    _VNSTOCK_OUT_SCHEMA,
    _normalize,
    fetch_vnstock_news,
)


def _fake_vnstock_news(n: int = 3) -> pd.DataFrame:
    """Mirror real Company.news output: 21 cols, key fields populated."""
    return pd.DataFrame(
        {
            "public_date": [
                "2025-09-05T14:30:00",
                "2025-10-15T09:00:00",
                "2026-01-20T16:00:00",
            ][:n],
            "news_title": [f"VCB news headline {i}" for i in range(n)],
            "news_short_content": [
                "VCB short content body 1",
                "",  # empty → None
                "VCB short content body 3",
            ][:n],
            "news_source_link": ["https://x.com/1", "", None][:n],
            "ticker": ["VCB"] * n,
        }
    )


def test_normalize_schema() -> None:
    """Output columns must match _VNSTOCK_OUT_SCHEMA exactly."""
    df = _normalize(_fake_vnstock_news(), ticker="VCB")
    assert df.columns.tolist() == _VNSTOCK_OUT_SCHEMA
    assert df["source"].unique().tolist() == ["vnstock"]
    assert df["published_at_utc"].dt.tz is not None  # tz-aware UTC


def test_normalize_raises_on_missing_column() -> None:
    """vnstock schema drift must trip the invariant, not silent-degrade."""
    raw = _fake_vnstock_news().drop(columns=["news_title"])
    with pytest.raises(ValueError, match="schema missing"):
        _normalize(raw, ticker="VCB")


def test_normalize_converts_empty_url_and_summary_to_missing() -> None:
    """vnstock returns '' for missing URL/summary; we want a missing value
    (NaN/None) for clean parquet semantics. We assert via pd.isna because
    pandas object-Series `.where(..., None)` stores NaN, not literal None.
    """
    df = _normalize(_fake_vnstock_news(n=3), ticker="VCB")
    assert pd.isna(df["url"].iloc[1])  # was empty string
    assert pd.isna(df["url"].iloc[2])  # was None
    assert pd.isna(df["summary"].iloc[1])  # was empty string
    # Non-empty values still pass through unchanged
    assert df["url"].iloc[0] == "https://x.com/1"


def test_normalize_tickers_is_list_of_one_per_row() -> None:
    """Each row gets `[ticker]` — list, not scalar. Parquet needs list dtype."""
    df = _normalize(_fake_vnstock_news(), ticker="VCB")
    assert all(isinstance(v, list) and v == ["VCB"] for v in df["tickers"])


def test_fetch_raises_on_empty_response(monkeypatch) -> None:
    """Empty response = data outage. Must raise, not return empty DataFrame."""

    class _FakeCompany:
        def __init__(self, source: str, symbol: str) -> None:
            pass

        def news(self) -> pd.DataFrame:
            return pd.DataFrame()

    monkeypatch.setattr("src.data_pipeline.news_fetch.Company", _FakeCompany)
    with pytest.raises(RuntimeError, match="empty Company.news"):
        fetch_vnstock_news("VCB")
