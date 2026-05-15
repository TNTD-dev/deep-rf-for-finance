"""PKG-1 acceptance — schema, retry/fallback, NaN-free.

Network is mocked. Real-network checks live in `scripts/fetch_data.py` and
the day-1 spike output captured in the PR description.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.data_pipeline.vnstock_prices import _SCHEMA, _normalize, fetch_prices


def _fake_quote_df(n: int = 10) -> pd.DataFrame:
    """Mirror real vnstock output: `time` column with 07:00:00 time-of-day."""
    return pd.DataFrame(
        {
            "time": pd.date_range("2024-06-03 07:00:00", periods=n, freq="B"),
            "open": [100.0 + i for i in range(n)],
            "high": [101.0 + i for i in range(n)],
            "low": [99.0 + i for i in range(n)],
            "close": [100.5 + i for i in range(n)],
            "volume": [1000 * (i + 1) for i in range(n)],
        }
    )


def test_normalize_schema() -> None:
    """Output columns must match the contract; downstream code relies on this."""
    df = _normalize(_fake_quote_df(), ticker="VCB")
    assert df.columns.tolist() == _SCHEMA
    assert df["ticker"].unique().tolist() == ["VCB"]
    assert df["date"].is_monotonic_increasing


def test_normalize_strips_time_of_day() -> None:
    """vnstock returns datetime with 07:00:00; we store date-only.

    If time-of-day leaks through, downstream date-equality checks (e.g. joining
    with news by date) will silently miss matches.
    """
    df = _normalize(_fake_quote_df(), ticker="VCB")
    first_ts = pd.Timestamp(df["date"].iloc[0])
    assert first_ts.hour == 0
    assert first_ts.minute == 0


def test_normalize_raises_on_nan_close() -> None:
    """A NaN close means data is corrupt — must fail loud (CLAUDE.md Rule 12)."""
    raw = _fake_quote_df()
    raw.loc[3, "close"] = pd.NA
    with pytest.raises(ValueError, match="NaN in close"):
        _normalize(raw, ticker="VCB")


def test_normalize_raises_on_missing_column() -> None:
    """Schema drift in vnstock must trip the invariant, not silent-degrade."""
    raw = _fake_quote_df().drop(columns=["volume"])
    with pytest.raises(ValueError, match="schema missing"):
        _normalize(raw, ticker="VCB")


def test_fetch_prices_fallback_to_vci(monkeypatch) -> None:
    """KBS failure must trigger VCI; otherwise we'd have a silent SPOF on KBS."""
    calls: list[str] = []

    class _FakeQuote:
        def __init__(self, symbol: str, source: str) -> None:
            calls.append(source)
            self.source = source

        def history(self, **kwargs) -> pd.DataFrame:
            if self.source == "kbs":
                raise RuntimeError("simulated KBS down")
            return _fake_quote_df()

    monkeypatch.setattr("src.data_pipeline.vnstock_prices.Quote", _FakeQuote)
    df = fetch_prices("VCB", "2024-06-01", "2024-06-15")
    assert calls == ["kbs", "vci"]
    assert df["ticker"].iloc[0] == "VCB"


def test_fetch_prices_raises_when_all_sources_fail(monkeypatch) -> None:
    """Both sources down → loud raise, not empty DataFrame."""

    class _FakeQuote:
        def __init__(self, symbol: str, source: str) -> None:
            pass

        def history(self, **kwargs) -> pd.DataFrame:
            raise RuntimeError("simulated outage")

    monkeypatch.setattr("src.data_pipeline.vnstock_prices.Quote", _FakeQuote)
    with pytest.raises(RuntimeError, match="all sources failed"):
        fetch_prices("VCB", "2024-06-01", "2024-06-15")


def test_fetch_prices_empty_response_treated_as_failure(monkeypatch) -> None:
    """An empty DataFrame from one source must fall over, not propagate."""

    class _FakeQuote:
        def __init__(self, symbol: str, source: str) -> None:
            self.source = source

        def history(self, **kwargs) -> pd.DataFrame:
            if self.source == "kbs":
                return pd.DataFrame()
            return _fake_quote_df()

    monkeypatch.setattr("src.data_pipeline.vnstock_prices.Quote", _FakeQuote)
    df = fetch_prices("VCB", "2024-06-01", "2024-06-15")
    assert len(df) > 0
