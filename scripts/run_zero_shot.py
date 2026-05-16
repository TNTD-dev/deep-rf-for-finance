"""CLI: run ZeroShotTrader backtest on a split (default test).

Writes results/zero_shot/{portfolio_curve,holdings}.parquet plus prints
metrics snapshot (cost USD, parse_failure_rate, llm_calls).

Usage:
    .venv/bin/python scripts/run_zero_shot.py                     # full test
    .venv/bin/python scripts/run_zero_shot.py --n-sessions 10     # smoke
    .venv/bin/python scripts/run_zero_shot.py --model gpt-4o      # upgrade model
"""

from __future__ import annotations

import argparse
import logging
import sys

import pandas as pd

from src import config
from src.agent_base import BacktestResult
from src.baselines import _records_to_frames, _snapshot
from src.env_data_loader import load_market_data
from src.llm import metrics
from src.llm.zero_shot import ZeroShotTrader
from src.trading_env import VNTradingEnv

RESULTS_DIR = config.PROJECT_ROOT / "results" / "zero_shot"
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
    p.add_argument(
        "--n-sessions",
        type=int,
        default=None,
        help="Limit to first N sessions (smoke test); default = full split",
    )
    args = p.parse_args()

    md = load_market_data(args.split)
    news = pd.read_parquet(NEWS_PATH) if NEWS_PATH.exists() else pd.DataFrame()
    print(
        f"split={args.split}  sessions={len(md.dates)}  "
        f"news_rows={len(news)}  model={args.model}"
    )

    metrics.reset()
    env = VNTradingEnv(md)
    agent = ZeroShotTrader(market_data=md, news_data=news, model=args.model)
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
    print(f"prompt tokens:   {snap['total_prompt_tokens']:,} "
          f"(cached {snap['total_cached_tokens']:,})")
    print(f"completion:      {snap['total_completion_tokens']:,}")
    print(f"est cost:        ${snap['estimated_cost_usd']:.4f}")
    print(f"parse success:   {snap['parse_success']}")
    print(f"parse failure:   {snap['parse_failure']} "
          f"({snap['parse_failure_rate']:.1%})")
    if snap["parse_failure_reasons"]:
        print(f"failure reasons: {snap['parse_failure_reasons']}")
    return 0


def _run_full(env: VNTradingEnv, agent: ZeroShotTrader, seed: int) -> BacktestResult:
    from src.baselines import run_backtest

    return run_backtest(env, agent, seed=seed)


def _run_n(
    env: VNTradingEnv, agent: ZeroShotTrader, seed: int, n: int
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
