"""CLI: train PPO on train split, eval on val. Saves best model + JSONL log.

PPO is the DDPG backup (PRD §14 Risk #7). Run independently of train_ddpg.py.

Usage:
    .venv/bin/python scripts/train_ppo.py                            # full train
    .venv/bin/python scripts/train_ppo.py --total-timesteps 10000    # smoke
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from src import config
from src.env_data_loader import load_market_data
from src.rl_training.ppo_trainer import load_ppo_config, train_ppo
from src.trading_env import VNTradingEnv

CFG_PATH = config.PROJECT_ROOT / "configs" / "ppo.yaml"
MODEL_PATH = config.PROJECT_ROOT / "results" / "models" / "ppo_best.zip"
LOG_PATH = config.PROJECT_ROOT / "results" / "ppo_training_log.jsonl"


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    p = argparse.ArgumentParser()
    p.add_argument("--config", default=str(CFG_PATH))
    p.add_argument(
        "--total-timesteps",
        type=int,
        default=None,
        help="Override config total_timesteps (smoke runs)",
    )
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    cfg = load_ppo_config(Path(args.config))
    if args.total_timesteps is not None:
        cfg["total_timesteps"] = int(args.total_timesteps)

    train_md = load_market_data("train")
    val_md = load_market_data("val")
    train_env = VNTradingEnv(train_md)
    val_env = VNTradingEnv(val_md)
    print(
        f"train sessions: {len(train_md.dates)}, "
        f"val sessions: {len(val_md.dates)}, "
        f"timesteps: {cfg['total_timesteps']}"
    )

    result = train_ppo(
        cfg=cfg,
        train_env=train_env,
        val_env=val_env,
        save_path=MODEL_PATH,
        log_path=LOG_PATH,
        seed=args.seed,
    )
    print("\n=== Training summary ===")
    print(f"aborted:       {result['aborted']}")
    print(f"reason:        {result.get('aborted_reason')}")
    print(f"best_sharpe:   {result['best_sharpe']:.4f}")
    print(f"final_step:    {result['final_step']}")
    print(f"eval_count:    {result['eval_count']}")
    print(f"model saved:   {MODEL_PATH}")
    print(f"log:           {LOG_PATH}")
    if result["aborted"]:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
