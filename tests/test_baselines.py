"""Baseline agents + Agent Protocol + mini backtest runner invariants.

Uses ``synthetic_market_data`` fixture from conftest.py — no parquet/network
dependency.
"""

from __future__ import annotations

import numpy as np

from src import config
from src.agent_base import Agent
from src.baselines import (
    EQUAL_WEIGHT_TARGET,
    BuyAndHold,
    EqualWeightRebalance,
    RandomAgent,
    run_backtest,
)
from src.trading_env import N_TICKERS, VNTradingEnv


def test_agent_protocol_runtime_check(synthetic_market_data) -> None:
    """All three baselines satisfy the Agent Protocol — keeps the contract
    documented and machine-checkable."""
    env = VNTradingEnv(synthetic_market_data)
    env.reset(seed=0)
    assert isinstance(BuyAndHold(), Agent)
    assert isinstance(EqualWeightRebalance(), Agent)
    assert isinstance(RandomAgent(env), Agent)


def test_buy_and_hold_first_call_emits_equal_weight(synthetic_market_data) -> None:
    """First decide() allocates EQUAL_WEIGHT_TARGET per ticker."""
    env = VNTradingEnv(synthetic_market_data)
    obs, info = env.reset(seed=0)
    agent = BuyAndHold()
    w = agent.decide(obs, info)
    assert w.shape == (N_TICKERS,)
    assert np.allclose(w, EQUAL_WEIGHT_TARGET)


def test_buy_and_hold_holdings_constant_after_first_step(
    synthetic_market_data,
) -> None:
    """True buy-and-hold: shares (not weights) stay constant after day 1.

    If holdings drift, the "hold" semantic is broken — env is silently
    rebalancing because BuyAndHold's cached-weight emission re-quantizes
    via lot-100 each step.
    """
    env = VNTradingEnv(synthetic_market_data)
    obs, info = env.reset(seed=0)
    agent = BuyAndHold()
    # Day 1: initial allocation
    obs, _, _, _, info = env.step(agent.decide(obs, info))
    holdings_after_init = list(info["holdings"])
    # Days 2-5: should hold
    for _ in range(4):
        if env._terminated:
            break
        obs, _, _, _, info = env.step(agent.decide(obs, info))
        assert list(info["holdings"]) == holdings_after_init, (
            "BuyAndHold drifted from initial holdings — true hold semantic broken"
        )


def test_equal_weight_rebalances_on_month_change() -> None:
    """Month-change must trigger rebalance; same-month must hold cached."""
    agent = EqualWeightRebalance()
    obs = np.zeros(56, dtype=np.float32)

    # First call: any month triggers (last_month=None)
    w1 = agent.decide(obs, {"date": "2025-05-05T00:00:00"})
    assert np.allclose(w1, EQUAL_WEIGHT_TARGET)

    # Same month (May) → returns cached, not re-emitted
    w2 = agent.decide(obs, {"date": "2025-05-15T00:00:00"})
    assert np.array_equal(w1, w2)

    # Month change (June): re-rebalance fires
    w3 = agent.decide(obs, {"date": "2025-06-02T00:00:00"})
    assert np.allclose(w3, EQUAL_WEIGHT_TARGET)
    # Internal state advanced
    assert agent._last_month == 6


def test_equal_weight_first_call_initializes_last_month() -> None:
    """`_last_month=None` must NOT match any int month — first call always fires."""
    agent = EqualWeightRebalance()
    assert agent._last_month is None
    agent.decide(np.zeros(56, dtype=np.float32), {"date": "2025-05-05T00:00:00"})
    assert agent._last_month == 5


def test_random_agent_uses_env_rng_reproducible(synthetic_market_data) -> None:
    """Same env seed → identical RandomAgent action sequence. Single-RNG
    invariant from PKG-3; if it breaks, downstream backtest determinism
    breaks too."""

    def trial() -> list[float]:
        env = VNTradingEnv(synthetic_market_data)
        env.reset(seed=2026)
        agent = RandomAgent(env)
        actions = [
            agent.decide(np.zeros(56, dtype=np.float32), {"t": i}).tolist()
            for i in range(5)
        ]
        return actions

    assert trial() == trial()


def test_run_backtest_records_initial_plus_each_step(
    synthetic_market_data,
) -> None:
    """portfolio_curve has n_steps + 1 rows: 1 initial snapshot + 1 per step."""
    env = VNTradingEnv(synthetic_market_data)
    result = run_backtest(env, BuyAndHold(), seed=42)
    assert len(result.portfolio_curve) == result.n_steps + 1
    assert len(result.holdings_curve) == result.n_steps + 1


def test_run_backtest_portfolio_curve_schema(synthetic_market_data) -> None:
    """Schema locked for PKG-10 metrics + PKG-13 frontend consumption."""
    env = VNTradingEnv(synthetic_market_data)
    result = run_backtest(env, BuyAndHold(), seed=42)
    expected_pv = [
        "date",
        "agent_name",
        "portfolio_value",
        "cash",
        *[f"w_{t}" for t in config.TICKERS],
    ]
    expected_h = ["date", "agent_name", *[f"h_{t}" for t in config.TICKERS]]
    assert list(result.portfolio_curve.columns) == expected_pv
    assert list(result.holdings_curve.columns) == expected_h


def test_run_backtest_reproducible_same_seed(synthetic_market_data) -> None:
    """Two runs of the same agent + env + seed → identical final_pv.

    Underpins PKG-3 invariant `test_same_seed_same_trajectory`; if this
    breaks, multi-seed runs in PKG-9 lose determinism for free."""
    md = synthetic_market_data

    def run() -> float:
        env = VNTradingEnv(md)
        return run_backtest(env, BuyAndHold(), seed=42).final_pv

    assert run() == run()


def test_buy_and_hold_full_episode_no_crash(synthetic_market_data) -> None:
    """Smoke: full episode completes; pv positive throughout; holdings
    lot-aligned after every step (PKG-3 invariant preserved)."""
    env = VNTradingEnv(synthetic_market_data)
    result = run_backtest(env, BuyAndHold(), seed=42)
    assert result.final_pv > 0
    assert result.n_steps == len(synthetic_market_data.dates) - 1
    # Holdings rows are int64 multiples of LOT_SIZE
    h_cols = [f"h_{t}" for t in config.TICKERS]
    holdings_matrix = result.holdings_curve[h_cols].to_numpy()
    assert (holdings_matrix % config.LOT_SIZE == 0).all(), (
        "lot-100 invariant broke during backtest"
    )
