"""Indicator correctness + cross-ticker isolation.

We test shape (NaN warm-up, leak isolation, columns present) rather than exact
golden values, because `ta` has changed default smoothing schemes across minor
versions and we pin loosely (`ta>=0.11`). Shape-based tests still catch the
bug classes that actually matter for backtest validity.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.data_pipeline.indicators import (
    INDICATOR_COLS,
    RSI_WINDOW,
    apply_indicators,
)


def _two_ticker_30d() -> pd.DataFrame:
    """30 business days × 2 tickers. AAA trends up, BBB stays flat."""
    dates = pd.date_range("2024-01-02", periods=30, freq="B")
    a = pd.DataFrame(
        {
            "date": dates,
            "ticker": "AAA",
            "open": np.linspace(100, 130, 30),
            "high": np.linspace(101, 131, 30),
            "low": np.linspace(99, 129, 30),
            "close": np.linspace(100, 130, 30),
            "volume": [1000] * 30,
        }
    )
    b = a.copy()
    b["ticker"] = "BBB"
    b[["open", "high", "low", "close"]] = 50.0
    return pd.concat([a, b], ignore_index=True)


def test_indicator_columns_present() -> None:
    """All 9 indicator columns must appear after apply_indicators."""
    out = apply_indicators(_two_ticker_30d())
    assert set(INDICATOR_COLS).issubset(out.columns)


def test_warmup_period_is_nan() -> None:
    """First (window-1) rows of RSI must be NaN. Env warm-up depends on this.

    If a future patch silently fillna-s warmup, agents would receive fabricated
    values for the first 13 sessions of the test period — silent lookahead.
    """
    out = apply_indicators(_two_ticker_30d())
    first_aaa = out[out["ticker"] == "AAA"].head(RSI_WINDOW - 1)
    assert first_aaa["rsi14"].isna().all()


def test_cross_ticker_isolation() -> None:
    """SMA20 of AAA when run with BBB must equal SMA20 if AAA were alone.

    The most likely bug here is a groupby misuse where ticker B's data leaks
    into ticker A's rolling window. This test catches it directly.
    """
    full = _two_ticker_30d()
    both = apply_indicators(full)
    alone = apply_indicators(full[full["ticker"] == "AAA"].copy())
    a_both = both[both["ticker"] == "AAA"].reset_index(drop=True)
    pd.testing.assert_series_equal(
        a_both["sma20"], alone["sma20"], check_names=False
    )


def test_flat_series_rsi_is_constant() -> None:
    """On a flat price series RSI must be CONSTANT across the late period.

    The exact value is a `ta`-library detail (currently 100 because zero
    losses → division by zero → ceiling), but we don't care which constant.
    We care that BBB's RSI doesn't get contaminated by AAA's uptrend — if
    cross-ticker leakage were happening, BBB's RSI would drift.
    """
    out = apply_indicators(_two_ticker_30d())
    b_rsi_late = out[(out["ticker"] == "BBB") & (out["date"] >= "2024-02-01")][
        "rsi14"
    ].dropna()
    assert not b_rsi_late.empty
    assert b_rsi_late.nunique() == 1, (
        f"flat-series RSI drifted (cross-ticker leak?): {b_rsi_late.tolist()}"
    )
