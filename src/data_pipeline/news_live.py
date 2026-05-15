"""Live news source for SSE streaming (PKG-12).

Reads CafeF's `latest-news-sitemap.xml` (updated continuously) and filters to
the last N hours. Reuses parse + tag helpers from `news_scraper` — DRY.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pandas as pd

from src.data_pipeline.news_align import to_utc
from src.data_pipeline.news_scraper import (
    USER_AGENT,
    parse_chunk,
    tag_tickers,
)

LATEST_URL: str = "https://cafef.vn/latest-news-sitemap.xml"


def fetch_live_news(hours: int = 24) -> pd.DataFrame:
    """Fetch latest CafeF news and filter to last `hours` window.

    Returns DataFrame conforming to NEWS_SCHEMA minus `available_for_session`
    (live mode caller computes it against the live calendar).
    """
    with httpx.Client(headers={"User-Agent": USER_AGENT}) as client:
        r = client.get(LATEST_URL, timeout=15.0)
        r.raise_for_status()

    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    rows: list[dict] = []
    for entry in parse_chunk(r.text):
        tickers = tag_tickers(entry["title"])
        if not tickers:
            continue
        rows.append(
            {
                "published_at_utc": entry["lastmod"],
                "source": "cafef_live",
                "url": entry["url"],
                "title": entry["title"],
                "summary": None,
                "tickers": tickers,
            }
        )

    if not rows:
        return pd.DataFrame(
            columns=["published_at_utc", "source", "url", "title", "summary", "tickers"]
        )
    df = pd.DataFrame(rows)
    df["published_at_utc"] = to_utc(df["published_at_utc"])
    df = df[df["published_at_utc"] >= cutoff]
    return df.sort_values("published_at_utc").reset_index(drop=True)
