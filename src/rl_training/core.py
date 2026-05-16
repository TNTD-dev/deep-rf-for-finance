"""Shared RL training core. DDPG/PPO trainers call train_rl() with their
algo class + parsed config + envs.

train_rl wires the standard callbacks (ValMetricsCallback, DivergenceCallback)
and returns a summary dict with abort status + best val Sharpe — never
raises, so CLIs map abort → exit code 2 + warning, not stacktrace.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import gymnasium as gym
from stable_baselines3.common.callbacks import BaseCallback, CallbackList

from src.rl_training.callbacks import DivergenceCallback, ValMetricsCallback

log = logging.getLogger(__name__)


class RewardScaleWrapper(gym.RewardWrapper):
    """Multiply env reward by a constant scale. Used for DDPG to bring
    log-return rewards into a Q-network-friendly magnitude."""

    def __init__(self, env: gym.Env, scale: float = 1.0) -> None:
        super().__init__(env)
        self.scale = float(scale)

    def reward(self, reward: float) -> float:
        return float(reward) * self.scale


def train_rl(
    *,
    algo_cls: type,
    algo_kwargs: dict[str, Any],
    train_env: gym.Env,
    val_env: gym.Env,
    total_timesteps: int,
    save_path: Path,
    log_path: Path,
    eval_freq: int = 5000,
    n_eval_episodes: int = 1,
    extra_callbacks: list[BaseCallback] | None = None,
    seed: int = 42,
) -> dict[str, Any]:
    """Shared training entry. Returns a summary dict; never raises.

    Summary keys:
    - aborted: bool
    - aborted_reason: str | None
    - best_sharpe: float (val Sharpe of best checkpoint, -inf if no eval ran)
    - final_step: int
    - eval_count: int
    """
    save_path = Path(save_path)
    log_path = Path(log_path)
    save_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    # Fresh log per run
    if log_path.exists():
        log_path.unlink()

    val_cb = ValMetricsCallback(
        val_env=val_env,
        log_path=log_path,
        best_save_path=save_path,
        eval_freq=eval_freq,
        n_eval_episodes=n_eval_episodes,
        eval_seed=seed,
    )
    div_cb = DivergenceCallback()
    callbacks: list[BaseCallback] = [val_cb, div_cb]
    if extra_callbacks:
        callbacks.extend(extra_callbacks)

    model = algo_cls(env=train_env, seed=seed, **algo_kwargs)
    summary: dict[str, Any] = {
        "aborted": False,
        "aborted_reason": None,
        "best_sharpe": val_cb.best_sharpe,
        "final_step": 0,
        "eval_count": 0,
    }
    try:
        model.learn(
            total_timesteps=total_timesteps,
            callback=CallbackList(callbacks),
        )
    except Exception as e:  # noqa: BLE001 — training failures must surface as summary
        log.warning("training raised %s: %s", type(e).__name__, e)
        summary["aborted"] = True
        summary["aborted_reason"] = f"{type(e).__name__}: {e}"

    summary["final_step"] = int(getattr(model, "num_timesteps", 0))
    summary["eval_count"] = int(val_cb.eval_count)
    summary["best_sharpe"] = float(val_cb.best_sharpe)
    if div_cb.aborted_reason is not None:
        summary["aborted"] = True
        summary["aborted_reason"] = div_cb.aborted_reason

    # If no eval ever ran (e.g. training aborted early) AND no best model
    # saved, still save the final model so PKG-10 has SOMETHING to load.
    if not save_path.exists():
        try:
            model.save(str(save_path))
            log.info("no eval-best saved; wrote final model to %s", save_path)
        except Exception as e:  # noqa: BLE001
            log.warning("final model save failed: %s", e)

    return summary
