"""metrics singleton invariants — reset, accumulate, snapshot rate computation."""

from __future__ import annotations

import pytest

from src.llm import metrics


def test_reset_clears_state() -> None:
    """reset() must zero all counters — state from prior backtest can't leak
    into the next one."""
    metrics.record_llm_call(
        "gpt-4o", {"prompt_tokens": 100, "completion_tokens": 10, "cached_tokens": 0}
    )
    metrics.record_parse_failure("JSONDecodeError")
    metrics.reset()
    snap = metrics.get_snapshot()
    assert snap["llm_calls"] == 0
    assert snap["total_prompt_tokens"] == 0
    assert snap["parse_failure"] == 0
    assert snap["estimated_cost_usd"] == 0.0


def test_record_llm_call_accumulates_tokens_and_cost() -> None:
    """Cost = billable_in × in_rate + cached × cached_rate + out × out_rate.

    For gpt-4o-mini: 1500 prompt (1000 cached) + 200 completion =
    500 × 0.15 + 1000 × 0.075 + 200 × 0.60 = 75 + 75 + 120 = 270 micro-USD = 0.000270
    """
    metrics.reset()
    metrics.record_llm_call(
        "gpt-4o-mini",
        {"prompt_tokens": 1500, "completion_tokens": 200, "cached_tokens": 1000},
    )
    snap = metrics.get_snapshot()
    assert snap["llm_calls"] == 1
    assert snap["total_prompt_tokens"] == 1500
    assert snap["total_cached_tokens"] == 1000
    assert snap["estimated_cost_usd"] == pytest.approx(0.000270, rel=1e-9)


def test_record_parse_failure_increments_counter_and_reasons() -> None:
    """Reason strings must accumulate distinctly so PKG-10 can break down failures."""
    metrics.reset()
    metrics.record_parse_failure("JSONDecodeError")
    metrics.record_parse_failure("JSONDecodeError")
    metrics.record_parse_failure("ValueError")
    snap = metrics.get_snapshot()
    assert snap["parse_failure"] == 3
    assert snap["parse_failure_reasons"] == {"JSONDecodeError": 2, "ValueError": 1}


def test_get_snapshot_computes_parse_failure_rate() -> None:
    """parse_failure_rate = failures / (success + failures). Surfacing this
    lets PKG-10 alert when an LLM agent's parse rate drifts."""
    metrics.reset()
    metrics.record_parse_success()
    metrics.record_parse_success()
    metrics.record_parse_success()
    metrics.record_parse_failure("ValueError")
    snap = metrics.get_snapshot()
    assert snap["parse_success"] == 3
    assert snap["parse_failure"] == 1
    assert snap["parse_failure_rate"] == 0.25
