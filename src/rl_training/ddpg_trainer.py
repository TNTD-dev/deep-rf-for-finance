"""DDPG trainer (PKG-9). Wraps stable_baselines3.DDPG with project config."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import gymnasium as gym
import numpy as np
import yaml
from stable_baselines3 import DDPG
from stable_baselines3.common.noise import NormalActionNoise

from src.rl_training.callbacks import ActionNoiseDecayCallback
from src.rl_training.core import RewardScaleWrapper, train_rl


def load_ddpg_config(cfg_path: Path) -> dict[str, Any]:
    return yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8"))


def train_ddpg(
    *,
    cfg: dict[str, Any],
    train_env: gym.Env,
    val_env: gym.Env,
    save_path: Path,
    log_path: Path,
    seed: int = 42,
) -> dict[str, Any]:
    """Train DDPG with hyperparams from cfg. Returns train_rl summary."""
    reward_scale = float(cfg.get("reward_scale", 1.0))
    if reward_scale != 1.0:
        train_env = RewardScaleWrapper(train_env, scale=reward_scale)

    n_actions = int(np.asarray(train_env.action_space.shape).prod())
    noise_cfg = cfg.get(
        "action_noise", {"sigma_start": 0.1, "sigma_end": 0.02}
    )
    action_noise = NormalActionNoise(
        mean=np.zeros(n_actions),
        sigma=float(noise_cfg["sigma_start"]) * np.ones(n_actions),
    )

    algo_kwargs: dict[str, Any] = dict(
        policy="MlpPolicy",
        learning_rate=float(cfg["learning_rate"]),
        buffer_size=int(cfg["buffer_size"]),
        learning_starts=int(cfg["learning_starts"]),
        batch_size=int(cfg["batch_size"]),
        tau=float(cfg["tau"]),
        gamma=float(cfg["gamma"]),
        train_freq=int(cfg.get("train_freq", 1)),
        gradient_steps=int(cfg.get("gradient_steps", 1)),
        policy_kwargs=cfg.get("policy_kwargs", {}),
        action_noise=action_noise,
        verbose=int(cfg.get("verbose", 0)),
    )

    total_timesteps = int(cfg["total_timesteps"])
    decay_cb = ActionNoiseDecayCallback(
        sigma_start=float(noise_cfg["sigma_start"]),
        sigma_end=float(noise_cfg["sigma_end"]),
        total_timesteps=total_timesteps,
    )

    return train_rl(
        algo_cls=DDPG,
        algo_kwargs=algo_kwargs,
        train_env=train_env,
        val_env=val_env,
        total_timesteps=total_timesteps,
        save_path=save_path,
        log_path=log_path,
        eval_freq=int(cfg.get("eval_freq", 5000)),
        n_eval_episodes=int(cfg.get("n_eval_episodes", 1)),
        extra_callbacks=[decay_cb],
        seed=seed,
    )
