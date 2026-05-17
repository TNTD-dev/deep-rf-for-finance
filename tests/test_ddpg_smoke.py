"""DDPG/PPO training smoke — 1000-step runs on synthetic env. ~30-60s total.

These tests verify the trainer wiring (config → algo → callbacks → model.zip)
without depending on full-train convergence. Real-train Sharpe is captured
in PR description, not asserted here.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from src.rl_training.ddpg_trainer import train_ddpg
from src.rl_training.ppo_trainer import train_ppo
from src.trading_env import VNTradingEnv


@pytest.fixture
def _envs(synthetic_market_data):
    """Train + val envs from same synthetic data (fixture is small).

    OK for smoke: we only check non-divergence + save/load, not generalization.
    """
    md = synthetic_market_data
    return VNTradingEnv(md), VNTradingEnv(md)


def test_ddpg_train_1000_steps_completes_without_nan(tmp_path, _envs):
    """End-to-end: train DDPG for 1000 steps on synthetic env; model saved;
    callbacks fire; no NaN in final-step prediction."""
    train_env, val_env = _envs
    cfg = {
        "total_timesteps": 1000,
        "learning_rate": 1e-4,
        "buffer_size": 5000,
        "learning_starts": 100,
        "batch_size": 32,
        "tau": 0.005,
        "gamma": 0.99,
        "train_freq": 1,
        "gradient_steps": 1,
        "verbose": 0,
        "policy_kwargs": {"net_arch": [64, 64]},
        "action_noise": {"sigma_start": 0.1, "sigma_end": 0.02},
        "reward_scale": 100.0,
        "eval_freq": 500,
        "n_eval_episodes": 1,
    }
    save_path = tmp_path / "ddpg.zip"
    log_path = tmp_path / "ddpg.jsonl"

    summary = train_ddpg(
        cfg=cfg, train_env=train_env, val_env=val_env,
        save_path=save_path, log_path=log_path, seed=42,
    )
    assert not summary["aborted"], summary["aborted_reason"]
    assert save_path.exists(), "model.zip not saved"
    assert log_path.exists(), "training log not written"
    # Eval ran at least once
    lines = log_path.read_text().splitlines()
    assert len(lines) >= 1
    row = json.loads(lines[0])
    assert "val_sharpe" in row
    assert "val_cum_return" in row
    # Predict on val env — no NaN
    obs, _ = val_env.reset(seed=42)
    from stable_baselines3 import DDPG
    model = DDPG.load(str(save_path))
    action, _ = model.predict(obs, deterministic=True)
    assert not np.any(np.isnan(action))


def test_ppo_train_1000_steps_completes_without_nan(tmp_path, _envs):
    train_env, val_env = _envs
    cfg = {
        "total_timesteps": 1024,  # multiple of n_steps so PPO updates fire
        "learning_rate": 3e-4,
        "n_steps": 256,
        "batch_size": 32,
        "n_epochs": 4,
        "gamma": 0.99,
        "gae_lambda": 0.95,
        "clip_range": 0.2,
        "ent_coef": 0.0,
        "vf_coef": 0.5,
        "verbose": 0,
        "policy_kwargs": {"net_arch": [64, 64]},
        "reward_scale": 1.0,
        "eval_freq": 512,
        "n_eval_episodes": 1,
    }
    save_path = tmp_path / "ppo.zip"
    log_path = tmp_path / "ppo.jsonl"

    summary = train_ppo(
        cfg=cfg, train_env=train_env, val_env=val_env,
        save_path=save_path, log_path=log_path, seed=42,
    )
    assert not summary["aborted"], summary["aborted_reason"]
    assert save_path.exists()
    assert log_path.exists()
    # Predict — no NaN
    obs, _ = val_env.reset(seed=42)
    from stable_baselines3 import PPO
    model = PPO.load(str(save_path))
    action, _ = model.predict(obs, deterministic=True)
    assert not np.any(np.isnan(action))
