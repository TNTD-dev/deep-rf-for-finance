"""Load PKG-1 prices.parquet → wide-format ndarrays for fast env stepping.

Long→wide pivot per ticker with column order locked to `config.TICKERS`.
Indicators are z-score normalized rolling 60-day per (ticker, feature) so the
DDPG network sees stable scale across the full date range. `warmup_offset` is
the first row where all indicators are non-NaN (≈ session 50 after SMA50
warm-up).

Splits (train/val/test) follow PRD §15 locked boundaries from `config.py`.
Z-score window is computed on the full series BEFORE slicing so the rolling
window doesn't cliff at split boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from src import config
from src.data_pipeline.indicators import INDICATOR_COLS

PRICES_PATH = config.PROJECT_ROOT / "data" / "processed" / "prices.parquet"
ZSCORE_WINDOW: int = 60


@dataclass(frozen=True)
class MarketData:
    """Immutable container of wide-format market arrays for one split."""

    dates: pd.DatetimeIndex            # shape (T,)
    tickers: tuple[str, ...]           # shape (n_tickers,)
    close: np.ndarray                  # shape (T, n_tickers), float32
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    indicators_norm: np.ndarray        # shape (T, n_tickers, n_indicators), z-scored
    warmup_offset: int                 # first valid session idx (post warm-up)


def load_market_data(
    split: Literal["train", "val", "test", "full"] = "full",
) -> MarketData:
    """Load + pivot + normalize + split.

    Args:
        split: which date range to return.
            train: TRAIN_START → VAL_START (exclusive)
            val:   VAL_START → TEST_START (exclusive)
            test:  TEST_START → TEST_END (inclusive)
            full:  TRAIN_START → TEST_END (inclusive)

    Returns:
        MarketData with arrays in `config.TICKERS` column order.
    """
    df = pd.read_parquet(PRICES_PATH)
    df = df.sort_values(["ticker", "date"]).reset_index(drop=True)
    tickers = tuple(config.TICKERS)
    seen = set(df["ticker"].unique())
    if seen != set(tickers):
        raise ValueError(
            f"Ticker mismatch — parquet has {sorted(seen)}, config has {list(tickers)}"
        )

    dates_full = pd.DatetimeIndex(df["date"].drop_duplicates().sort_values())
    close = _pivot(df, "close", tickers)
    open_ = _pivot(df, "open", tickers)
    high = _pivot(df, "high", tickers)
    low = _pivot(df, "low", tickers)

    ind_cols = list(INDICATOR_COLS)
    indicators = np.stack(
        [_pivot(df, c, tickers) for c in ind_cols], axis=-1
    )  # (T, n_tickers, n_indicators)

    # Z-score BEFORE split so the rolling window covers across split boundary
    ind_norm = _rolling_zscore(indicators, ZSCORE_WINDOW)

    start, end = _split_bounds(split)
    mask = (dates_full >= pd.to_datetime(start)) & (dates_full <= pd.to_datetime(end))
    sub_dates = dates_full[mask]
    sub_idx = np.where(mask)[0]
    sub_close = close[sub_idx]
    sub_open = open_[sub_idx]
    sub_high = high[sub_idx]
    sub_low = low[sub_idx]
    sub_ind = ind_norm[sub_idx]

    valid = ~np.isnan(sub_ind).any(axis=(1, 2))
    warmup_offset = int(np.argmax(valid)) if valid.any() else len(sub_dates)
    return MarketData(
        dates=sub_dates,
        tickers=tickers,
        close=sub_close,
        open=sub_open,
        high=sub_high,
        low=sub_low,
        indicators_norm=sub_ind,
        warmup_offset=warmup_offset,
    )


def _split_bounds(split: str) -> tuple[str, str]:
    if split == "train":
        return config.TRAIN_START, config.VAL_START
    if split == "val":
        return config.VAL_START, config.TEST_START
    if split == "test":
        return config.TEST_START, config.TEST_END
    if split == "full":
        return config.TRAIN_START, config.TEST_END
    raise ValueError(f"unknown split: {split}")


def _pivot(df: pd.DataFrame, col: str, tickers: tuple[str, ...]) -> np.ndarray:
    """Pivot long → wide preserving `tickers` column order, not alphabetical."""
    w = df.pivot(index="date", columns="ticker", values=col)
    return w[list(tickers)].to_numpy(dtype=np.float32)


def _rolling_zscore(x: np.ndarray, window: int) -> np.ndarray:
    """Z-score along axis 0 with rolling window. Leading positions stay NaN
    until enough samples accumulate (min_samples = window // 2).

    Suppresses NaN-slice runtime warnings; we explicitly check NaN-fullness
    before scoring and leave such positions as NaN — that's the intended state
    during the SMA50 warm-up.
    """
    out = np.full_like(x, np.nan, dtype=np.float32)
    min_samples = max(window // 2, 20)
    with np.errstate(invalid="ignore"):
        import warnings as _w

        with _w.catch_warnings():
            _w.simplefilter("ignore", RuntimeWarning)
            for i in range(x.shape[0]):
                lo = max(0, i - window + 1)
                chunk = x[lo : i + 1]
                if chunk.shape[0] < min_samples:
                    continue
                non_nan_count = (~np.isnan(chunk)).sum(axis=0)
                if (non_nan_count < min_samples).any():
                    continue  # not enough samples for at least one feature
                mu = np.nanmean(chunk, axis=0)
                sd = np.nanstd(chunk, axis=0)
                sd = np.where(sd < 1e-8, 1.0, sd)
                out[i] = (x[i] - mu) / sd
    return out
