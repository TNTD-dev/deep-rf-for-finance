"""CLI: load a trained sb3 model via RLAgent, run backtest on a split.

Writes results/{agent_name}/{portfolio_curve,holdings}.parquet for PKG-10.

Usage:
    .venv/bin/python scripts/run_rl_backtest.py --model results/models/ddpg_best.zip
    .venv/bin/python scripts/run_rl_backtest.py --model results/models/ppo_best.zip --split val
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src import config
from src.agents.rl_agent import RLAgent
from src.baselines import run_backtest
from src.env_data_loader import load_market_data
from src.trading_env import VNTradingEnv

RESULTS_DIR = config.PROJECT_ROOT / "results"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--model",
        required=True,
        type=Path,
        help="path to saved sb3 .zip (e.g. results/models/ddpg_best.zip)",
    )
    p.add_argument("--split", default="test", choices=["train", "val", "test"])
    p.add_argument("--seed", type=int, default=42)
    p.add_argument(
        "--name",
        default=None,
        help="agent name override (default: inferred from filename)",
    )
    args = p.parse_args()

    md = load_market_data(args.split)
    env = VNTradingEnv(md)
    agent = RLAgent(args.model, name=args.name)
    print(
        f"agent: {agent.name}  model: {args.model}  "
        f"split: {args.split}  sessions: {len(md.dates)}"
    )

    result = run_backtest(env, agent, seed=args.seed)
    out_dir = RESULTS_DIR / agent.name
    out_dir.mkdir(parents=True, exist_ok=True)
    result.portfolio_curve.to_parquet(
        out_dir / "portfolio_curve.parquet",
        engine="pyarrow",
        compression="snappy",
    )
    result.holdings_curve.to_parquet(
        out_dir / "holdings.parquet",
        engine="pyarrow",
        compression="snappy",
    )

    cum = result.final_pv / float(config.INITIAL_CAPITAL) - 1
    print("\n=== Backtest summary ===")
    print(f"agent:       {result.agent_name}")
    print(f"steps:       {result.n_steps}")
    print(f"final pv:    {result.final_pv:,.0f} VND")
    print(f"cum return:  {cum:+.2%}")
    print(f"saved:       {out_dir}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
