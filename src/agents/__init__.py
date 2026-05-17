"""Agent registry — name → factory function (SERIALIZED with PKG-S).

CLAUDE.md §"Key Files" marks this as a serialized file: multiple packages
add entries; merge with care. Keep entries alphabetical to minimize PKG-S
merge friction. Keep this minimal — display names, baseline flags etc.
belong in PKG-S extensions.

Every factory takes ``(market_data, news_data, env=None, **kw) -> Agent``
so ``scripts/run_all.py`` can iterate uniformly. ``env`` is supplied (not
None) for agents that consume the env's seeded RNG (RandomAgent).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from src.agent_base import Agent
from src.baselines import BuyAndHold, EqualWeightRebalance, RandomAgent
from src.llm.multi_agent.agent import MultiAgentTrader
from src.llm.single_agentic import SingleAgenticTrader
from src.llm.zero_shot import ZeroShotTrader

AgentFactory = Callable[..., Agent]
DEFAULT_RL_MODEL_DIR = Path("results/models")


def _rl_factory(model_path: Path, name: str) -> AgentFactory:
    """Closure capturing the on-disk model path; each call returns a fresh
    RLAgent so seed/state isn't shared across consecutive runs."""

    def make(market_data, news_data, env=None, **kw: Any) -> Agent:
        # Import locally so importing the registry doesn't pull torch + sb3.
        from src.agents.rl_agent import RLAgent

        return RLAgent(model_path, name=name)

    return make


def _random_factory(market_data, news_data, env=None, **kw: Any) -> Agent:
    if env is None:
        raise ValueError("RandomAgent requires the env (uses env.np_random)")
    return RandomAgent(env)


AGENT_REGISTRY: dict[str, AgentFactory] = {
    "buy_and_hold": lambda md, news, env=None, **kw: BuyAndHold(),
    "ddpg": _rl_factory(DEFAULT_RL_MODEL_DIR / "ddpg_best.zip", "ddpg"),
    "equal_weight": lambda md, news, env=None, **kw: EqualWeightRebalance(),
    "multi_agent": lambda md, news, env=None, **kw: MultiAgentTrader(md, news),
    "ppo": _rl_factory(DEFAULT_RL_MODEL_DIR / "ppo_best.zip", "ppo"),
    "random": _random_factory,
    "single_agentic": lambda md, news, env=None, **kw: SingleAgenticTrader(md, news),
    "zero_shot": lambda md, news, env=None, **kw: ZeroShotTrader(md, news),
}
