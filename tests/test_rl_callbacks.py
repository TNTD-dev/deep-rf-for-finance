"""sb3 callback invariants — Divergence, ValMetrics, ActionNoiseDecay.

Uses mocks for sb3 model + env to keep tests fast (no real training).
"""

from __future__ import annotations

import json
import math
from unittest.mock import MagicMock

import numpy as np

from src.rl_training.callbacks import (
    ActionNoiseDecayCallback,
    DivergenceCallback,
    ValMetricsCallback,
)


def _make_model_with_metrics(metrics: dict, num_timesteps: int = 100) -> MagicMock:
    """Build a fake sb3 model exposing logger.name_to_value + num_timesteps."""
    model = MagicMock()
    model.logger.name_to_value = metrics
    model.num_timesteps = num_timesteps
    return model


def _attach_callback(cb, model: MagicMock) -> None:
    """sb3 binds model via init_callback; mimic that here."""
    cb.model = model
    cb.n_calls = 0
    cb.num_timesteps = model.num_timesteps


def test_divergence_callback_aborts_on_nan_critic_loss():
    """DDPG-style: NaN in train/critic_loss → _on_step returns False."""
    cb = DivergenceCallback()
    model = _make_model_with_metrics(
        {"train/critic_loss": float("nan"), "train/actor_loss": 0.5}
    )
    _attach_callback(cb, model)
    cb.n_calls = 1
    assert cb._on_step() is False
    assert cb.aborted_reason is not None
    assert "critic_loss" in cb.aborted_reason


def test_divergence_callback_aborts_on_inf_value_loss():
    """PPO-style: Inf in train/value_loss → abort. Algo-agnostic via *_loss pattern."""
    cb = DivergenceCallback()
    model = _make_model_with_metrics(
        {
            "train/value_loss": float("inf"),
            "train/policy_gradient_loss": 0.1,
            "train/entropy_loss": -0.01,
        }
    )
    _attach_callback(cb, model)
    cb.n_calls = 1
    assert cb._on_step() is False
    assert "value_loss" in cb.aborted_reason


def test_divergence_callback_passes_on_finite_losses():
    """Healthy training step → no abort, returns True."""
    cb = DivergenceCallback()
    model = _make_model_with_metrics(
        {"train/critic_loss": 0.5, "train/actor_loss": 0.2}
    )
    _attach_callback(cb, model)
    cb.n_calls = 1
    assert cb._on_step() is True
    assert cb.aborted_reason is None


def test_divergence_callback_skips_non_loss_keys():
    """train/learning_rate is non-finite by spec? No — but defensively, the
    callback ONLY checks keys matching train/*_loss to avoid false positives."""
    cb = DivergenceCallback()
    model = _make_model_with_metrics(
        {
            "train/learning_rate": float("nan"),  # bizarre but shouldn't abort
            "train/actor_loss": 0.5,
            "train/critic_loss": 0.3,
        }
    )
    _attach_callback(cb, model)
    cb.n_calls = 1
    assert cb._on_step() is True


def test_val_metrics_callback_writes_jsonl_at_eval_freq(tmp_path):
    """At step == eval_freq, callback runs a rollout and appends one JSONL line."""
    log_path = tmp_path / "val.jsonl"
    val_env = MagicMock()
    # 3-step episode: reset → step → step → step (done)
    val_env.reset.return_value = (np.zeros(56, dtype=np.float32), {})
    val_env.step.side_effect = [
        (np.zeros(56, dtype=np.float32), 0.01, False, False, {}),
        (np.zeros(56, dtype=np.float32), 0.02, False, False, {}),
        (np.zeros(56, dtype=np.float32), -0.01, True, False, {}),
    ]

    cb = ValMetricsCallback(
        val_env=val_env,
        log_path=log_path,
        eval_freq=10,
        n_eval_episodes=1,
    )
    model = MagicMock()
    model.predict.return_value = (np.zeros(5, dtype=np.float32), None)
    model.logger.name_to_value = {"train/critic_loss": 0.5}
    model.num_timesteps = 10
    _attach_callback(cb, model)
    cb.n_calls = 10  # triggers eval (n_calls % eval_freq == 0)
    cb.num_timesteps = 10
    assert cb._on_step() is True

    lines = log_path.read_text().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["step"] == 10
    assert row["eval_idx"] == 1
    assert row["val_cum_return"] == 0.01 + 0.02 - 0.01  # sum of step rewards
    assert "val_sharpe" in row
    assert row["train/critic_loss"] == 0.5  # train metrics forwarded


def test_val_metrics_callback_saves_best_on_sharpe_improvement(tmp_path):
    """Two evals: first sets best; second with higher Sharpe triggers second save."""
    log_path = tmp_path / "val.jsonl"
    best_path = tmp_path / "best.zip"
    val_env = MagicMock()
    val_env.reset.return_value = (np.zeros(56, dtype=np.float32), {})
    # Cycle of returns: (0.01, 0.02, done) → cum=0.03 mean 0.01 std ~0.005 high Sharpe
    val_env.step.side_effect = [
        (np.zeros(56, dtype=np.float32), 0.01, False, False, {}),
        (np.zeros(56, dtype=np.float32), 0.02, True, False, {}),
        # Second eval — DIFFERENT, higher cum
        (np.zeros(56, dtype=np.float32), 0.03, False, False, {}),
        (np.zeros(56, dtype=np.float32), 0.04, True, False, {}),
    ]
    cb = ValMetricsCallback(
        val_env=val_env,
        log_path=log_path,
        best_save_path=best_path,
        eval_freq=10,
        n_eval_episodes=1,
    )
    model = MagicMock()
    model.predict.return_value = (np.zeros(5, dtype=np.float32), None)
    model.logger.name_to_value = {}
    model.num_timesteps = 10
    _attach_callback(cb, model)
    cb.n_calls = 10
    cb.num_timesteps = 10
    cb._on_step()
    first_sharpe = cb.best_sharpe
    cb.n_calls = 20
    cb.num_timesteps = 20
    cb._on_step()
    assert model.save.call_count == 2
    assert cb.best_sharpe > first_sharpe


def test_val_metrics_callback_no_eval_outside_freq(tmp_path):
    """n_calls not divisible by eval_freq → no rollout, no write."""
    log_path = tmp_path / "val.jsonl"
    val_env = MagicMock()
    cb = ValMetricsCallback(val_env=val_env, log_path=log_path, eval_freq=10)
    model = MagicMock()
    model.num_timesteps = 5
    _attach_callback(cb, model)
    cb.n_calls = 5  # not multiple of 10
    cb._on_step()
    assert val_env.reset.call_count == 0
    assert not log_path.exists()


def test_action_noise_decay_interpolates_linearly():
    """At step 0 sigma = start; at step total sigma = end; at step total/2 → midpoint."""
    cb = ActionNoiseDecayCallback(sigma_start=0.1, sigma_end=0.02, total_timesteps=1000)
    model = MagicMock()
    model.action_noise = MagicMock()
    model.action_noise._sigma = np.array([0.1, 0.1, 0.1, 0.1, 0.1])
    _attach_callback(cb, model)
    # At step 0 → sigma_start
    cb.num_timesteps = 0
    cb._on_step()
    assert math.isclose(model.action_noise._sigma[0], 0.1, abs_tol=1e-6)
    # At step 500 → midpoint = 0.06
    cb.num_timesteps = 500
    cb._on_step()
    assert math.isclose(model.action_noise._sigma[0], 0.06, abs_tol=1e-6)
    # At step 1000 → sigma_end = 0.02
    cb.num_timesteps = 1000
    cb._on_step()
    assert math.isclose(model.action_noise._sigma[0], 0.02, abs_tol=1e-6)


def test_action_noise_decay_safe_when_noise_absent():
    """PPO has action_noise=None — callback should be a no-op, not crash."""
    cb = ActionNoiseDecayCallback(sigma_start=0.1, sigma_end=0.02, total_timesteps=1000)
    model = MagicMock()
    model.action_noise = None
    _attach_callback(cb, model)
    cb.num_timesteps = 500
    assert cb._on_step() is True  # no crash, returns True
