"""Buy-and-hold + equal-weight monthly rebalance + random + mini backtest runner.

Equal-weight target is 0.19 per ticker (5 × 0.19 = 0.95), leaving a 5% cash
buffer to absorb buy fee (≤ 0.14% NAV) + lot-100 rounding drift (≤ 0.1% NAV).
Without the buffer, env's "can't afford" fallback would trigger and silently
under-allocate.

Monthly rebalance triggers on the first trading day of each calendar month,
detected by month-changed-since-last-rebalance. The env only steps on trading
days, so a month boundary that falls on a weekend/holiday correctly resolves
to the next trading day.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src import config
from src.agent_base import Agent, BacktestResult
from src.trading_env import N_TICKERS, VNTradingEnv

EQUAL_WEIGHT_TARGET: float = 0.19


class BuyAndHold:
    """First decide() allocates equal-weight; subsequent calls emit weights
    that map back to the CURRENT holdings so env sees ``delta_shares = 0``
    and no trade fires.

    True buy-and-hold holds SHARES constant, not WEIGHTS. As market drifts
    differentially per ticker, weights naturally diverge from 0.19 — that's
    correct behavior. Without this, env would re-rebalance every day toward
    equal weight (which is what EqualWeightRebalance does daily, defeating
    the purpose of having two distinct baselines).
    """

    name: str = "buy_and_hold"

    def __init__(self) -> None:
        self._initialized: bool = False

    def decide(self, obs: np.ndarray, info: dict) -> np.ndarray:
        if not self._initialized:
            self._initialized = True
            return np.full(N_TICKERS, EQUAL_WEIGHT_TARGET, dtype=np.float32)
        # Map current holdings → weights so env reproduces them on this step.
        # target_shares = floor(weight * pv / close[t] / LOT) * LOT
        # Naive `weight = holdings * close / pv` loses ~15 VND per ticker after
        # float32 cast at action boundary — enough that floor occasionally
        # drops one lot. Add a half-lot share-equivalent buffer so the floor
        # always lands on the current holdings exactly.
        holdings = np.asarray(info["holdings"], dtype=np.float64)
        close_t = np.asarray(info["close_t"], dtype=np.float64)
        pv = max(float(info["portfolio_value"]), 1e-8)
        buffer_shares = config.LOT_SIZE / 2.0
        weights = ((holdings + buffer_shares) * close_t) / pv
        return weights.astype(np.float32)


class EqualWeightRebalance:
    """Rebalance to equal-weight on first trading day of each calendar month."""

    name: str = "equal_weight"

    def __init__(self) -> None:
        self._last_month: int | None = None
        self._weights: np.ndarray = np.zeros(N_TICKERS, dtype=np.float32)

    def decide(self, obs: np.ndarray, info: dict) -> np.ndarray:
        month = pd.Timestamp(info["date"]).month
        if month != self._last_month:
            self._weights = np.full(
                N_TICKERS, EQUAL_WEIGHT_TARGET, dtype=np.float32
            )
            self._last_month = month
        return self._weights.copy()


class RandomAgent:
    """Uniform sample from action_space using env's seeded RNG (reproducible).

    Borrows ``env.np_random`` rather than creating its own — matches the
    PKG-3 reproducibility invariant where ``env.reset(seed=N)`` seeds the
    single RNG that all stochastic components consume.
    """

    name: str = "random"

    def __init__(self, env: VNTradingEnv) -> None:
        self._rng = env.np_random

    def decide(self, obs: np.ndarray, info: dict) -> np.ndarray:
        return self._rng.uniform(-1, 1, N_TICKERS).astype(np.float32)


def run_backtest(
    env: VNTradingEnv, agent: Agent, seed: int = 42
) -> BacktestResult:
    """Step-until-terminate loop. Records (date, pv, cash, weights, holdings).

    Pure function — same env + agent + seed → identical BacktestResult.
    PKG-10 will ship a fuller version with metrics; this is the minimal core.
    """
    obs, info = env.reset(seed=seed)
    records: list[dict] = [_snapshot(env, info)]
    total_log_r = 0.0
    n_steps = 0
    while not env._terminated:
        action = agent.decide(obs, info)
        obs, r, term, trunc, info = env.step(action)
        total_log_r += r
        n_steps += 1
        records.append(_snapshot(env, info))
    pv_df, h_df = _records_to_frames(records, agent.name)
    return BacktestResult(
        agent_name=agent.name,
        portfolio_curve=pv_df,
        holdings_curve=h_df,
        total_log_return=total_log_r,
        final_pv=float(info["portfolio_value"]),
        n_steps=n_steps,
        seed=seed,
    )


def _snapshot(env: VNTradingEnv, info: dict) -> dict:
    """Capture one row of (date, pv, cash, w_*, h_*) state at env._t."""
    pv = float(info["portfolio_value"])
    holdings = np.asarray(info["holdings"], dtype=np.int64)
    t = min(env._t, len(env.md.dates) - 1)
    prices = env.md.close[t]
    weights = (holdings * prices) / max(pv, 1e-8)
    row = {
        "date": info["date"],
        "portfolio_value": pv,
        "cash": float(info["cash"]),
    }
    for i, tkr in enumerate(config.TICKERS):
        row[f"w_{tkr}"] = float(weights[i])
    for i, tkr in enumerate(config.TICKERS):
        row[f"h_{tkr}"] = int(holdings[i])
    return row


def _records_to_frames(
    records: list[dict], agent_name: str
) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["date"])
    df["agent_name"] = agent_name
    w_cols = [f"w_{t}" for t in config.TICKERS]
    h_cols = [f"h_{t}" for t in config.TICKERS]
    pv_df = df[["date", "agent_name", "portfolio_value", "cash", *w_cols]].copy()
    h_df = df[["date", "agent_name", *h_cols]].copy()
    return pv_df, h_df
