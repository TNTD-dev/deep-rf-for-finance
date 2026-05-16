"""Agent Protocol + BacktestResult dataclass — the interface contract.

Every agent in this project (BuyAndHold, EqualWeightRebalance, RandomAgent,
DDPG via sb3 wrapper, LLM zero-shot, single-agentic, multi-agent) implements
``decide(obs, info) -> action``.

Protocol is ``runtime_checkable`` so ``isinstance(obj, Agent)`` works for
sanity asserts. Not enforced — duck-typing is fine if obj has ``.name`` and
``.decide()``.

This file is intentionally separate from ``src/agents/__init__.py``. That file
is PKG-S serialized (multiple packages add registry entries); keeping the
Protocol here lets every package import it without touching the registry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import numpy as np
import pandas as pd


@runtime_checkable
class Agent(Protocol):
    """Pluggable agent interface (CLAUDE.md §"Patterns")."""

    name: str  # short identifier, used in filesystem paths

    def decide(self, obs: np.ndarray, info: dict) -> np.ndarray:
        """Return action in env.action_space = Box(-1, 1, (n_tickers,)).

        Args:
            obs: 56-dim float32 observation from VNTradingEnv.
            info: env info dict with keys date, t, cash, holdings,
                portfolio_value. Agents may consume any subset — RL agents
                typically use only obs; LLM agents typically use info['date']
                for schedule and inspect holdings/cash for context.
        """
        ...


@dataclass(frozen=True)
class BacktestResult:
    """Output of run_backtest. Immutable so downstream metric code can't
    mutate the trajectory mid-analysis."""

    agent_name: str
    portfolio_curve: pd.DataFrame   # date, agent_name, portfolio_value, cash, w_*
    holdings_curve: pd.DataFrame    # date, agent_name, h_*
    total_log_return: float
    final_pv: float
    n_steps: int
    seed: int
