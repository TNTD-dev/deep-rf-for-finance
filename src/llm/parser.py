"""Parse LLM JSON output → action ndarray. Robust to markdown wrapping +
malformed responses. Fallback = hold-shares (current portfolio weights), NOT
zero (which would trigger panic-sell at next env step).

Mirrors the post-init weight emission from ``BuyAndHold`` in baselines.py:
``weight_i = (holdings_i + LOT/2) × close_t_i / pv`` — half-lot buffer
absorbs float32 quantization at the action-space boundary.
"""

from __future__ import annotations

import json
import re

import numpy as np

from src import config
from src.llm import metrics

_JSON_BLOCK_RE = re.compile(
    r"```(?:json)?\s*(\{[^`]+?\})\s*```", re.DOTALL
)
_BARE_OBJECT_RE = re.compile(r"\{[^{}]*\}", re.DOTALL)


def parse_weights_json(
    text: str | None,
    info: dict,
    ticker_order: list[str] | None = None,
) -> tuple[np.ndarray, bool]:
    """Returns (action, success). On parse failure, action = hold-shares.

    Records to ``metrics`` for both outcomes so PKG-10 surfaces parse_failure_rate.
    """
    tickers = ticker_order or list(config.TICKERS)
    try:
        weights = _extract_weights(text, tickers)
        metrics.record_parse_success()
        return weights.astype(np.float32), True
    except (ValueError, json.JSONDecodeError, KeyError, TypeError) as e:
        metrics.record_parse_failure(reason=type(e).__name__)
        return _hold_shares_action(info, tickers), False


def _extract_weights(text: str | None, tickers: list[str]) -> np.ndarray:
    if not text:
        raise ValueError("empty text")
    m = _JSON_BLOCK_RE.search(text)
    if m:
        obj = json.loads(m.group(1))
    else:
        m2 = _BARE_OBJECT_RE.search(text)
        if not m2:
            raise ValueError("no JSON object found")
        obj = json.loads(m2.group(0))
    if not isinstance(obj, dict):
        raise ValueError(f"expected dict, got {type(obj).__name__}")
    weights = np.zeros(len(tickers), dtype=np.float64)
    for i, t in enumerate(tickers):
        v = obj.get(t, 0.0)
        if not isinstance(v, (int, float)):
            raise ValueError(f"weight for {t!r} not numeric: {v!r}")
        weights[i] = float(v)
    weights = np.clip(weights, 0.0, 1.0)
    total = weights.sum()
    if total > 1.0:
        weights = weights / total
    return weights


def _hold_shares_action(info: dict, tickers: list[str]) -> np.ndarray:
    """Emit weights matching current holdings so env sees delta_shares = 0.

    Mirrors BuyAndHold.decide post-init logic; same half-lot precision
    buffer to absorb float32 quantization.
    """
    n = len(tickers)
    holdings = np.asarray(
        info.get("holdings", [0] * n), dtype=np.float64
    )
    close_t = np.asarray(
        info.get("close_t", [1.0] * n), dtype=np.float64
    )
    pv = max(float(info.get("portfolio_value", 1.0)), 1e-8)
    buffer_shares = config.LOT_SIZE / 2.0
    return (((holdings + buffer_shares) * close_t) / pv).astype(np.float32)
