"""Apply technical indicators per ticker. Uses `ta` library defaults.

All indicators are computed within a single ticker's series — never across
tickers. Cross-ticker leakage via groupby misuse is the most likely bug class
here, hence the explicit per-ticker loop and the test that asserts isolation.

First (window-1) rows per ticker will be NaN — that is the indicator's
warm-up. Do NOT fillna here; let the env decide when to start consuming.
"""

from __future__ import annotations

import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import MACD, SMAIndicator
from ta.volatility import AverageTrueRange, BollingerBands

RSI_WINDOW: int = 14
MACD_SLOW: int = 26
MACD_FAST: int = 12
MACD_SIGNAL: int = 9
SMA_WINDOWS: tuple[int, ...] = (5, 20, 50)
BB_WINDOW: int = 20
BB_DEV: float = 2.0
ATR_WINDOW: int = 14

INDICATOR_COLS: tuple[str, ...] = (
    "rsi14",
    "macd",
    "macd_signal",
    "sma5",
    "sma20",
    "sma50",
    "bb_upper",
    "bb_lower",
    "atr14",
)


def apply_indicators(prices_long: pd.DataFrame) -> pd.DataFrame:
    """Augment long-format prices DataFrame with indicators.

    Args:
        prices_long: schema (date, ticker, open, high, low, close, volume).

    Returns:
        Same rows + INDICATOR_COLS appended. Sorted by (ticker, date).
    """
    out_chunks: list[pd.DataFrame] = []
    for _ticker, group in prices_long.groupby("ticker", sort=False):
        g = group.sort_values("date").reset_index(drop=True).copy()
        c = g["close"]
        g["rsi14"] = RSIIndicator(close=c, window=RSI_WINDOW).rsi()
        macd = MACD(
            close=c,
            window_slow=MACD_SLOW,
            window_fast=MACD_FAST,
            window_sign=MACD_SIGNAL,
        )
        g["macd"] = macd.macd()
        g["macd_signal"] = macd.macd_signal()
        for w in SMA_WINDOWS:
            g[f"sma{w}"] = SMAIndicator(close=c, window=w).sma_indicator()
        bb = BollingerBands(close=c, window=BB_WINDOW, window_dev=BB_DEV)
        g["bb_upper"] = bb.bollinger_hband()
        g["bb_lower"] = bb.bollinger_lband()
        g["atr14"] = AverageTrueRange(
            high=g["high"], low=g["low"], close=c, window=ATR_WINDOW
        ).average_true_range()
        out_chunks.append(g)
    return pd.concat(out_chunks, ignore_index=True)
