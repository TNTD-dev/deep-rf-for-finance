"""CLI: fetch all tickers' prices, compute indicators, write parquet.

Run once per session (data refreshes once/day). Re-run is idempotent — output
file is overwritten. Day-1 risk gate exits non-zero if depth fails PRD §15.

Fundamentals were moved from PKG-1 to PKG-5 because vnstock community version
limits the Finance API to 4 most recent quarters.

Usage:
    .venv/bin/python scripts/fetch_data.py
    .venv/bin/python scripts/fetch_data.py --end 2026-04-30
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date

import pandas as pd

from src import config
from src.data_pipeline.indicators import apply_indicators
from src.data_pipeline.vnstock_prices import fetch_prices

PRICES_OUT = config.PROJECT_ROOT / "data" / "processed" / "prices.parquet"
MIN_ROWS_PER_TICKER: int = 1500  # PRD §15 acceptance ≈ 6 years × 250 trading days


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument(
        "--end",
        default=date.today().isoformat(),
        help="end date YYYY-MM-DD (default: today)",
    )
    p.add_argument(
        "--start",
        default=config.TRAIN_START,
        help=f"start date (default: TRAIN_START={config.TRAIN_START})",
    )
    args = p.parse_args()
    return 0 if run_prices(start=args.start, end=args.end) else 1


def run_prices(start: str, end: str) -> bool:
    """Fetch + indicators + day-1 gate. Returns True iff gate passes."""
    chunks: list[pd.DataFrame] = []
    report_rows: list[dict] = []
    for ticker in config.TICKERS:
        df = fetch_prices(ticker, start=start, end=end)
        chunks.append(df)
        report_rows.append(
            {
                "ticker": ticker,
                "earliest": df["date"].min(),
                "latest": df["date"].max(),
                "rows": len(df),
            }
        )

    prices = pd.concat(chunks, ignore_index=True)
    prices = apply_indicators(prices)
    PRICES_OUT.parent.mkdir(parents=True, exist_ok=True)
    prices.to_parquet(PRICES_OUT, engine="pyarrow", compression="snappy")

    report = pd.DataFrame(report_rows)
    print("\n=== PRICES DEPTH REPORT ===")
    print(report.to_string(index=False))
    print(f"\nWritten: {PRICES_OUT} ({len(prices)} rows total)")

    # Day-1 risk gate (PRD §14 Risk #8, TASKS PKG-1 acceptance).
    # Allow a 7-day grace window — TRAIN_START may fall on a weekend/holiday
    # (e.g. 2019-01-01 New Year), and the first actual trading day shifts.
    train_start_threshold = pd.to_datetime(config.TRAIN_START) + pd.Timedelta(days=7)
    late = report[pd.to_datetime(report["earliest"]) > train_start_threshold]
    shallow = report[report["rows"] < MIN_ROWS_PER_TICKER]

    if not late.empty:
        print(
            f"\n⚠️  WARNING: {len(late)} ticker(s) start more than 7 days after "
            f"TRAIN_START={config.TRAIN_START}:"
        )
        print(late.to_string(index=False))
        print("→ Consider shortening TRAIN_START. Update PRD §15 if changed.")

    if not shallow.empty:
        print(
            f"\n⚠️  WARNING: {len(shallow)} ticker(s) below "
            f"{MIN_ROWS_PER_TICKER} rows:"
        )
        print(shallow.to_string(index=False))

    return late.empty and shallow.empty


if __name__ == "__main__":
    sys.exit(main())
