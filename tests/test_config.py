"""Verify config reads correct values from .env.example.

Acceptance for PKG-0: every constant in src/config.py matches the value
documented in .env.example. If a future PR changes either side without
updating both, this test fails loudly.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent


def test_env_example_exists() -> None:
    assert (ROOT / ".env.example").exists(), ".env.example is required for onboarding"


def test_env_example_has_all_required_keys() -> None:
    values = dotenv_values(ROOT / ".env.example")
    required = {
        "OPENAI_API_KEY",
        "LLM_MODEL_PRIMARY",
        "LLM_MODEL_MINI",
        "TICKERS",
        "TRAIN_START",
        "VAL_START",
        "TEST_START",
        "TEST_END",
        "INITIAL_CAPITAL",
        "BUY_FEE",
        "SELL_FEE",
        "PRICE_BAND",
        "LOT_SIZE",
    }
    missing = required - set(values)
    assert not missing, f".env.example missing required keys: {missing}"


@pytest.fixture
def cfg_from_env_example(monkeypatch):
    """Load .env.example values into process env, reload config, return module."""
    values = dotenv_values(ROOT / ".env.example")
    for key, val in values.items():
        if val is not None:
            monkeypatch.setenv(key, val)
    import src.config as cfg

    importlib.reload(cfg)
    return cfg


def test_universe_locked(cfg_from_env_example) -> None:
    # PRD §15: 5 specific VN30 tickers, order-sensitive for some metrics
    assert cfg_from_env_example.TICKERS == ["VCB", "FPT", "HPG", "VIC", "VNM"]


def test_period_boundaries_locked(cfg_from_env_example) -> None:
    # PRD §15: train 2019-01 → 2024-12, val Q1-2025, test 2025-05 → 2026-04
    assert cfg_from_env_example.TRAIN_START == "2019-01-01"
    assert cfg_from_env_example.VAL_START == "2025-01-01"
    assert cfg_from_env_example.TEST_START == "2025-05-01"
    assert cfg_from_env_example.TEST_END == "2026-04-30"


def test_capital_and_fees(cfg_from_env_example) -> None:
    cfg = cfg_from_env_example
    # PRD §15: 1 billion VND minimum for lot-100 rounding not to dominate
    assert cfg.INITIAL_CAPITAL == 1_000_000_000
    # PRD §15: asymmetric fees (sell includes 0.1% transfer tax)
    assert cfg.BUY_FEE == 0.0015
    assert cfg.SELL_FEE == 0.0025
    # Invariant: sell costs more than buy. If this flips, env logic breaks.
    assert cfg.SELL_FEE > cfg.BUY_FEE


def test_hose_market_rules(cfg_from_env_example) -> None:
    # HOSE daily limit and lot size — model in env, not at callsite
    assert cfg_from_env_example.PRICE_BAND == 0.07
    assert cfg_from_env_example.LOT_SIZE == 100


def test_llm_model_lock(cfg_from_env_example) -> None:
    cfg = cfg_from_env_example
    # CLAUDE.md "LLM model lock": only cutoff-Oct-2023 models permitted
    assert cfg.LLM_MODEL_PRIMARY == "gpt-4o"
    assert cfg.LLM_MODEL_MINI == "gpt-4o-mini"
    assert set(cfg.LLM_ALLOWED_MODELS) == {"gpt-4o", "gpt-4o-mini"}
