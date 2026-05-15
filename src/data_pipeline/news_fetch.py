"""Fetch ticker-tagged news from vnstock Company API (primary source).

vnstock community version caps `Company.news()` at 50 items per ticker. Range
probed 2026-05-15: VCB ~8mo, FPT ~10mo, HPG ~10mo, VIC ~7mo, VNM ~7mo. Source
`vci` works reliably; `kbs` returns 1 row only (broken).

Output rows lack `available_for_session` — that column is added by the
orchestrator (`scripts/fetch_news.py`) after a trading calendar is available
from the prices parquet.
"""

from __future__ import annotations

import logging

import pandas as pd
from vnstock.api.company import Company

from src.data_pipeline.news_align import to_utc

log = logging.getLogger(__name__)

_RAW_REQUIRED: set[str] = {"public_date", "news_title", "news_short_content"}
_VNSTOCK_OUT_SCHEMA: list[str] = [
    "published_at_utc",
    "source",
    "url",
    "title",
    "summary",
    "tickers",
]


def fetch_vnstock_news(ticker: str, source: str = "vci") -> pd.DataFrame:
    """Fetch up to 50 most recent news items for `ticker` via vnstock.

    Args:
        ticker: VN30 symbol, e.g. "VCB".
        source: vnstock source — only "vci" works for news (kbs is broken).

    Returns:
        DataFrame conforming to _VNSTOCK_OUT_SCHEMA (lacks
        `available_for_session`; orchestrator adds that).
    """
    raw = Company(source=source, symbol=ticker).news()
    if raw is None or raw.empty:
        raise RuntimeError(f"empty Company.news for {ticker}")
    return _normalize(raw, ticker)


def _normalize(raw: pd.DataFrame, ticker: str) -> pd.DataFrame:
    missing = _RAW_REQUIRED - set(raw.columns)
    if missing:
        raise ValueError(
            f"vnstock news schema missing {missing} for {ticker}: "
            f"cols={raw.columns.tolist()[:10]}"
        )
    url_series = raw.get("news_source_link", pd.Series([None] * len(raw)))
    url_series = url_series.where(url_series.astype(bool), None)
    summary_series = raw["news_short_content"].where(
        raw["news_short_content"].astype(bool), None
    )
    df = pd.DataFrame(
        {
            "published_at_utc": to_utc(raw["public_date"]),
            "source": "vnstock",
            "url": url_series,
            "title": raw["news_title"].astype(str),
            "summary": summary_series,
        }
    )
    df["tickers"] = [[ticker]] * len(df)
    return (
        df[_VNSTOCK_OUT_SCHEMA]
        .sort_values("published_at_utc")
        .reset_index(drop=True)
    )
