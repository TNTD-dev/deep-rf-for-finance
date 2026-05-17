"""Tests for src/eval/aggregate.py — JSONL readers + metrics_table builder."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.eval import aggregate as A

# ---------- read_audit_jsonl -------------------------------------------------


def test_read_audit_jsonl_handles_missing_file(tmp_path: Path) -> None:
    assert A.read_audit_jsonl(tmp_path / "nope.jsonl") == []


def test_read_audit_jsonl_skips_bad_lines(tmp_path: Path) -> None:
    p = tmp_path / "audit.jsonl"
    p.write_text(
        '{"a": 1}\nnot-json\n\n{"b": 2}\n',
        encoding="utf-8",
    )
    rows = A.read_audit_jsonl(p)
    assert rows == [{"a": 1}, {"b": 2}]


# ---------- multi_agent reader -----------------------------------------------


def test_multi_agent_reader_aggregates_decisions(tmp_path: Path) -> None:
    (tmp_path / "decisions.jsonl").write_text(
        json.dumps(
            {
                "duration_s": 20.0,
                "cost_delta_usd": 0.05,
                "timed_out": False,
                "debate_rounds": 2,
                "node_errors_count": 0,
                "parse_ok": True,
            }
        )
        + "\n"
        + json.dumps(
            {
                "duration_s": 40.0,
                "cost_delta_usd": 0.10,
                "timed_out": True,
                "debate_rounds": 3,
                "node_errors_count": 1,
                "parse_ok": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    m = A._read_multi_agent_metrics(tmp_path)
    assert m["n_decisions"] == 2
    assert m["llm_cost_usd"] == pytest.approx(0.15)
    assert m["avg_latency_s"] == pytest.approx(30.0)
    assert m["max_latency_s"] == 40.0
    assert m["timeout_rate"] == 0.5
    assert m["node_errors_total"] == 1
    assert m["avg_debate_rounds"] == 2.5
    assert m["parse_failure_rate"] == 0.0


def test_multi_agent_reader_missing_file_returns_empty(tmp_path: Path) -> None:
    assert A._read_multi_agent_metrics(tmp_path) == {}


# ---------- single_agentic reader --------------------------------------------


def test_single_agentic_reader_computes_hallucination_rate(tmp_path: Path) -> None:
    (tmp_path / "tool_calls.jsonl").write_text(
        json.dumps(
            {
                "event": "iteration",
                "tool_calls": [
                    {"name": "get_price", "errored": False},
                    {"name": "get_news", "errored": True},
                    {"name": "get_news", "errored": False},
                ],
            }
        )
        + "\n"
        + json.dumps(
            {
                "event": "decision",
                "iterations_used": 2,
                "cap_hit": False,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    m = A._read_single_agentic_metrics(tmp_path)
    assert m["hallucination_rate"] == pytest.approx(1 / 3)
    assert m["n_decisions"] == 1
    assert m["avg_iterations_per_decision"] == 2.0
    assert m["cap_hit_rate"] == 0.0


# ---------- dispatcher -------------------------------------------------------


def test_read_llm_metrics_returns_empty_for_unknown_agent(tmp_path: Path) -> None:
    assert A.read_llm_metrics("random", tmp_path) == {}
    assert A.read_llm_metrics("ddpg", tmp_path) == {}


# ---------- build_metrics_table ----------------------------------------------


def _write_metrics_json(p: Path, agent: str, cum: float) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(
            {
                "agent": agent,
                "portfolio_curve": [],
                "holdings": [],
                "metrics": {"cumulative_return": cum, "sharpe": 1.5},
            }
        ),
        encoding="utf-8",
    )


def test_build_metrics_table_handles_nested_baselines_dir(tmp_path: Path) -> None:
    # Flat layout for one agent, nested for another.
    _write_metrics_json(tmp_path / "zero_shot" / "metrics.json", "zero_shot", 0.10)
    _write_metrics_json(
        tmp_path / "baselines" / "buy_and_hold" / "metrics.json",
        "buy_and_hold",
        1.03,
    )
    _write_metrics_json(
        tmp_path / "baselines" / "random" / "metrics.json",
        "random",
        -0.37,
    )

    df = A.build_metrics_table(tmp_path)
    assert sorted(df["agent"].tolist()) == ["buy_and_hold", "random", "zero_shot"]
    # Sorted by cumulative_return desc
    assert df.iloc[0]["agent"] == "buy_and_hold"
    assert df.iloc[-1]["agent"] == "random"
    assert "sharpe" in df.columns


def test_build_metrics_table_missing_dir_returns_empty(tmp_path: Path) -> None:
    out = A.build_metrics_table(tmp_path / "does-not-exist")
    assert isinstance(out, pd.DataFrame)
    assert out.empty
