"""Parser invariants — happy paths, malformed cases, hold-shares fallback."""

from __future__ import annotations

import numpy as np

from src import config
from src.llm import metrics
from src.llm.parser import parse_weights_json


def _info() -> dict:
    """Realistic 1-billion-VND scale: each ticker holds ~15-20% of pv.

    Holdings = 5 tickers × ~2-3M shares each = realistic VN portfolio at 1B VND.
    """
    return {
        "holdings": [3_200_000, 2_100_000, 6_900_000, 880_000, 3_000_000],
        "close_t": [55.5, 90.1, 27.4, 215.2, 62.0],
        "portfolio_value": 1_050_000_000.0,
    }


def test_parse_happy_json_block() -> None:
    """Standard ```json {...}``` markdown wrapper → parsed weights."""
    text = '''Analysis:

```json
{"VCB": 0.20, "FPT": 0.25, "HPG": 0.15, "VIC": 0.20, "VNM": 0.10}
```
'''
    action, ok = parse_weights_json(text, _info())
    assert ok is True
    np.testing.assert_allclose(action, [0.20, 0.25, 0.15, 0.20, 0.10], atol=1e-6)


def test_parse_happy_bare_object() -> None:
    """LLM may emit raw {...} without code fence — parser still extracts."""
    text = 'Decision: {"VCB": 0.3, "FPT": 0.2, "HPG": 0.1, "VIC": 0.1, "VNM": 0.1} done.'
    action, ok = parse_weights_json(text, _info())
    assert ok is True
    np.testing.assert_allclose(action, [0.3, 0.2, 0.1, 0.1, 0.1], atol=1e-6)


def test_parse_partial_dict_fills_missing_with_zero() -> None:
    """LLM may omit some tickers — we treat missing as 0 weight (cash)."""
    text = '{"VCB": 0.4, "FPT": 0.3}'
    action, ok = parse_weights_json(text, _info())
    assert ok is True
    np.testing.assert_allclose(action, [0.4, 0.3, 0.0, 0.0, 0.0], atol=1e-6)


def test_parse_renormalizes_when_sum_exceeds_one() -> None:
    """Sum > 1 → divide by total. Env would also do this; we sanity-check."""
    text = '{"VCB": 0.5, "FPT": 0.5, "HPG": 0.5, "VIC": 0.5, "VNM": 0.5}'  # sum=2.5
    action, ok = parse_weights_json(text, _info())
    assert ok is True
    np.testing.assert_allclose(action, [0.2, 0.2, 0.2, 0.2, 0.2], atol=1e-6)


def test_parse_clips_negative_weights_to_zero() -> None:
    """Long-only — negative weights clip. PKG-3 env clips too; defense-in-depth."""
    text = '{"VCB": -0.3, "FPT": 0.5, "HPG": 0.2, "VIC": 0.0, "VNM": 0.0}'
    action, ok = parse_weights_json(text, _info())
    assert ok is True
    assert action[0] == 0.0


def test_parse_failure_returns_hold_shares() -> None:
    """Malformed JSON → hold-shares (NOT zero, which would panic-sell).

    Hold-shares weights = (holdings + LOT/2) × close_t / pv. With sample info,
    weights ~= holdings × price / pv ≈ {0.158, 0.171, 0.130, 0.307, 0.106}
    """
    metrics.reset()
    text = "I refuse to comply, no JSON for you."
    action, ok = parse_weights_json(text, _info())
    assert ok is False
    # Action sums to invested fraction of pv; close to 1 minus cash fraction
    assert action.sum() > 0.5  # significant invested portion
    snap = metrics.get_snapshot()
    assert snap["parse_failure"] == 1


def test_parse_empty_text_returns_hold() -> None:
    """None / empty text — also hold-shares fallback."""
    metrics.reset()
    action, ok = parse_weights_json(None, _info())
    assert ok is False
    assert action.shape == (len(config.TICKERS),)


def test_parse_records_metric_for_success_and_failure() -> None:
    """Both paths must accumulate counters distinctly so PKG-10 can break
    down parse_failure_rate."""
    metrics.reset()
    parse_weights_json('{"VCB": 0.2}', _info())  # success
    parse_weights_json("garbage", _info())  # failure
    parse_weights_json("more garbage", _info())  # failure
    snap = metrics.get_snapshot()
    assert snap["parse_success"] == 1
    assert snap["parse_failure"] == 2
    assert snap["parse_failure_rate"] == 2 / 3
