"""CLI: run SingleAgenticTrader backtest on a split (default test).

Writes results/single_agentic/{portfolio_curve,holdings}.parquet plus appends
to tool_calls.jsonl. Prints metrics snapshot + audit summary (avg iterations,
hallucination rate).

Usage:
    .venv/bin/python scripts/run_single_agentic.py                       # full test
    .venv/bin/python scripts/run_single_agentic.py --n-sessions 10       # smoke
    .venv/bin/python scripts/run_single_agentic.py --model gpt-4o        # upgrade
    .venv/bin/python scripts/run_single_agentic.py --reset-audit         # fresh log
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

import pandas as pd

from src import config
from src.agent_base import BacktestResult
from src.baselines import _records_to_frames, _snapshot
from src.env_data_loader import load_market_data
from src.llm import metrics
from src.llm.single_agentic import SingleAgenticTrader
from src.trading_env import VNTradingEnv

RESULTS_DIR = config.PROJECT_ROOT / "results" / "single_agentic"
AUDIT_PATH = RESULTS_DIR / "tool_calls.jsonl"
NEWS_PATH = config.PROJECT_ROOT / "data" / "processed" / "news.parquet"


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    p = argparse.ArgumentParser()
    p.add_argument(
        "--split", default="test", choices=["train", "val", "test", "full"]
    )
    p.add_argument(
        "--model",
        default="gpt-4o-mini",
        choices=sorted(config.LLM_ALLOWED_MODELS),
    )
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--max-iterations", type=int, default=10)
    p.add_argument(
        "--n-sessions",
        type=int,
        default=None,
        help="Limit to first N sessions (smoke test); default = full split",
    )
    p.add_argument(
        "--reset-audit",
        action="store_true",
        help="Delete existing audit log before running",
    )
    args = p.parse_args()

    if args.reset_audit and AUDIT_PATH.exists():
        AUDIT_PATH.unlink()

    md = load_market_data(args.split)
    news = pd.read_parquet(NEWS_PATH) if NEWS_PATH.exists() else pd.DataFrame()
    print(
        f"split={args.split}  sessions={len(md.dates)}  "
        f"news_rows={len(news)}  model={args.model}  "
        f"max_iter={args.max_iterations}"
    )

    metrics.reset()
    env = VNTradingEnv(md)
    agent = SingleAgenticTrader(
        market_data=md,
        news_data=news,
        model=args.model,
        max_iterations=args.max_iterations,
        audit_log_path=AUDIT_PATH,
    )
    result = (
        _run_n(env, agent, args.seed, args.n_sessions)
        if args.n_sessions
        else _run_full(env, agent, args.seed)
    )
    _write(result)

    snap = metrics.get_snapshot()
    cum = result.final_pv / float(config.INITIAL_CAPITAL) - 1
    print("\n=== Backtest summary ===")
    print(f"agent:           {result.agent_name}")
    print(f"steps:           {result.n_steps}")
    print(f"final pv:        {result.final_pv:,.0f} VND")
    print(f"cum return:      {cum:+.2%}")
    print(f"LLM calls:       {snap['llm_calls']}")
    print(f"by model:        {snap['by_model']}")
    print(
        f"prompt tokens:   {snap['total_prompt_tokens']:,} "
        f"(cached {snap['total_cached_tokens']:,})"
    )
    print(f"completion:      {snap['total_completion_tokens']:,}")
    print(f"est cost:        ${snap['estimated_cost_usd']:.4f}")
    print(f"parse success:   {snap['parse_success']}")
    print(
        f"parse failure:   {snap['parse_failure']} "
        f"({snap['parse_failure_rate']:.1%})"
    )
    if snap["parse_failure_reasons"]:
        print(f"failure reasons: {snap['parse_failure_reasons']}")
    _print_audit_summary()
    return 0


def _print_audit_summary() -> None:
    """Per-decision summary from audit log: avg iterations, hallucination_rate."""
    if not AUDIT_PATH.exists():
        return
    lines = AUDIT_PATH.read_text(encoding="utf-8").splitlines()
    if not lines:
        return
    recs = [json.loads(ln) for ln in lines]
    decisions = [r for r in recs if r.get("event") == "decision"]
    iters = [r for r in recs if r.get("event") == "iteration"]
    tc_all = [tc for r in iters for tc in r["tool_calls"]]
    tc_errored = [tc for tc in tc_all if tc.get("errored")]
    caps = sum(1 for d in decisions if d.get("cap_hit"))
    avg_iter = sum(d["iterations_used"] for d in decisions) / max(
        len(decisions), 1
    )
    halluc_rate = len(tc_errored) / max(len(tc_all), 1)
    print("\n=== Audit summary ===")
    print(f"decisions:         {len(decisions)}")
    print(f"avg iterations:    {avg_iter:.2f}")
    print(f"cap-hit decisions: {caps}")
    print(f"total tool calls:  {len(tc_all)}")
    print(
        f"tool errors:       {len(tc_errored)} "
        f"({halluc_rate:.1%} hallucination rate)"
    )


def _run_full(
    env: VNTradingEnv, agent: SingleAgenticTrader, seed: int
) -> BacktestResult:
    from src.baselines import run_backtest

    return run_backtest(env, agent, seed=seed)


def _run_n(
    env: VNTradingEnv, agent: SingleAgenticTrader, seed: int, n: int
) -> BacktestResult:
    obs, info = env.reset(seed=seed)
    records: list[dict] = [_snapshot(env, info)]
    total_r, steps = 0.0, 0
    while not env._terminated and steps < n:
        action = agent.decide(obs, info)
        obs, r, term, trunc, info = env.step(action)
        total_r += r
        steps += 1
        records.append(_snapshot(env, info))
    pv_df, h_df = _records_to_frames(records, agent.name)
    return BacktestResult(
        agent_name=agent.name,
        portfolio_curve=pv_df,
        holdings_curve=h_df,
        total_log_return=total_r,
        final_pv=float(info["portfolio_value"]),
        n_steps=steps,
        seed=seed,
    )


def _write(result: BacktestResult) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    result.portfolio_curve.to_parquet(
        RESULTS_DIR / "portfolio_curve.parquet",
        engine="pyarrow",
        compression="snappy",
    )
    result.holdings_curve.to_parquet(
        RESULTS_DIR / "holdings.parquet",
        engine="pyarrow",
        compression="snappy",
    )


if __name__ == "__main__":
    sys.exit(main())
