"""LLM call + parser metrics. Module-level singleton.

PKG-10 will call ``reset()`` before a backtest and ``get_snapshot()`` after,
attaching the snapshot to the backtest result. Singleton is acceptable
because we run sequentially (one backtest per process); if we ever introduce
concurrency, this needs a refactor.

Cost model is hardcoded:
    gpt-4o:      $2.50/1M input,  $10/1M output, cached input 50% off
    gpt-4o-mini: $0.15/1M input,  $0.60/1M output, cached input 50% off
"""

from __future__ import annotations

import collections
from typing import Any

_PRICING: dict[str, dict[str, float]] = {
    "gpt-4o":      {"in": 2.50e-6, "out": 10.0e-6, "cached_in": 1.25e-6},
    "gpt-4o-mini": {"in": 0.15e-6, "out": 0.60e-6, "cached_in": 0.075e-6},
}

_state: dict[str, Any] = {}


def reset() -> None:
    _state.clear()
    _state.update(
        {
            "llm_calls": 0,
            "by_model": collections.Counter(),
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
            "total_cached_tokens": 0,
            "estimated_cost_usd": 0.0,
            "parse_success": 0,
            "parse_failure": 0,
            "parse_failure_reasons": collections.Counter(),
        }
    )


def record_llm_call(model: str, usage: dict) -> None:
    _state["llm_calls"] += 1
    _state["by_model"][model] += 1
    pt = int(usage.get("prompt_tokens", 0))
    ct = int(usage.get("completion_tokens", 0))
    cached = int(usage.get("cached_tokens", 0))
    _state["total_prompt_tokens"] += pt
    _state["total_completion_tokens"] += ct
    _state["total_cached_tokens"] += cached
    if model in _PRICING:
        p = _PRICING[model]
        billable_in = max(0, pt - cached)
        _state["estimated_cost_usd"] += (
            billable_in * p["in"] + cached * p["cached_in"] + ct * p["out"]
        )


def record_parse_success() -> None:
    _state["parse_success"] += 1


def record_parse_failure(reason: str) -> None:
    _state["parse_failure"] += 1
    _state["parse_failure_reasons"][reason] += 1


def get_snapshot() -> dict:
    total = _state["parse_success"] + _state["parse_failure"]
    rate = _state["parse_failure"] / total if total else 0.0
    snap = dict(_state)
    snap["parse_failure_rate"] = rate
    snap["by_model"] = dict(_state["by_model"])
    snap["parse_failure_reasons"] = dict(_state["parse_failure_reasons"])
    return snap


reset()  # initialize on import
