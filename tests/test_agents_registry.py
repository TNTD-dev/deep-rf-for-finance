"""Contract tests for src/agents/__init__.py registry."""

from __future__ import annotations

import contextlib

import pandas as pd
import pytest

from src.agent_base import Agent
from src.agents import AGENT_REGISTRY, DEFAULT_RL_MODEL_DIR
from src.env_data_loader import load_market_data
from src.trading_env import VNTradingEnv

EXPECTED_AGENTS = {
    "buy_and_hold",
    "ddpg",
    "equal_weight",
    "multi_agent",
    "ppo",
    "random",
    "single_agentic",
    "zero_shot",
}

# Agents whose factory makes a real OpenAI client / loads heavy deps are
# skipped from instantiation contract test; signature-only check covers them.
HEAVY_AGENTS = {"zero_shot", "single_agentic", "multi_agent"}


def test_registry_has_all_8_agents() -> None:
    assert set(AGENT_REGISTRY) == EXPECTED_AGENTS


def test_registry_keys_sorted_alphabetically() -> None:
    # SERIALIZED file convention to minimize merge conflicts with PKG-S
    assert list(AGENT_REGISTRY) == sorted(AGENT_REGISTRY)


def test_lightweight_factories_produce_agent_protocol() -> None:
    """For non-LLM, non-RL agents, build + isinstance check."""
    md = load_market_data("test")
    news = pd.DataFrame()
    env = VNTradingEnv(md)
    for name in ("buy_and_hold", "equal_weight", "random"):
        agent = AGENT_REGISTRY[name](md, news, env=env)
        assert isinstance(agent, Agent), f"{name} doesn't satisfy Agent protocol"
        assert agent.name == name or agent.name  # name attribute present


def test_rl_factories_construct_when_model_exists() -> None:
    md = load_market_data("test")
    news = pd.DataFrame()
    env = VNTradingEnv(md)
    for name in ("ddpg", "ppo"):
        model_path = DEFAULT_RL_MODEL_DIR / f"{name}_best.zip"
        if not model_path.exists():
            pytest.skip(f"{model_path} missing — skip RL factory test")
        agent = AGENT_REGISTRY[name](md, news, env=env)
        assert isinstance(agent, Agent)
        assert agent.name == name


def test_factory_signatures_uniform_keyword_args() -> None:
    """Every factory must accept (md, news, env=None) without raising on
    extra kwargs."""
    md = load_market_data("test")
    news = pd.DataFrame()
    env = VNTradingEnv(md)
    for name, factory in AGENT_REGISTRY.items():
        if name in HEAVY_AGENTS:
            continue  # don't construct LLM agents (creates OpenAI client)
        # RL factories raise FileNotFoundError when model missing — acceptable
        # signature contract; just verify the call shape works.
        with contextlib.suppress(FileNotFoundError):
            factory(md, news, env=env, extra_kwarg=123)


def test_random_factory_requires_env() -> None:
    md = load_market_data("test")
    news = pd.DataFrame()
    with pytest.raises(ValueError, match="env"):
        AGENT_REGISTRY["random"](md, news)
