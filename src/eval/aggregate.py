"""LLM-specific metric readers + metrics_table.csv aggregator (PKG-10).

Each agent writes its audit trail in a different shape:
- zero_shot       → metrics_snapshot.json (no per-decision log)
- single_agentic  → tool_calls.jsonl (event=iteration|decision) + snapshot
- multi_agent     → decisions.jsonl (one row per decision)

Tolerant of missing artifacts — non-LLM agents return empty dict;
malformed JSONL lines are skipped with a WARNING (never crash a run).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)


def read_audit_jsonl(path: Path) -> list[dict]:
    """Tolerant JSONL reader. Missing file → []; bad line → skip + warn."""
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError as e:
            log.warning("skip bad jsonl line in %s: %s", path, e)
    return out


def _read_snapshot(agent_dir: Path) -> dict:
    p = agent_dir / "metrics_snapshot.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        log.warning("snapshot read failed at %s: %s", p, e)
        return {}


def _read_zero_shot_metrics(agent_dir: Path) -> dict:
    snap = _read_snapshot(agent_dir)
    if not snap:
        return {}
    return {
        "llm_cost_usd": float(snap.get("estimated_cost_usd", 0.0)),
        "llm_calls": int(snap.get("llm_calls", 0)),
        "parse_failure_rate": float(snap.get("parse_failure_rate", 0.0)),
        "cached_tokens": int(snap.get("total_cached_tokens", 0)),
    }


def _read_single_agentic_metrics(agent_dir: Path) -> dict:
    rows = read_audit_jsonl(agent_dir / "tool_calls.jsonl")
    iters = [r for r in rows if r.get("event") == "iteration"]
    decisions = [r for r in rows if r.get("event") == "decision"]
    all_tcs = [tc for r in iters for tc in r.get("tool_calls", [])]
    errored = sum(1 for tc in all_tcs if tc.get("errored"))
    snap = _read_snapshot(agent_dir)
    out: dict = {}
    if snap:
        out["llm_cost_usd"] = float(snap.get("estimated_cost_usd", 0.0))
        out["llm_calls"] = int(snap.get("llm_calls", 0))
        out["parse_failure_rate"] = float(snap.get("parse_failure_rate", 0.0))
    out["avg_iterations_per_decision"] = (
        sum(d["iterations_used"] for d in decisions) / len(decisions) if decisions else 0.0
    )
    out["hallucination_rate"] = errored / len(all_tcs) if all_tcs else 0.0
    out["cap_hit_rate"] = (
        sum(1 for d in decisions if d.get("cap_hit")) / len(decisions) if decisions else 0.0
    )
    out["n_decisions"] = len(decisions)
    return out


def _read_multi_agent_metrics(agent_dir: Path) -> dict:
    rows = read_audit_jsonl(agent_dir / "decisions.jsonl")
    if not rows:
        return {}
    n = len(rows)
    return {
        "llm_cost_usd": float(sum(r.get("cost_delta_usd", 0.0) for r in rows)),
        "avg_latency_s": float(sum(r["duration_s"] for r in rows) / n),
        "max_latency_s": float(max(r["duration_s"] for r in rows)),
        "timeout_rate": float(sum(bool(r.get("timed_out", False)) for r in rows) / n),
        "node_errors_total": int(sum(r.get("node_errors_count", 0) for r in rows)),
        "avg_debate_rounds": float(sum(r.get("debate_rounds", 0) for r in rows) / n),
        "parse_failure_rate": float(sum(1 for r in rows if not r.get("parse_ok", True)) / n),
        "n_decisions": n,
    }


LLM_AUDIT_READERS: dict[str, Callable[[Path], dict]] = {
    "zero_shot": _read_zero_shot_metrics,
    "single_agentic": _read_single_agentic_metrics,
    "multi_agent": _read_multi_agent_metrics,
}


def read_llm_metrics(agent_name: str, agent_dir: Path) -> dict:
    """Dispatch to the right reader; non-LLM agents → {}."""
    reader = LLM_AUDIT_READERS.get(agent_name)
    return reader(agent_dir) if reader is not None else {}


def build_metrics_table(results_dir: Path) -> pd.DataFrame:
    """Walk results/ collecting per-agent metrics.json into one DataFrame.

    Handles both flat (results/zero_shot/metrics.json) and 1-level-nested
    (results/baselines/buy_and_hold/metrics.json) layouts. Sorted by
    cumulative_return desc when present.
    """
    rows: list[dict] = []
    if not results_dir.exists():
        return pd.DataFrame(rows)
    for agent_dir in sorted(results_dir.iterdir()):
        if not agent_dir.is_dir():
            continue
        metrics_json = agent_dir / "metrics.json"
        if metrics_json.exists():
            try:
                payload = json.loads(metrics_json.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as e:
                log.warning("failed to read %s: %s", metrics_json, e)
                continue
            row = {"agent": payload.get("agent", agent_dir.name)}
            row.update(payload.get("metrics", {}))
            rows.append(row)
        else:
            # Recurse one level for nested baselines/ layout.
            for sub in sorted(agent_dir.iterdir()):
                if not sub.is_dir():
                    continue
                inner = sub / "metrics.json"
                if not inner.exists():
                    continue
                try:
                    payload = json.loads(inner.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as e:
                    log.warning("failed to read %s: %s", inner, e)
                    continue
                row = {"agent": payload.get("agent", sub.name)}
                row.update(payload.get("metrics", {}))
                rows.append(row)
    df = pd.DataFrame(rows)
    if "cumulative_return" in df.columns and not df.empty:
        df = df.sort_values("cumulative_return", ascending=False).reset_index(drop=True)
    return df
