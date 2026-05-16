"""VN trading environment (Gymnasium). Contract for every agent in this project.

Action space:    ``Box(-1, 1, (n_tickers,), float32)`` — target weights.
                 Negative components clamp to 0 (long-only); if sum > 1,
                 weights are renormalized so total weight ≤ 1 (rest = cash).
Observation:     Flat 56-dim float32 vector =
                 [45 z-scored indicators] + [5 weights] + [5 prev-returns] + [1 cash_ratio]
Reward:          ``log(pv_t / pv_{t-1})``. Override with ``reward_fn=`` kwarg.
Decision policy: agent emits weights each step; env executes at session close.
                 Weekly-rebalance agents must cache externally — env doesn't
                 understand schedules.

Invariants (CLAUDE.md §"Domain-Specific Rules"):
  1. state at session T sees only data with date < T (lookahead-safe)
  2. fill price clamped to [prev_close × 0.93, prev_close × 1.07]
  3. shares rounded DOWN to nearest LOT_SIZE (100)
  4. fees: buy 0.15%, sell 0.25% (asymmetric, sell includes 0.1% transfer tax)
  5. long-only: negative action components → 0
  6. T+2 settlement: optional, default off

OBS_DIM is LOCKED at 56. Changing it requires retraining every DDPG/PPO model
and updating PKG-5 LLM serialization. Coordinate via PR, never silently.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import gymnasium as gym
import numpy as np
from gymnasium import spaces
from gymnasium.utils import seeding

from src import config
from src.env_data_loader import MarketData

N_TICKERS: int = 5
N_INDICATORS: int = 9  # must match len(INDICATOR_COLS) from indicators.py
OBS_DIM: int = N_TICKERS * N_INDICATORS + 2 * N_TICKERS + 1  # 45 + 10 + 1 = 56
CATASTROPHIC_LOSS_REWARD: float = -100.0


def log_return_reward(pv_prev: float, pv_cur: float) -> float:
    """Default reward: log portfolio-value ratio.

    Returns CATASTROPHIC_LOSS_REWARD if either pv is non-positive, which
    triggers terminal state in ``step``.
    """
    if pv_cur <= 0 or pv_prev <= 0:
        return CATASTROPHIC_LOSS_REWARD
    return float(np.log(pv_cur / pv_prev))


class VNTradingEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(
        self,
        market_data: MarketData,
        initial_capital: float = float(config.INITIAL_CAPITAL),
        t_plus_2: bool = False,
        reward_fn: Callable[[float, float], float] | None = None,
    ) -> None:
        super().__init__()
        if market_data.close.shape[1] != N_TICKERS:
            raise ValueError(
                f"market_data has {market_data.close.shape[1]} tickers, "
                f"expected {N_TICKERS}"
            )
        self.md = market_data
        self.initial_capital = float(initial_capital)
        self.t_plus_2 = t_plus_2
        self._reward_fn = reward_fn or log_return_reward

        self.action_space = spaces.Box(
            low=-1.0, high=1.0, shape=(N_TICKERS,), dtype=np.float32
        )
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(OBS_DIM,), dtype=np.float32
        )
        self._reset_state()

    # ---- gymnasium API -----------------------------------------------------

    def reset(
        self,
        seed: int | None = None,
        options: dict | None = None,
    ) -> tuple[np.ndarray, dict]:
        super().reset(seed=seed)
        self.np_random, _ = seeding.np_random(seed)
        self._reset_state()
        return self._compute_obs(), self._info()

    def step(
        self, action: np.ndarray
    ) -> tuple[np.ndarray, float, bool, bool, dict]:
        if self._terminated:
            raise RuntimeError(
                "step() called after episode terminated — call reset()"
            )

        t = self._t
        pv_before = self._portfolio_value(t)
        weights = self._clean_action(action)
        self._execute_with_vn_rules(t, weights)
        pv_after = self._portfolio_value(t)
        reward = self._reward_fn(pv_before, pv_after)

        # Advance time. Terminate on end-of-data or catastrophic loss.
        self._t += 1
        self._terminated = (
            self._t >= len(self.md.dates) - 1 or pv_after <= 0
        )
        obs = self._compute_obs()
        info = self._info()
        info.update({"pv_before": pv_before, "pv_after": pv_after, "fill_t": t})
        return obs, float(reward), self._terminated, False, info

    # ---- internal ----------------------------------------------------------

    def _reset_state(self) -> None:
        self._t: int = self.md.warmup_offset
        self._holdings: np.ndarray = np.zeros(N_TICKERS, dtype=np.int64)
        self._cash: float = self.initial_capital
        self._settlement_q: list[tuple[int, float]] = []
        self._terminated: bool = False

    def _clean_action(self, action: np.ndarray) -> np.ndarray:
        a = np.clip(np.asarray(action, dtype=np.float32), 0.0, 1.0)
        total = float(a.sum())
        if total > 1.0:
            a = a / total
        return a

    def _portfolio_value(self, t: int) -> float:
        t_safe = min(t, len(self.md.dates) - 1)
        price_t = self.md.close[t_safe]
        return float(self._cash + (self._holdings * price_t).sum())

    def _fill_price(self, t: int) -> np.ndarray:
        """±7% band clamp against previous-session close (CLAUDE.md §3)."""
        if t == 0:
            return self.md.close[t]
        prev = self.md.close[t - 1]
        band_low = prev * (1 - config.PRICE_BAND)
        band_high = prev * (1 + config.PRICE_BAND)
        return np.clip(self.md.close[t], band_low, band_high)

    def _execute_with_vn_rules(self, t: int, target_weights: np.ndarray) -> None:
        """Compute delta_shares, execute sells first then buys, apply fees.

        Lot-100 floor rounding; fee asymmetry buy/sell; optional T+2 settlement.
        """
        if self.t_plus_2:
            released = sum(amt for rt, amt in self._settlement_q if rt <= t)
            self._settlement_q = [
                (rt, amt) for rt, amt in self._settlement_q if rt > t
            ]
            self._cash += released

        fill_price = self._fill_price(t)
        pv = self._portfolio_value(t)
        target_values = target_weights * pv
        denom = np.maximum(fill_price, 1e-8)
        target_shares = (
            np.floor(target_values / denom / config.LOT_SIZE).astype(np.int64)
            * config.LOT_SIZE
        )
        delta = target_shares - self._holdings

        # Sells first to free cash
        for i in range(N_TICKERS):
            if delta[i] < 0:
                shares = int(-delta[i])
                proceeds = shares * float(fill_price[i]) * (1 - config.SELL_FEE)
                if self.t_plus_2:
                    self._settlement_q.append((t + 2, proceeds))
                else:
                    self._cash += proceeds
                self._holdings[i] -= shares

        # Buys with affordability fallback
        for i in range(N_TICKERS):
            if delta[i] > 0:
                shares = int(delta[i])
                cost = shares * float(fill_price[i]) * (1 + config.BUY_FEE)
                if cost > self._cash + 1e-6:
                    per_lot_cost = (
                        float(fill_price[i]) * config.LOT_SIZE * (1 + config.BUY_FEE)
                    )
                    affordable_lots = (
                        int(self._cash // per_lot_cost) if per_lot_cost > 0 else 0
                    )
                    shares = max(0, affordable_lots * config.LOT_SIZE)
                    cost = shares * float(fill_price[i]) * (1 + config.BUY_FEE)
                self._cash -= cost
                self._holdings[i] += shares

    def _compute_obs(self) -> np.ndarray:
        t = min(self._t, len(self.md.dates) - 1)
        pv = max(self._portfolio_value(t), 1e-8)
        weights = (self._holdings * self.md.close[t]) / pv  # (n_tickers,)
        if t >= 1:
            prev_ret = (self.md.close[t] - self.md.close[t - 1]) / np.maximum(
                self.md.close[t - 1], 1e-8
            )
        else:
            prev_ret = np.zeros(N_TICKERS, dtype=np.float32)
        cash_ratio = float(self._cash / pv)

        ind = self.md.indicators_norm[t].astype(np.float32).reshape(-1)  # 45
        obs = np.concatenate(
            [
                ind,
                weights.astype(np.float32),
                prev_ret.astype(np.float32),
                np.array([cash_ratio], dtype=np.float32),
            ]
        )
        # Defensive: clear residual NaN/inf so sb3 doesn't crash mid-train
        return np.nan_to_num(obs, nan=0.0, posinf=0.0, neginf=0.0)

    def _info(self) -> dict[str, Any]:
        t = min(self._t, len(self.md.dates) - 1)
        return {
            "date": self.md.dates[t].isoformat(),
            "t": int(self._t),
            "cash": float(self._cash),
            "holdings": self._holdings.tolist(),
            "portfolio_value": self._portfolio_value(t),
        }
