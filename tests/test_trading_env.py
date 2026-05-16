"""VNTradingEnv invariants — Gymnasium API + VN market rules + reproducibility.

Tests use a synthetic MarketData fixture (no parquet, no network) so they run
in CI even before PKG-1 has shipped data. The fixture is small (60 sessions ×
5 tickers) and deliberately includes a price-spike beyond ±7% so the band
clamp invariant can be verified.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src import config
from src.env_data_loader import MarketData
from src.trading_env import (
    CATASTROPHIC_LOSS_REWARD,
    N_TICKERS,
    OBS_DIM,
    VNTradingEnv,
    log_return_reward,
)


def _synthetic_market_data(
    n_sessions: int = 60, spike_idx: int | None = None, spike_factor: float = 1.20
) -> MarketData:
    """Build deterministic MarketData with 5 tickers × ``n_sessions`` days.

    Prices start at [50, 60, 70, 80, 90] and drift up 0.1% per session.
    If ``spike_idx`` is given, close on that session is multiplied by
    ``spike_factor`` for ticker 0 — used to test band clamp.
    """
    rng = np.random.default_rng(seed=0)
    base = np.array([50.0, 60.0, 70.0, 80.0, 90.0], dtype=np.float32)
    close = np.zeros((n_sessions, N_TICKERS), dtype=np.float32)
    close[0] = base
    for t in range(1, n_sessions):
        close[t] = close[t - 1] * (1.0 + 0.001)
    if spike_idx is not None:
        close[spike_idx, 0] = close[spike_idx - 1, 0] * spike_factor

    high = close * 1.01
    low = close * 0.99
    open_ = close * (1.0 + rng.normal(0, 0.001, close.shape).astype(np.float32))

    # Indicators already z-scored: 9 features per ticker. Use small random
    # values so the env sees something other than zeros.
    ind = rng.normal(0, 1, (n_sessions, N_TICKERS, 9)).astype(np.float32)

    dates = pd.date_range("2025-01-02", periods=n_sessions, freq="B")
    return MarketData(
        dates=pd.DatetimeIndex(dates),
        tickers=tuple(config.TICKERS),
        close=close,
        open=open_,
        high=high,
        low=low,
        indicators_norm=ind,
        warmup_offset=0,
    )


# ---- gymnasium API contract ------------------------------------------------


def test_reset_returns_obs_and_info() -> None:
    """Gymnasium 1.x reset → (obs, info). obs shape locked at OBS_DIM=56."""
    env = VNTradingEnv(_synthetic_market_data())
    obs, info = env.reset(seed=42)
    assert obs.shape == (OBS_DIM,)
    assert obs.dtype == np.float32
    assert "date" in info and "portfolio_value" in info
    assert info["portfolio_value"] == pytest.approx(float(config.INITIAL_CAPITAL))


def test_action_space_is_box_minus1_to_1_for_sb3() -> None:
    """sb3 DDPG default policy outputs in [-1, 1]; action_space must match."""
    env = VNTradingEnv(_synthetic_market_data())
    assert env.action_space.shape == (N_TICKERS,)
    assert env.action_space.low.tolist() == [-1.0] * N_TICKERS
    assert env.action_space.high.tolist() == [1.0] * N_TICKERS


def test_step_returns_5_tuple() -> None:
    """Gymnasium 1.x mandate: step → (obs, reward, terminated, truncated, info).
    sb3 + sb3-contrib both require the 5-tuple; gym-style 4-tuple silently
    wraps step return at the vec env layer and reward bookkeeping drifts."""
    env = VNTradingEnv(_synthetic_market_data())
    env.reset(seed=0)
    out = env.step(np.zeros(N_TICKERS, dtype=np.float32))
    assert len(out) == 5
    obs, reward, terminated, truncated, info = out
    assert isinstance(reward, float)
    assert isinstance(terminated, bool)
    assert isinstance(truncated, bool)


# ---- VN market rule invariants ---------------------------------------------


def test_negative_action_treated_as_zero_weight() -> None:
    """Long-only: negative action components must not produce short positions."""
    env = VNTradingEnv(_synthetic_market_data())
    env.reset(seed=0)
    action = np.array([-0.5, -0.3, 0.4, 0.3, 0.0], dtype=np.float32)
    env.step(action)
    holdings = np.asarray(env._holdings)
    assert (holdings >= 0).all()
    assert holdings[0] == 0 and holdings[1] == 0


def test_action_summing_above_1_renormalized() -> None:
    """Sum(weights) > 1 → renormalize. Without it, agent could over-leverage
    and force the buy fallback into a degenerate state."""
    env = VNTradingEnv(_synthetic_market_data())
    env.reset(seed=0)
    # 5 * 0.5 = 2.5 nominal weight → should renormalize to 0.2 each
    env.step(np.array([0.5] * N_TICKERS, dtype=np.float32))
    # Cash should be near zero (~0 after renorm + fees + lot-rounding drag)
    info = env._info()
    pv = info["portfolio_value"]
    invested = pv - info["cash"]
    # Each ticker ≈ 20% allocated; total ≥ 95% invested after fees + rounding
    assert invested / pv > 0.90


def test_lot_100_rounding_floor_invariant() -> None:
    """After any step, every holding must be divisible by LOT_SIZE=100.
    HOSE rule — broker rejects orders not in round lots."""
    env = VNTradingEnv(_synthetic_market_data())
    env.reset(seed=42)
    for _ in range(10):
        a = env.action_space.sample()
        env.step(a)
        for h in env._holdings:
            assert int(h) % config.LOT_SIZE == 0, f"holding {h} not divisible by {config.LOT_SIZE}"


def test_fee_asymmetry_buy_then_sell_loses_money() -> None:
    """Full buy followed by full sell at the same price loses ~0.4% to fees
    (0.15 buy + 0.25 sell). PRD §15 asymmetry — if buy_fee >= sell_fee, env
    would silently make sells too cheap and bias DDPG toward churn."""
    md = _synthetic_market_data(n_sessions=10)
    # Flatten price trajectory so buy and sell happen at same price
    md.close[:] = 50.0
    md.high[:] = 50.0
    md.low[:] = 50.0
    md.open[:] = 50.0
    env = VNTradingEnv(md)
    env.reset(seed=0)
    pv0 = env._portfolio_value(env._t)
    # Step 1: buy 90% (10% headroom for fees)
    env.step(np.array([0.18] * N_TICKERS, dtype=np.float32))
    # Step 2: sell all
    env.step(np.zeros(N_TICKERS, dtype=np.float32))
    pv2 = env._portfolio_value(env._t)
    loss_pct = (pv0 - pv2) / pv0
    # Round-trip cost ≈ 0.9 × (0.0015 + 0.0025) = 0.36% on the invested 90%
    assert 0.001 < loss_pct < 0.01, f"unexpected round-trip loss {loss_pct:.4%}"


def test_band_clamp_caps_fill_price_at_plus_7_percent() -> None:
    """If today's close exceeds prev_close × 1.07, the env must fill at the
    band ceiling, not the actual close. Defensive against future data sources
    that don't pre-clip to the HOSE band."""
    md = _synthetic_market_data(n_sessions=10, spike_idx=5, spike_factor=1.20)
    env = VNTradingEnv(md)
    fill = env._fill_price(5)
    prev = md.close[4]
    band_high = prev * (1 + config.PRICE_BAND)
    # Ticker 0 had the +20% spike; must clamp to +7%
    assert fill[0] == pytest.approx(band_high[0], rel=1e-5)
    # Other tickers untouched
    assert fill[1] == pytest.approx(md.close[5, 1], rel=1e-5)


# ---- reproducibility -------------------------------------------------------


def test_same_seed_same_trajectory() -> None:
    """Reseeding to the same value must produce identical step-by-step
    trajectory. If this breaks, multi-seed reproducibility (PRD §15 §5)
    fails downstream and Person 2 can't verify backtests."""
    md = _synthetic_market_data()

    def run() -> float:
        env = VNTradingEnv(md)
        env.reset(seed=2026)
        for _ in range(20):
            a = env.np_random.uniform(-1, 1, N_TICKERS).astype(np.float32)
            env.step(a)
        return env._portfolio_value(env._t)

    assert run() == run()


# ---- termination + edge cases ----------------------------------------------


def test_episode_terminates_at_end_of_data() -> None:
    """Episode terminates exactly at len(dates) - 1, not at len(dates)."""
    md = _synthetic_market_data(n_sessions=20)
    env = VNTradingEnv(md)
    env.reset(seed=0)
    steps = 0
    while not env._terminated and steps < 100:
        env.step(np.zeros(N_TICKERS, dtype=np.float32))
        steps += 1
    assert env._terminated
    assert env._t == len(md.dates) - 1


def test_step_after_terminated_raises() -> None:
    """Calling step after terminated must fail loud (sb3 catches this and
    auto-resets, but tests must verify the contract)."""
    md = _synthetic_market_data(n_sessions=5)
    env = VNTradingEnv(md)
    env.reset(seed=0)
    while not env._terminated:
        env.step(np.zeros(N_TICKERS, dtype=np.float32))
    with pytest.raises(RuntimeError, match="terminated"):
        env.step(np.zeros(N_TICKERS, dtype=np.float32))


def test_catastrophic_loss_yields_sentinel_reward() -> None:
    """log_return_reward returns CATASTROPHIC_LOSS_REWARD when pv goes
    non-positive. Sentinel value is intentional — DDPG sees a huge negative
    signal and learns to avoid blow-ups."""
    assert log_return_reward(1.0, 0.0) == CATASTROPHIC_LOSS_REWARD
    assert log_return_reward(1.0, -5.0) == CATASTROPHIC_LOSS_REWARD
    assert log_return_reward(0.0, 1.0) == CATASTROPHIC_LOSS_REWARD


def test_t_plus_2_settlement_defers_sell_proceeds() -> None:
    """With t_plus_2=True, cash from a sell must NOT appear in cash balance
    until 2 sessions later. PRD §15 calls this a nice-to-have; behavior must
    still be correct when opted in."""
    md = _synthetic_market_data(n_sessions=10)
    md.close[:] = 50.0  # flat market
    md.open[:] = 50.0
    md.high[:] = 50.0
    md.low[:] = 50.0
    env = VNTradingEnv(md, t_plus_2=True)
    env.reset(seed=0)
    env.step(np.array([0.18] * N_TICKERS, dtype=np.float32))  # buy
    cash_after_buy = env._cash
    env.step(np.zeros(N_TICKERS, dtype=np.float32))  # sell-all → queued
    assert env._cash == pytest.approx(cash_after_buy, rel=1e-9), (
        "t_plus_2: cash from sell appeared immediately — settlement queue broken"
    )
    # 2 sessions later, queue drains
    env.step(np.zeros(N_TICKERS, dtype=np.float32))
    env.step(np.zeros(N_TICKERS, dtype=np.float32))
    assert env._cash > cash_after_buy, "t_plus_2: queue did not drain after 2 sessions"


def test_random_agent_full_episode_no_crash() -> None:
    """Smoke test: random actions for full synthetic episode → no exception,
    pv stays positive, terminal info dict is well-formed."""
    md = _synthetic_market_data(n_sessions=60)
    env = VNTradingEnv(md)
    obs, info = env.reset(seed=42)
    assert info["portfolio_value"] > 0
    while not env._terminated:
        a = env.action_space.sample()
        obs, r, term, trunc, info = env.step(a)
        assert obs.shape == (OBS_DIM,)
        assert info["portfolio_value"] > 0
        assert not np.isnan(obs).any()


def test_obs_dim_locked_at_56() -> None:
    """OBS_DIM is a contract — DDPG models trained against 56-dim observation
    will fail to load if this changes. Document constant and pin via test."""
    assert OBS_DIM == 56
    md = _synthetic_market_data()
    env = VNTradingEnv(md)
    obs, _ = env.reset(seed=0)
    assert obs.shape == (56,)
