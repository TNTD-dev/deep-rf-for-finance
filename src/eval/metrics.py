"""Financial metrics — pure functions on portfolio_value / weights / holdings.

Reproducible (no clock, no random). Golden-value tested.

Annualization = 252 (cross-market equity convention). VN actually trades ~248
sessions/year but 252 is the standard for cross-comparison.

All functions are tolerant of degenerate inputs:
- empty / single-point series → 0.0 (not NaN)
- flat series → 0.0 Sharpe (std=0 short-circuit)
- missing weight columns → 0.0 turnover
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from src import config

ANNUALIZATION_DAYS: int = 252


def log_returns(portfolio_value: np.ndarray) -> np.ndarray:
    """log(pv_t / pv_{t-1}). Matches env reward exactly."""
    pv = np.asarray(portfolio_value, dtype=np.float64)
    if len(pv) < 2:
        return np.array([], dtype=np.float64)
    pv = np.maximum(pv, 1e-12)
    return np.log(pv[1:] / pv[:-1])


def compute_cumulative_return(portfolio_value: np.ndarray) -> float:
    pv = np.asarray(portfolio_value, dtype=np.float64)
    if len(pv) < 2 or pv[0] <= 0:
        return 0.0
    return float(pv[-1] / pv[0] - 1.0)


def compute_sharpe(portfolio_value: np.ndarray, annualization: int = ANNUALIZATION_DAYS) -> float:
    r = log_returns(portfolio_value)
    if r.size == 0:
        return 0.0
    s = float(r.std())
    if s < 1e-12:
        return 0.0
    return float(r.mean() / s * math.sqrt(annualization))


def compute_sortino(portfolio_value: np.ndarray, annualization: int = ANNUALIZATION_DAYS) -> float:
    r = log_returns(portfolio_value)
    if r.size == 0:
        return 0.0
    neg = r[r < 0]
    if neg.size == 0:
        return 0.0
    s = float(neg.std())
    if s < 1e-12:
        return 0.0
    return float(r.mean() / s * math.sqrt(annualization))


def compute_max_drawdown(portfolio_value: np.ndarray) -> float:
    """Max peak-to-trough drawdown as a positive fraction (0.20 = 20% loss)."""
    pv = np.asarray(portfolio_value, dtype=np.float64)
    if pv.size == 0:
        return 0.0
    running_max = np.maximum.accumulate(pv)
    dd = (running_max - pv) / np.maximum(running_max, 1e-12)
    return float(dd.max())


def compute_turnover(portfolio_curve: pd.DataFrame) -> float:
    """Frazzini-Pedersen turnover: mean(sum |Δw_i|) per step."""
    w_cols = [f"w_{t}" for t in config.TICKERS]
    if not all(c in portfolio_curve.columns for c in w_cols):
        return 0.0
    w = portfolio_curve[w_cols].to_numpy(dtype=np.float64)
    if w.shape[0] < 2:
        return 0.0
    delta = np.abs(np.diff(w, axis=0)).sum(axis=1)
    return float(delta.mean())


def compute_total_cost(holdings_df: pd.DataFrame, market_data) -> float:
    """Sum of (buy_fee × buy_VND + sell_fee × sell_VND) reconstructed from
    holdings diff × execution-day close × fee rate.

    Approximation: doesn't account for env's ±7% band clamp on fill price,
    but trade SIZE (shares) is what holdings_df captures and what dominates
    fee. Validated by Spike B: buy_and_hold yields ~0.143% of capital,
    matching the 0.15% buy fee minus tiny rounding losses.
    """
    h_cols = [f"h_{t}" for t in config.TICKERS]
    if not all(c in holdings_df.columns for c in h_cols):
        return 0.0
    h = holdings_df[h_cols].to_numpy(dtype=np.float64)
    if h.shape[0] < 2:
        return 0.0
    delta = np.diff(h, axis=0)
    md_dates = [d.date() for d in market_data.dates]
    h_dates = pd.to_datetime(holdings_df["date"]).dt.date.tolist()
    n_tickers = len(config.TICKERS)
    fills_list = []
    for d in h_dates[1:]:
        if d in md_dates:
            fills_list.append(market_data.close[md_dates.index(d)])
        else:
            fills_list.append(np.zeros(n_tickers, dtype=np.float32))
    fills = np.asarray(fills_list, dtype=np.float64)
    buy = np.where(delta > 0, delta, 0) * fills * float(config.BUY_FEE)
    sell = np.where(delta < 0, -delta, 0) * fills * float(config.SELL_FEE)
    return float(buy.sum() + sell.sum())


def compute_all_financial_metrics(
    portfolio_curve: pd.DataFrame,
    holdings_df: pd.DataFrame,
    market_data,
) -> dict[str, float]:
    """One-shot compute of all financial metrics. PKG-11 reads this dict."""
    pv = portfolio_curve["portfolio_value"].to_numpy()
    return {
        "cumulative_return": compute_cumulative_return(pv),
        "sharpe": compute_sharpe(pv),
        "sortino": compute_sortino(pv),
        "max_drawdown": compute_max_drawdown(pv),
        "turnover": compute_turnover(portfolio_curve),
        "total_cost": compute_total_cost(holdings_df, market_data),
        "n_steps": int(len(portfolio_curve) - 1),
    }
