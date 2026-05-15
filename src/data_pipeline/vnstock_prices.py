"""Fetch OHLCV daily from vnstock v4 with KBS → VCI fallback.

vnstock deprecated `Vnstock().stock(...)` on 2025-08-31. We use the new
`vnstock.api.quote.Quote` class directly.

vnstock returns columns `[time, open, high, low, close, volume]` where `time`
is a datetime with 07:00:00 time-of-day. We normalize to `date` (date-only),
add `ticker`, and validate the close column is NaN-free before returning.
"""

from __future__ import annotations

import logging

import pandas as pd
from vnstock.api.quote import Quote

log = logging.getLogger(__name__)

_SCHEMA: list[str] = ["date", "ticker", "open", "high", "low", "close", "volume"]


def fetch_prices(
    ticker: str,
    start: str,
    end: str,
    sources: tuple[str, ...] = ("kbs", "vci"),
) -> pd.DataFrame:
    """Fetch daily OHLCV for one ticker. Returns long-format DataFrame.

    Tries each source in order. Raises `RuntimeError` only if ALL sources fail —
    a silent SPOF on KBS would be invisible to downstream.

    Args:
        ticker: VN30 ticker symbol, e.g. "VCB".
        start: Start date "YYYY-MM-DD" inclusive.
        end: End date "YYYY-MM-DD" inclusive.
        sources: Ordered fallback chain. KBS primary per PRD §8.

    Returns:
        DataFrame with columns _SCHEMA, sorted by date ascending.
    """
    last_err: Exception | None = None
    for src in sources:
        try:
            raw = Quote(symbol=ticker, source=src).history(
                start=start, end=end, interval="1D"
            )
            if raw is None or raw.empty:
                raise ValueError(f"empty response from {src}")
            return _normalize(raw, ticker)
        except Exception as e:  # noqa: BLE001 — intentional broad catch for fallback
            log.warning("fetch_prices %s via %s failed: %s", ticker, src, e)
            last_err = e
    raise RuntimeError(f"all sources failed for {ticker}: {last_err}")


def _normalize(raw: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Map vnstock columns to canonical _SCHEMA.

    vnstock returns: `[time, open, high, low, close, volume]`. `time` is
    datetime64[ns] with hour-of-day; we strip to date-only via `.normalize()`.
    """
    df = raw.rename(columns={"time": "date"}).copy()
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    df["ticker"] = ticker
    missing = set(_SCHEMA) - set(df.columns)
    if missing:
        raise ValueError(
            f"vnstock schema missing {missing} for {ticker}: cols={df.columns.tolist()}"
        )
    df = df[_SCHEMA].sort_values("date").reset_index(drop=True)
    if df["close"].isna().any():
        raise ValueError(f"NaN in close for {ticker}")
    return df
