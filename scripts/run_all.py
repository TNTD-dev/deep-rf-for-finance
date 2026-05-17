"""Run all agents end-to-end + build the cross-agent metrics_table.csv.

Usage:
    .venv/bin/python scripts/run_all.py                          # all agents
    .venv/bin/python scripts/run_all.py --agents zero_shot ddpg  # subset
    .venv/bin/python scripts/run_all.py --skip-existing          # reuse cache

``--skip-existing`` checks for ``results/{agent}/metrics.json +
portfolio_curve.parquet``; when both are present, the agent is NOT re-run
and the cached artifacts feed the aggregated ``metrics_table.csv``. Use
this for dev iteration so iterating on one agent doesn't re-burn LLM cost
on the others.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

import pandas as pd

from src import config
from src.agents import AGENT_REGISTRY
from src.env_data_loader import load_market_data
from src.eval.aggregate import build_metrics_table, read_llm_metrics
from src.eval.backtest import (
    build_payload,
    run_and_score,
    save_artifacts,
    score_from_cache,
)
from src.llm import metrics as llm_metrics_mod
from src.trading_env import VNTradingEnv

log = logging.getLogger("run_all")

RESULTS_DIR = config.PROJECT_ROOT / "results"
NEWS_PATH = config.PROJECT_ROOT / "data" / "processed" / "news.parquet"


def _has_results(agent_name: str) -> bool:
    d = RESULTS_DIR / agent_name
    return (d / "metrics.json").exists() and (d / "portfolio_curve.parquet").exists()


def _has_parquets_only(agent_name: str) -> bool:
    d = RESULTS_DIR / agent_name
    return (d / "portfolio_curve.parquet").exists() and not (d / "metrics.json").exists()


def _test_window() -> tuple[str, str]:
    return (str(config.TEST_START)[:10], str(config.TEST_END)[:10])


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--split", default="test", choices=["train", "val", "test", "full"])
    p.add_argument("--seed", type=int, default=42)
    p.add_argument(
        "--agents",
        nargs="+",
        default=None,
        help=f"Subset to run; default ALL: {sorted(AGENT_REGISTRY)}",
    )
    p.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip agents whose metrics.json + portfolio_curve.parquet exist",
    )
    args = p.parse_args()

    md = load_market_data(args.split)
    news = pd.read_parquet(NEWS_PATH) if NEWS_PATH.exists() else pd.DataFrame()
    log.info("split=%s sessions=%d news_rows=%d", args.split, len(md.dates), len(news))

    agents_to_run = args.agents or list(AGENT_REGISTRY.keys())
    window = _test_window() if args.split == "test" else None

    for name in agents_to_run:
        if name not in AGENT_REGISTRY:
            log.warning("unknown agent %r — skip", name)
            continue
        if args.skip_existing and _has_results(name):
            log.info("skip %s (cached metrics.json + parquets exist)", name)
            continue
        if args.skip_existing and _has_parquets_only(name):
            agent_dir = RESULTS_DIR / name
            llm_extra = read_llm_metrics(name, agent_dir)
            payload = score_from_cache(
                name,
                agent_dir,
                market_data=md,
                seed=args.seed,
                test_window=window,
                llm_metrics=llm_extra,
            )
            if payload is not None:
                m = payload["metrics"]
                log.info(
                    "rebuilt %s from cached parquets: cum=%+.2f%% sharpe=%.2f",
                    name,
                    m.get("cumulative_return", 0.0) * 100,
                    m.get("sharpe", 0.0),
                )
                continue

        log.info("=== %s ===", name)
        factory = AGENT_REGISTRY[name]
        env = VNTradingEnv(md)
        try:
            agent = factory(md, news, env=env)
        except FileNotFoundError as e:
            log.warning("cannot construct %s: %s — skip", name, e)
            continue

        # Reset LLM in-process metrics so the per-agent snapshot captures
        # only this agent's spend.
        llm_metrics_mod.reset()
        result, fin_metrics = run_and_score(agent, market_data=md, env=env, seed=args.seed)

        # Persist in-process LLM snapshot for non-multi-agent (zero/single).
        agent_dir = RESULTS_DIR / name
        agent_dir.mkdir(parents=True, exist_ok=True)
        snap = llm_metrics_mod.get_snapshot()
        (agent_dir / "metrics_snapshot.json").write_text(
            json.dumps(snap, default=str, indent=2),
            encoding="utf-8",
        )

        llm_extra = read_llm_metrics(name, agent_dir)
        payload = build_payload(
            result,
            fin_metrics,
            llm_metrics=llm_extra,
            test_window=window,
            seed=args.seed,
        )
        save_artifacts(payload, result, RESULTS_DIR)

        cum = fin_metrics.get("cumulative_return", 0.0)
        sharpe = fin_metrics.get("sharpe", 0.0)
        log.info(
            "%s done: cum=%+.2f%% sharpe=%.2f steps=%d",
            name,
            cum * 100,
            sharpe,
            result.n_steps,
        )

    # Build the cross-agent table from whatever metrics.json files are on disk
    # (including untouched cached agents under --skip-existing).
    table = build_metrics_table(RESULTS_DIR)
    table_path = RESULTS_DIR / "metrics_table.csv"
    table.to_csv(table_path, index=False)
    log.info("metrics_table.csv: %d rows → %s", len(table), table_path)
    if not table.empty:
        print(table.to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
