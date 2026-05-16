"""PPO trainer (PKG-9). The DDPG backup — on-policy, far more stable.

No action noise (PPO uses stochastic policy directly); no decay callback.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import gymnasium as gym
import yaml
from stable_baselines3 import PPO

from src.rl_training.core import RewardScaleWrapper, train_rl


def load_ppo_config(cfg_path: Path) -> dict[str, Any]:
    return yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8"))


def train_ppo(
    *,
    cfg: dict[str, Any],
    train_env: gym.Env,
    val_env: gym.Env,
    save_path: Path,
    log_path: Path,
    seed: int = 42,
) -> dict[str, Any]:
    """Train PPO with hyperparams from cfg. Returns train_rl summary."""
    reward_scale = float(cfg.get("reward_scale", 1.0))
    if reward_scale != 1.0:
        train_env = RewardScaleWrapper(train_env, scale=reward_scale)

    algo_kwargs: dict[str, Any] = dict(
        policy="MlpPolicy",
        learning_rate=float(cfg["learning_rate"]),
        n_steps=int(cfg["n_steps"]),
        batch_size=int(cfg["batch_size"]),
        n_epochs=int(cfg["n_epochs"]),
        gamma=float(cfg["gamma"]),
        gae_lambda=float(cfg["gae_lambda"]),
        clip_range=float(cfg["clip_range"]),
        ent_coef=float(cfg.get("ent_coef", 0.0)),
        vf_coef=float(cfg.get("vf_coef", 0.5)),
        policy_kwargs=cfg.get("policy_kwargs", {}),
        verbose=int(cfg.get("verbose", 0)),
    )

    return train_rl(
        algo_cls=PPO,
        algo_kwargs=algo_kwargs,
        train_env=train_env,
        val_env=val_env,
        total_timesteps=int(cfg["total_timesteps"]),
        save_path=save_path,
        log_path=log_path,
        eval_freq=int(cfg.get("eval_freq", 10000)),
        n_eval_episodes=int(cfg.get("n_eval_episodes", 1)),
        seed=seed,
    )
