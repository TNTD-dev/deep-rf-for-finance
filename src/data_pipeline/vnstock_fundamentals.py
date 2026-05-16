"""Fetch quarterly fundamentals from vnstock Finance API; file-cache 7-day TTL.

Moved here from PKG-1 scope after the Spike 2 finding that vnstock community
caps Finance to 4 most-recent quarters. Lookahead enforcement happens at the
``LookaheadSafeTools.get_fundamentals`` layer (filters quarters with
``report_date < asof - lag``); this module just fetches + caches the raw
4-quarter snapshot.

Cached layout: ``data/raw/fundamentals_cache/{ticker}.parquet``, long format
unified across income/balance/cashflow/ratio statements.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import pandas as pd
from vnstock.api.financial import Finance

from src import config

log = logging.getLogger(__name__)

CACHE_DIR: Path = config.PROJECT_ROOT / "data" / "raw" / "fundamentals_cache"
CACHE_TTL_DAYS: int = 7
STATEMENTS: tuple[str, ...] = (
    "income_statement",
    "balance_sheet",
    "cash_flow",
    "ratio",
)
_UNIFIED_SCHEMA: list[str] = [
    "ticker",
    "statement",
    "period",
    "item",
    "item_en",
    "item_id",
    "value",
]


def fetch_fundamentals(ticker: str, refresh: bool = False) -> pd.DataFrame:
    """Returns long-format DataFrame conforming to ``_UNIFIED_SCHEMA``.

    ~26 income + 86 balance + N cash_flow + N ratio rows × 4 quarters per
    ticker (≈ several hundred rows total).
    """
    cache_path = CACHE_DIR / f"{ticker}.parquet"
    if not refresh and _cache_fresh(cache_path):
        return pd.read_parquet(cache_path)
    df = _fetch_live(ticker)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache_path, engine="pyarrow", compression="snappy")
    return df


def _cache_fresh(path: Path) -> bool:
    if not path.exists():
        return False
    age_days = (time.time() - path.stat().st_mtime) / 86400
    return age_days < CACHE_TTL_DAYS


def _fetch_live(ticker: str) -> pd.DataFrame:
    fin = Finance(source="vci", symbol=ticker, period="quarter", get_all=True)
    chunks: list[pd.DataFrame] = []
    for stmt in STATEMENTS:
        method = getattr(fin, stmt, None)
        if method is None:
            continue
        try:
            raw = method()
        except Exception as e:  # noqa: BLE001 — vnstock raises diverse types
            log.warning("Finance.%s for %s failed: %s", stmt, ticker, e)
            continue
        if raw is None or raw.empty:
            log.warning("Finance.%s for %s returned empty", stmt, ticker)
            continue
        chunks.append(_melt(raw, ticker, stmt))
    if not chunks:
        raise RuntimeError(f"all 4 statements failed for {ticker}")
    return pd.concat(chunks, ignore_index=True)[list(_UNIFIED_SCHEMA)]


def _melt(raw: pd.DataFrame, ticker: str, statement: str) -> pd.DataFrame:
    """vnstock returns wide ``[item, item_en, item_id, Q1, Q2, Q3, Q4]``;
    melt to long ``[ticker, statement, period, item, item_en, item_id, value]``.
    """
    meta_cols = [c for c in ("item", "item_en", "item_id") if c in raw.columns]
    period_cols = [c for c in raw.columns if "-Q" in str(c)]
    if not period_cols:
        raise ValueError(
            f"no period columns in {statement} for {ticker}: "
            f"{raw.columns.tolist()[:10]}"
        )
    melted = raw.melt(
        id_vars=meta_cols,
        value_vars=period_cols,
        var_name="period",
        value_name="value",
    )
    melted["ticker"] = ticker
    melted["statement"] = statement
    for c in ("item", "item_en", "item_id"):
        if c not in melted.columns:
            melted[c] = pd.NA
    return melted
