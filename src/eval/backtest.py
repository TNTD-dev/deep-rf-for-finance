"""Backtest + metrics + payload assembly (PKG-10).

Wraps PKG-4's ``run_backtest`` and adds PKG-10's metric computation +
PRD §10 ``GET /backtest/{agent}`` payload assembly. The payload shape
defined in ``build_payload`` is the single source of truth that PKG-11
serves verbatim from the saved ``metrics.json``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from src import config
from src.agent_base import Agent, BacktestResult
from src.baselines import run_backtest
from src.env_data_loader import MarketData
from src.eval.metrics import compute_all_financial_metrics
from src.trading_env import VNTradingEnv


def run_and_score(
    agent: Agent,
    market_data: MarketData,
    env: VNTradingEnv | None = None,
    seed: int = 42,
) -> tuple[BacktestResult, dict]:
    """Run backtest + compute financial metrics. Returns (result, metrics)."""
    env = env or VNTradingEnv(market_data)
    result = run_backtest(env, agent, seed=seed)
    metrics = compute_all_financial_metrics(
        result.portfolio_curve, result.holdings_curve, market_data
    )
    return result, metrics


def build_payload(
    result: BacktestResult,
    metrics: dict,
    llm_metrics: dict | None = None,
    test_window: tuple[str, str] | None = None,
    seed: int = 42,
) -> dict:
    """Build the PRD §10 GET /backtest/{agent} response payload."""
    full_metrics = dict(metrics)
    if llm_metrics:
        full_metrics.update(llm_metrics)

    pc = result.portfolio_curve.copy()
    pc["date"] = pd.to_datetime(pc["date"]).dt.strftime("%Y-%m-%d")
    portfolio_curve = [
        {"date": r["date"], "value": int(r["portfolio_value"])} for _, r in pc.iterrows()
    ]

    h = result.holdings_curve.copy()
    h["date"] = pd.to_datetime(h["date"]).dt.strftime("%Y-%m-%d")
    holdings = []
    for _, r in h.iterrows():
        item: dict = {"date": r["date"]}
        for t in config.TICKERS:
            item[t] = int(r[f"h_{t}"])
        holdings.append(item)

    return {
        "agent": result.agent_name,
        "portfolio_curve": portfolio_curve,
        "holdings": holdings,
        "metrics": full_metrics,
        "provenance": {
            "ts": datetime.now(UTC).isoformat(),
            "seed": int(seed),
            "test_window": list(test_window) if test_window else None,
            "n_steps": int(result.n_steps),
        },
    }


def save_artifacts(
    payload: dict,
    result: BacktestResult,
    results_root: Path,
) -> Path:
    """Write parquets + metrics.json to results/{agent}/. Returns the dir."""
    agent_dir = results_root / payload["agent"]
    agent_dir.mkdir(parents=True, exist_ok=True)
    result.portfolio_curve.to_parquet(
        agent_dir / "portfolio_curve.parquet",
        engine="pyarrow",
        compression="snappy",
    )
    result.holdings_curve.to_parquet(
        agent_dir / "holdings.parquet",
        engine="pyarrow",
        compression="snappy",
    )
    (agent_dir / "metrics.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return agent_dir


def score_from_cache(
    agent_name: str,
    agent_dir: Path,
    market_data: MarketData,
    seed: int = 42,
    test_window: tuple[str, str] | None = None,
    llm_metrics: dict | None = None,
) -> dict | None:
    """Build PRD §10 payload from cached parquets in ``agent_dir``.

    Used by run_all under --skip-existing when parquets exist (from a prior
    PKG-4/6/7/8/9 run) but metrics.json doesn't yet. Lets the aggregation
    layer surface all agents without re-spending LLM cost. Returns the
    payload dict (also writes ``metrics.json`` into ``agent_dir``) or None
    when required parquets are missing.
    """
    pc_path = agent_dir / "portfolio_curve.parquet"
    h_path = agent_dir / "holdings.parquet"
    if not (pc_path.exists() and h_path.exists()):
        return None
    pc_df = pd.read_parquet(pc_path)
    h_df = pd.read_parquet(h_path)
    metrics = compute_all_financial_metrics(pc_df, h_df, market_data)

    # Synthesize a minimal BacktestResult so build_payload can format dates.
    fake = BacktestResult(
        agent_name=agent_name,
        portfolio_curve=pc_df,
        holdings_curve=h_df,
        total_log_return=0.0,
        final_pv=float(pc_df["portfolio_value"].iloc[-1]),
        n_steps=int(len(pc_df) - 1),
        seed=seed,
    )
    payload = build_payload(
        fake,
        metrics,
        llm_metrics=llm_metrics,
        test_window=test_window,
        seed=seed,
    )
    (agent_dir / "metrics.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return payload
