"""Coverage report for CHECKPOINT 16/05 GO/NO-GO.

Prints per-ticker and overall coverage of trading sessions in the test period
that have at least one usable news item (counted via available_for_session).

Exit code: 0 if overall coverage ≥ GATE_THRESHOLD (GO), 1 otherwise (NO-GO →
fallback per TASKS.md PKG-2 §CHECKPOINT).
"""

from __future__ import annotations

import sys

import pandas as pd

from src import config

NEWS = config.PROJECT_ROOT / "data" / "processed" / "news.parquet"
PRICES = config.PROJECT_ROOT / "data" / "processed" / "prices.parquet"
GATE_THRESHOLD: float = 0.50


def main() -> int:
    if not NEWS.exists():
        print(f"ERROR: {NEWS} not found — run scripts/fetch_news.py first.")
        return 2
    news = pd.read_parquet(NEWS)
    prices = pd.read_parquet(PRICES)

    test_start = pd.to_datetime(config.TEST_START)
    test_end = pd.to_datetime(config.TEST_END)
    sessions = (
        prices[(prices["date"] >= test_start) & (prices["date"] <= test_end)]["date"]
        .drop_duplicates()
        .sort_values()
        .reset_index(drop=True)
    )
    print(
        f"Test sessions: {len(sessions)} "
        f"({sessions.iloc[0].date()} → {sessions.iloc[-1].date()})"
    )

    # Explode tickers list → one row per (news, ticker)
    exploded = news.explode("tickers").rename(columns={"tickers": "ticker"})
    exploded["session"] = pd.to_datetime(exploded["available_for_session"])
    exploded = exploded[exploded["session"].between(test_start, test_end)]

    rows: list[dict] = []
    for t in config.TICKERS:
        covered = exploded[exploded["ticker"] == t]["session"].nunique()
        pct = covered / len(sessions) if len(sessions) else 0.0
        rows.append(
            {"ticker": t, "sessions_with_news": covered, "pct": f"{pct:.1%}"}
        )
    tbl = pd.DataFrame(rows)
    print("\n=== PER-TICKER COVERAGE ===")
    print(tbl.to_string(index=False))

    total_cells = len(sessions) * len(config.TICKERS)
    filled = sum(r["sessions_with_news"] for r in rows)
    overall = filled / total_cells if total_cells else 0.0
    print(f"\nOverall coverage: {filled}/{total_cells} = {overall:.1%}")
    print(f"Gate threshold:   {GATE_THRESHOLD:.0%}")

    src = news["source"].value_counts()
    print(f"\nSource split:\n{src.to_string()}")

    if overall < GATE_THRESHOLD:
        print("\n❌ NO-GO — coverage below threshold. Trigger fallback (TASKS.md PKG-2).")
        return 1
    print("\n✅ GO — coverage meets threshold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
