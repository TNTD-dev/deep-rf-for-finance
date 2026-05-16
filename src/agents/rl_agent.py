"""RLAgent — Agent Protocol wrapper around a saved sb3 model (PKG-9).

Auto-detects algorithm from filename stem ("ddpg_*" → DDPG, "ppo_*" → PPO).
Caller can override via ``algo=DDPG`` or ``algo=PPO``.

Used by ``scripts/run_rl_backtest.py`` and PKG-10 backtest harness.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from stable_baselines3 import DDPG, PPO


class RLAgent:
    """Wraps a saved stable_baselines3 model. Implements Agent Protocol."""

    def __init__(
        self,
        model_path: Path | str,
        name: str | None = None,
        algo: type | None = None,
        deterministic: bool = True,
    ) -> None:
        self.model_path = Path(model_path)
        if not self.model_path.exists():
            raise FileNotFoundError(f"model not found: {self.model_path}")
        self._algo = algo or self._detect_algo(self.model_path)
        self._model = self._algo.load(str(self.model_path))
        self.name = name or self.model_path.stem.split("_")[0] or "rl"
        self.deterministic = bool(deterministic)

    @staticmethod
    def _detect_algo(model_path: Path) -> type:
        stem = model_path.stem.lower()
        if "ddpg" in stem:
            return DDPG
        if "ppo" in stem:
            return PPO
        # Default to DDPG (project's primary RL algo)
        return DDPG

    def decide(self, obs: np.ndarray, info: dict) -> np.ndarray:
        action, _state = self._model.predict(
            obs, deterministic=self.deterministic
        )
        return np.asarray(action, dtype=np.float32)
