"""CLI: fetch news (vnstock + CafeF sitemap), merge, dedup, write parquet.

Output: `data/processed/news.parquet` conforming to NEWS_SCHEMA. The
`available_for_session` column is computed against the trading calendar
derived from PKG-1's prices.parquet, so PKG-1 must be merged first.

Usage:
    .venv/bin/python scripts/fetch_news.py                    # full range
    .venv/bin/python scripts/fetch_news.py --skip-cafef       # vnstock only, fast iteration
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date

import pandas as pd

from src import config
from src.data_pipeline.calendar import build_trading_calendar
from src.data_pipeline.news_align import (
    NEWS_SCHEMA,
    compute_available_for_session,
)
from src.data_pipeline.news_fetch import fetch_vnstock_news
from src.data_pipeline.news_scraper import scrape_cafef_sitemap_range

NEWS_OUT = config.PROJECT_ROOT / "data" / "processed" / "news.parquet"
PRICES_IN = config.PROJECT_ROOT / "data" / "processed" / "prices.parquet"


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument(
        "--start", default=config.TEST_START, help="news start date YYYY-MM-DD"
    )
    p.add_argument(
        "--end", default=date.today().isoformat(), help="news end date YYYY-MM-DD"
    )
    p.add_argument(
        "--skip-cafef",
        action="store_true",
        help="skip CafeF sitemap scrape (vnstock only, for fast iteration)",
    )
    args = p.parse_args()

    if not PRICES_IN.exists():
        print(f"ERROR: {PRICES_IN} not found — run PKG-1 fetch_data.py first.")
        return 2

    prices = pd.read_parquet(PRICES_IN)
    calendar = build_trading_calendar(prices)
    print(f"Trading calendar: {len(calendar)} sessions ({calendar[0].date()} → {calendar[-1].date()})")

    chunks: list[pd.DataFrame] = []
    for t in config.TICKERS:
        try:
            df = fetch_vnstock_news(t)
            chunks.append(df)
            print(f"vnstock {t}: {len(df)} rows")
        except Exception as e:  # noqa: BLE001
            print(f"vnstock {t}: FAILED — {e}")

    if not args.skip_cafef:
        s = date.fromisoformat(args.start)
        e = date.fromisoformat(args.end)
        df = scrape_cafef_sitemap_range(s, e)
        chunks.append(df)
        print(f"cafef sitemap: {len(df)} rows ({s} → {e})")

    if not chunks:
        print("ERROR: no news fetched from any source.")
        return 1
    news = pd.concat(chunks, ignore_index=True)

    # Dedup ONLY rows with populated URLs. Pandas treats NaN as equal in
    # drop_duplicates, which would collapse all NaN-URL vnstock regulatory
    # disclosures (no source link) into a single row — losing 49 distinct
    # news items per ticker.
    if "url" in news.columns:
        before = len(news)
        with_url = news[news["url"].notna()].drop_duplicates(
            subset=["url"], keep="first"
        )
        without_url = news[news["url"].isna()]
        news = (
            pd.concat([with_url, without_url], ignore_index=True)
            .sort_values("published_at_utc")
            .reset_index(drop=True)
        )
        dropped = before - len(news)
        if dropped:
            print(f"deduplicated {dropped} rows by URL (NaN-URL rows preserved)")

    news["available_for_session"] = compute_available_for_session(
        news["published_at_utc"], calendar
    )
    news = news[NEWS_SCHEMA].sort_values("published_at_utc").reset_index(drop=True)

    NEWS_OUT.parent.mkdir(parents=True, exist_ok=True)
    news.to_parquet(NEWS_OUT, engine="pyarrow", compression="snappy")
    usable = news["available_for_session"].notna().sum()
    print(
        f"\nWritten {NEWS_OUT} ({len(news)} rows, {usable} with usable "
        f"available_for_session)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
