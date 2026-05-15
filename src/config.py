"""Project-wide configuration.

All locked parameters are read from environment variables (default = PRD §15
values). Do NOT change defaults without updating PRD §15 and CLAUDE.md.

Loading order:
1. If `.env` exists at project root, dotenv loads it into `os.environ`.
2. Module-level constants below read from `os.environ` with PRD-locked defaults.

Tests bypass `.env` by pre-setting env vars and `importlib.reload(src.config)`.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent

_env_file = PROJECT_ROOT / ".env"
if _env_file.exists():
    load_dotenv(_env_file, override=False)


def _str(key: str, default: str) -> str:
    return os.getenv(key, default)


def _int(key: str, default: int) -> int:
    raw = os.getenv(key)
    return int(raw) if raw is not None else default


def _float(key: str, default: float) -> float:
    raw = os.getenv(key)
    return float(raw) if raw is not None else default


def _list(key: str, default: str) -> list[str]:
    raw = os.getenv(key, default)
    return [tok.strip() for tok in raw.split(",") if tok.strip()]


# Universe (PRD §15 locked) ---------------------------------------------------
TICKERS: list[str] = _list("TICKERS", "VCB,FPT,HPG,VIC,VNM")

# Period boundaries (PRD §15 locked) ------------------------------------------
TRAIN_START: str = _str("TRAIN_START", "2019-01-01")
VAL_START: str = _str("VAL_START", "2025-01-01")
TEST_START: str = _str("TEST_START", "2025-05-01")
TEST_END: str = _str("TEST_END", "2026-04-30")

# Capital and fees (VND, PRD §15 locked) --------------------------------------
INITIAL_CAPITAL: int = _int("INITIAL_CAPITAL", 1_000_000_000)
BUY_FEE: float = _float("BUY_FEE", 0.0015)
SELL_FEE: float = _float("SELL_FEE", 0.0025)

# HOSE market rules -----------------------------------------------------------
PRICE_BAND: float = _float("PRICE_BAND", 0.07)
LOT_SIZE: int = _int("LOT_SIZE", 100)

# LLM (model lock — CLAUDE.md §"LLM model lock") ------------------------------
LLM_MODEL_PRIMARY: str = _str("LLM_MODEL_PRIMARY", "gpt-4o")
LLM_MODEL_MINI: str = _str("LLM_MODEL_MINI", "gpt-4o-mini")
LLM_ALLOWED_MODELS: frozenset[str] = frozenset({LLM_MODEL_PRIMARY, LLM_MODEL_MINI})

OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
