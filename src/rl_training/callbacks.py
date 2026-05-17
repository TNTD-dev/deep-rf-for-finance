"""sb3 callbacks for RL training (PKG-9).

Three callbacks:
- ``DivergenceCallback`` — abort training on NaN/Inf in any logged train/*_loss
  key. Algo-agnostic (advisor: DDPG logs critic_loss/actor_loss; PPO logs
  value_loss/policy_gradient_loss/entropy_loss/loss — same regex match).
  Note: ``train/q_value`` is NOT logged by sb3 2.8.0 DDPG, so the original
  Q-threshold check from the plan was dropped. NaN-in-loss is the actual
  observable divergence signal.
- ``ValMetricsCallback`` — periodic rollout on val env, write JSONL row,
  save best-on-Sharpe model.
- ``ActionNoiseDecayCallback`` — linearly decay NormalActionNoise.sigma
  over training (sb3 doesn't auto-decay).
"""

from __future__ import annotations

import contextlib
import json
import logging
import math
from pathlib import Path

import numpy as np
from stable_baselines3.common.callbacks import BaseCallback

log = logging.getLogger(__name__)


class DivergenceCallback(BaseCallback):
    """Abort training when any train/*_loss becomes non-finite.

    Both DDPG and PPO log their losses under keys matching the pattern
    ``train/*_loss`` (DDPG: actor_loss/critic_loss; PPO: value_loss/
    policy_gradient_loss/entropy_loss/loss). We check ALL of them every
    step; the first non-finite value triggers abort.

    sb3 only populates ``logger.name_to_value`` AFTER each ``log_interval``
    write, so during early steps the dict is empty (no false alarms).
    """

    def __init__(self) -> None:
        super().__init__()
        self.aborted_reason: str | None = None

    def _on_step(self) -> bool:
        try:
            metrics = dict(self.model.logger.name_to_value)
        except AttributeError:
            return True
        for key, value in metrics.items():
            if not key.startswith("train/"):
                continue
            if not key.endswith("_loss"):
                continue
            if value is None:
                continue
            try:
                v = float(value)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(v):
                self.aborted_reason = f"non-finite {key} = {v}"
                log.warning(
                    "DivergenceCallback aborting: %s at step %d",
                    self.aborted_reason,
                    int(self.num_timesteps),
                )
                return False
        return True


class ValMetricsCallback(BaseCallback):
    """Roll out the current policy on val env every ``eval_freq`` steps.

    Writes one JSONL row per eval: step, val_cum_return, val_sharpe.
    Saves the model to ``best_save_path`` when val Sharpe improves.

    Important: env reward is log(pv_t/pv_{t-1}). Cumulative reward = total
    log-return; Sharpe is computed on the per-step reward series.
    """

    def __init__(
        self,
        val_env,
        log_path: Path,
        best_save_path: Path | None = None,
        eval_freq: int = 5000,
        n_eval_episodes: int = 1,
        eval_seed: int = 42,
    ) -> None:
        super().__init__()
        self.val_env = val_env
        self.log_path = Path(log_path)
        self.best_save_path = (
            Path(best_save_path) if best_save_path is not None else None
        )
        self.eval_freq = int(eval_freq)
        self.n_eval_episodes = int(n_eval_episodes)
        self.eval_seed = int(eval_seed)
        self.best_sharpe: float = -float("inf")
        self.eval_count: int = 0

    def _on_step(self) -> bool:
        if self.n_calls == 0 or self.n_calls % self.eval_freq != 0:
            return True
        cum_returns: list[float] = []
        sharpes: list[float] = []
        for ep in range(self.n_eval_episodes):
            cr, sh = self._rollout_once(seed=self.eval_seed + ep)
            cum_returns.append(cr)
            sharpes.append(sh)
        val_cum_return = float(np.mean(cum_returns))
        val_sharpe = float(np.mean(sharpes))
        self.eval_count += 1
        row = {
            "step": int(self.num_timesteps),
            "eval_idx": int(self.eval_count),
            "val_cum_return": val_cum_return,
            "val_sharpe": val_sharpe,
        }
        # Forward known training metrics for offline curves
        try:
            for key, value in dict(self.model.logger.name_to_value).items():
                if key.startswith("train/"):
                    with contextlib.suppress(TypeError, ValueError):
                        row[key] = float(value)
        except AttributeError:
            pass
        self._write_row(row)
        # Save best on Sharpe improvement
        if (
            self.best_save_path is not None
            and math.isfinite(val_sharpe)
            and val_sharpe > self.best_sharpe
        ):
            self.best_sharpe = val_sharpe
            self.best_save_path.parent.mkdir(parents=True, exist_ok=True)
            self.model.save(str(self.best_save_path))
        return True

    def _rollout_once(self, seed: int) -> tuple[float, float]:
        obs, _ = self.val_env.reset(seed=seed)
        rewards: list[float] = []
        terminated = False
        truncated = False
        while not (terminated or truncated):
            action, _state = self.model.predict(obs, deterministic=True)
            obs, reward, terminated, truncated, _ = self.val_env.step(action)
            rewards.append(float(reward))
        if not rewards:
            return 0.0, 0.0
        arr = np.asarray(rewards, dtype=np.float64)
        cum = float(arr.sum())
        std = float(arr.std())
        sharpe = float(arr.mean() / std * math.sqrt(252)) if std > 1e-12 else 0.0
        return cum, sharpe

    def _write_row(self, row: dict) -> None:
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, default=str) + "\n")
        except OSError as e:
            log.warning("val metrics log write failed: %s", e)


class ActionNoiseDecayCallback(BaseCallback):
    """Linearly decay NormalActionNoise.sigma from ``sigma_start`` to
    ``sigma_end`` over training. sb3 doesn't auto-decay.
    """

    def __init__(
        self,
        sigma_start: float,
        sigma_end: float,
        total_timesteps: int,
    ) -> None:
        super().__init__()
        self.sigma_start = float(sigma_start)
        self.sigma_end = float(sigma_end)
        self.total_timesteps = max(int(total_timesteps), 1)

    def _on_step(self) -> bool:
        noise = getattr(self.model, "action_noise", None)
        if noise is None:
            return True
        frac = min(self.num_timesteps / self.total_timesteps, 1.0)
        sigma = self.sigma_start + frac * (self.sigma_end - self.sigma_start)
        # sb3 NormalActionNoise stores per-dim sigma in ._sigma
        if hasattr(noise, "_sigma"):
            shape = np.asarray(noise._sigma).shape
            noise._sigma = np.full(shape, sigma, dtype=np.float64)
        return True
