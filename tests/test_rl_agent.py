"""RLAgent invariants — Protocol, action shape, save/load round-trip, algo detect."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from stable_baselines3 import DDPG, PPO
from stable_baselines3.common.noise import NormalActionNoise

from src.agent_base import Agent
from src.agents.rl_agent import RLAgent
from src.trading_env import VNTradingEnv


@pytest.fixture
def ddpg_model_path(tmp_path, synthetic_market_data):
    """Tiny DDPG trained for 200 steps + saved. Module-scoped to share."""
    md = synthetic_market_data
    env = VNTradingEnv(md)
    n = env.action_space.shape[-1]
    noise = NormalActionNoise(mean=np.zeros(n), sigma=0.1 * np.ones(n))
    model = DDPG(
        "MlpPolicy", env,
        action_noise=noise,
        learning_starts=50,
        batch_size=32,
        learning_rate=1e-4,
        verbose=0,
        seed=42,
    )
    model.learn(total_timesteps=200, log_interval=10)
    path = tmp_path / "ddpg_smoke.zip"
    model.save(str(path))
    return path


@pytest.fixture
def ppo_model_path(tmp_path, synthetic_market_data):
    """Tiny PPO trained for 256 steps + saved."""
    md = synthetic_market_data
    env = VNTradingEnv(md)
    model = PPO(
        "MlpPolicy", env,
        n_steps=128,
        batch_size=32,
        learning_rate=3e-4,
        verbose=0,
        seed=42,
    )
    model.learn(total_timesteps=256)
    path = tmp_path / "ppo_smoke.zip"
    model.save(str(path))
    return path


def test_rl_agent_implements_protocol(ddpg_model_path):
    agent = RLAgent(ddpg_model_path)
    assert isinstance(agent, Agent)
    assert agent.name == "ddpg"


def test_decide_returns_valid_action(ddpg_model_path, synthetic_market_data):
    agent = RLAgent(ddpg_model_path)
    env = VNTradingEnv(synthetic_market_data)
    obs, info = env.reset(seed=42)
    action = agent.decide(obs, info)
    assert isinstance(action, np.ndarray)
    assert action.shape == (5,)
    assert action.dtype == np.float32
    assert not np.any(np.isnan(action))


def test_save_load_round_trip_preserves_predictions(
    ddpg_model_path, synthetic_market_data
):
    """RLAgent.decide() must produce the same action as the original model."""
    original = DDPG.load(str(ddpg_model_path))
    agent = RLAgent(ddpg_model_path)
    env = VNTradingEnv(synthetic_market_data)
    obs, info = env.reset(seed=42)
    original_action, _ = original.predict(obs, deterministic=True)
    agent_action = agent.decide(obs, info)
    np.testing.assert_allclose(original_action, agent_action, atol=1e-6)


def test_algo_auto_detect_ddpg(ddpg_model_path):
    agent = RLAgent(ddpg_model_path)
    assert agent._algo is DDPG


def test_algo_auto_detect_ppo(ppo_model_path):
    agent = RLAgent(ppo_model_path)
    assert agent._algo is PPO
    assert agent.name == "ppo"


def test_missing_model_raises_loud(tmp_path):
    with pytest.raises(FileNotFoundError):
        RLAgent(tmp_path / "does_not_exist.zip")


def test_rl_agent_works_in_run_backtest(ddpg_model_path, synthetic_market_data):
    """End-to-end: env + RLAgent + run_backtest must not crash."""
    from src.baselines import run_backtest
    env = VNTradingEnv(synthetic_market_data)
    agent = RLAgent(ddpg_model_path)
    result = run_backtest(env, agent, seed=42)
    assert result.agent_name == "ddpg"
    assert result.n_steps > 0
    assert not pd.isna(result.final_pv)
