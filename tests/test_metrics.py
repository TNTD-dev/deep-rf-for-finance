"""Golden-value tests for src/eval/metrics.py.

Tests cover:
- degenerate inputs (empty, single-point, flat) return 0.0 not NaN
- hand-computed expected values for non-trivial inputs
- turnover + total_cost integration with realistic DataFrame shapes
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from src import config
from src.eval import metrics as M

# ---------- log_returns ------------------------------------------------------


def test_log_returns_handles_short_series() -> None:
    assert M.log_returns(np.array([1.0])).size == 0
    assert M.log_returns(np.array([])).size == 0


def test_log_returns_basic() -> None:
    r = M.log_returns(np.array([1.0, math.e, math.e**2]))
    assert np.allclose(r, [1.0, 1.0])


# ---------- cumulative_return ------------------------------------------------


def test_cumulative_return_basic() -> None:
    assert M.compute_cumulative_return(np.array([1.0, 1.1, 1.21])) == pytest.approx(0.21)


def test_cumulative_return_zero_for_flat_series() -> None:
    assert M.compute_cumulative_return(np.array([1.0, 1.0, 1.0])) == 0.0


# ---------- sharpe -----------------------------------------------------------


def test_sharpe_positive_for_uptrend() -> None:
    # Synthetic ~0.1% daily return + tiny noise (so std > 0)
    rng = np.random.default_rng(0)
    daily = 0.001 + rng.normal(0, 0.001, size=200)
    pv = np.cumprod(1 + daily) * 1_000_000_000
    assert M.compute_sharpe(pv) > 0.5


def test_sharpe_zero_for_flat_series() -> None:
    assert M.compute_sharpe(np.array([1.0] * 50)) == 0.0


def test_sharpe_zero_for_empty_series() -> None:
    assert M.compute_sharpe(np.array([])) == 0.0


# ---------- sortino ----------------------------------------------------------


def test_sortino_only_penalizes_downside() -> None:
    # Mixed up/down series with non-identical downside magnitudes (else
    # neg-only std = 0 and degenerate-case triggers).
    pv = np.array([1.00, 1.05, 1.03, 1.10, 1.07, 1.15, 1.12, 1.20])
    sharpe = M.compute_sharpe(pv)
    sortino = M.compute_sortino(pv)
    assert sharpe > 0
    assert sortino > 0
    # Net uptrend with mild dips: downside-std (subset) < total-std (mix of
    # large positives + small negatives) → Sortino > Sharpe.
    assert sortino > sharpe


def test_sortino_zero_for_monotonic_uptrend() -> None:
    # No negative returns → Sortino = 0 (by our degenerate-case rule)
    assert M.compute_sortino(np.array([1.0, 1.01, 1.02, 1.03])) == 0.0


# ---------- max_drawdown -----------------------------------------------------


def test_max_drawdown_basic() -> None:
    # peak=1.5 at idx 1, trough=0.5 at idx 2 → dd = (1.5-0.5)/1.5 = 2/3
    pv = np.array([1.0, 1.5, 0.5, 1.2])
    assert M.compute_max_drawdown(pv) == pytest.approx(2.0 / 3.0)


def test_max_drawdown_zero_for_monotonic_uptrend() -> None:
    assert M.compute_max_drawdown(np.array([1.0, 1.1, 1.2, 1.3])) == 0.0


def test_max_drawdown_zero_for_empty() -> None:
    assert M.compute_max_drawdown(np.array([])) == 0.0


# ---------- turnover ---------------------------------------------------------


def _portfolio_curve(weights: np.ndarray) -> pd.DataFrame:
    """Build a minimal portfolio_curve DataFrame for turnover tests."""
    n_rows = weights.shape[0]
    df = pd.DataFrame(
        {
            "date": pd.date_range("2025-01-01", periods=n_rows, freq="D"),
            "agent_name": "x",
            "portfolio_value": 1.0,
            "cash": 0.0,
        }
    )
    for i, t in enumerate(config.TICKERS):
        df[f"w_{t}"] = weights[:, i]
    return df


def test_turnover_zero_for_buy_and_hold_after_init() -> None:
    n_t = len(config.TICKERS)
    w = np.full((5, n_t), 1.0 / n_t)  # constant weights → no churn
    assert M.compute_turnover(_portfolio_curve(w)) == 0.0


def test_turnover_positive_for_rebalance_pattern() -> None:
    n_t = len(config.TICKERS)
    w = np.zeros((4, n_t))
    w[0] = [0.2] * n_t
    w[1] = [0.4, 0.0, 0.2, 0.2, 0.2]  # delta sum = 0.4
    w[2] = [0.2] * n_t  # delta sum = 0.4
    w[3] = [0.2] * n_t  # delta sum = 0.0
    # mean of [0.4, 0.4, 0.0] = 0.2666...
    assert M.compute_turnover(_portfolio_curve(w)) == pytest.approx((0.4 + 0.4 + 0.0) / 3.0)


def test_turnover_missing_columns_returns_zero() -> None:
    df = pd.DataFrame({"date": [pd.Timestamp("2025-01-01")], "portfolio_value": [1.0]})
    assert M.compute_turnover(df) == 0.0


# ---------- total_cost -------------------------------------------------------


@dataclass(frozen=True)
class _FakeMD:
    dates: object
    close: np.ndarray


def test_total_cost_buy_only_uses_buy_fee() -> None:
    n_t = len(config.TICKERS)
    # 3 sessions, holdings increase from 0 → 100 → 100 (one buy, then hold)
    h_rows = [
        {"date": pd.Timestamp("2025-01-01")},
        {"date": pd.Timestamp("2025-01-02")},
        {"date": pd.Timestamp("2025-01-03")},
    ]
    for row, holds in zip(h_rows, [[0] * n_t, [100] * n_t, [100] * n_t], strict=True):
        for i, t in enumerate(config.TICKERS):
            row[f"h_{t}"] = holds[i]
    h_df = pd.DataFrame(h_rows)

    md_dates = pd.DatetimeIndex(
        [pd.Timestamp(date(2025, 1, 1) + timedelta(days=i)) for i in range(3)]
    )
    close = np.full((3, n_t), 50_000.0, dtype=np.float32)
    md = _FakeMD(dates=md_dates, close=close)

    # On day 2, delta = 100 shares × 50_000 VND × 5 tickers × 0.15% = 3,750,000 VND
    expected = 100 * 50_000 * n_t * float(config.BUY_FEE)
    assert M.compute_total_cost(h_df, md) == pytest.approx(expected)


def test_total_cost_sell_only_uses_sell_fee() -> None:
    n_t = len(config.TICKERS)
    h_rows = [
        {"date": pd.Timestamp("2025-01-01")},
        {"date": pd.Timestamp("2025-01-02")},
    ]
    for row, holds in zip(h_rows, [[100] * n_t, [0] * n_t], strict=True):
        for i, t in enumerate(config.TICKERS):
            row[f"h_{t}"] = holds[i]
    h_df = pd.DataFrame(h_rows)

    md_dates = pd.DatetimeIndex(
        [pd.Timestamp(date(2025, 1, 1) + timedelta(days=i)) for i in range(2)]
    )
    close = np.full((2, n_t), 50_000.0, dtype=np.float32)
    md = _FakeMD(dates=md_dates, close=close)

    expected = 100 * 50_000 * n_t * float(config.SELL_FEE)
    assert M.compute_total_cost(h_df, md) == pytest.approx(expected)


def test_total_cost_no_trade_returns_zero() -> None:
    n_t = len(config.TICKERS)
    h_rows = [{"date": pd.Timestamp(f"2025-01-0{i + 1}")} for i in range(3)]
    for row in h_rows:
        for t in config.TICKERS:
            row[f"h_{t}"] = 100
    h_df = pd.DataFrame(h_rows)
    md_dates = pd.DatetimeIndex(
        [pd.Timestamp(date(2025, 1, 1) + timedelta(days=i)) for i in range(3)]
    )
    close = np.full((3, n_t), 50_000.0, dtype=np.float32)
    assert M.compute_total_cost(h_df, _FakeMD(dates=md_dates, close=close)) == 0.0


# ---------- compute_all_financial_metrics integration ------------------------


def test_compute_all_keys_present_and_finite() -> None:
    n_t = len(config.TICKERS)
    n_rows = 10
    pc = pd.DataFrame(
        {
            "date": pd.date_range("2025-01-01", periods=n_rows, freq="D"),
            "agent_name": "x",
            "portfolio_value": np.linspace(1e9, 1.05e9, n_rows),
            "cash": 5e7,
        }
    )
    for t in config.TICKERS:
        pc[f"w_{t}"] = 1.0 / n_t

    h = pd.DataFrame({"date": pc["date"], "agent_name": "x"})
    for t in config.TICKERS:
        h[f"h_{t}"] = 100

    md = _FakeMD(
        dates=pd.DatetimeIndex(pc["date"]),
        close=np.full((n_rows, n_t), 50_000.0, dtype=np.float32),
    )

    out = M.compute_all_financial_metrics(pc, h, md)
    expected_keys = {
        "cumulative_return",
        "sharpe",
        "sortino",
        "max_drawdown",
        "turnover",
        "total_cost",
        "n_steps",
    }
    assert set(out.keys()) == expected_keys
    for k, v in out.items():
        assert math.isfinite(v), f"{k} = {v} not finite"
    assert out["n_steps"] == n_rows - 1
