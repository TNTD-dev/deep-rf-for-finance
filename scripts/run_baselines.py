"""CLI: run 3 baseline agents on a split, save portfolio curves + summary.

Output: ``results/baselines/{agent}/portfolio_curve.parquet`` and
``holdings.parquet`` per agent. Console prints summary table with final
cumulative return for each.

Usage:
    .venv/bin/python scripts/run_baselines.py
    .venv/bin/python scripts/run_baselines.py --split val --seed 0
"""

from __future__ import annotations

import argparse
import logging
import sys

import pandas as pd

from src import config
from src.agent_base import BacktestResult
from src.baselines import (
    BuyAndHold,
    EqualWeightRebalance,
    RandomAgent,
    run_backtest,
)
from src.env_data_loader import load_market_data
from src.trading_env import VNTradingEnv

RESULTS_DIR = config.PROJECT_ROOT / "results" / "baselines"


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    p = argparse.ArgumentParser()
    p.add_argument(
        "--split", default="test", choices=["train", "val", "test", "full"]
    )
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    md = load_market_data(args.split)
    print(
        f"split={args.split}: {len(md.dates)} sessions "
        f"({md.dates[0].date()} → {md.dates[-1].date()}), "
        f"warmup_offset={md.warmup_offset}"
    )

    summary_rows: list[dict] = []
    for agent_kind in ("buy_and_hold", "equal_weight", "random"):
        env = VNTradingEnv(md)
        if agent_kind == "buy_and_hold":
            agent = BuyAndHold()
        elif agent_kind == "equal_weight":
            agent = EqualWeightRebalance()
        else:
            env.reset(seed=args.seed)  # seed RNG before RandomAgent borrows
            agent = RandomAgent(env)
        result = run_backtest(env, agent, seed=args.seed)
        _write(result)
        summary_rows.append(
            {
                "agent": result.agent_name,
                "n_steps": result.n_steps,
                "total_log_r": round(result.total_log_return, 4),
                "final_pv": int(result.final_pv),
                "cumulative_return": round(
                    result.final_pv / float(config.INITIAL_CAPITAL) - 1, 4
                ),
            }
        )

    print(f"\n=== Baselines on split={args.split} seed={args.seed} ===")
    print(pd.DataFrame(summary_rows).to_string(index=False))
    print(f"\nArtifacts: {RESULTS_DIR}/")
    return 0


def _write(result: BacktestResult) -> None:
    d = RESULTS_DIR / result.agent_name
    d.mkdir(parents=True, exist_ok=True)
    result.portfolio_curve.to_parquet(
        d / "portfolio_curve.parquet", engine="pyarrow", compression="snappy"
    )
    result.holdings_curve.to_parquet(
        d / "holdings.parquet", engine="pyarrow", compression="snappy"
    )
    print(
        f"wrote {result.agent_name}: {result.n_steps} steps, "
        f"log-r={result.total_log_return:+.4f}, pv={result.final_pv:,.0f}"
    )


if __name__ == "__main__":
    sys.exit(main())
