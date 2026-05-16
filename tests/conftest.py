"""Shared pytest fixtures.

Centralizing the synthetic MarketData builder avoids duplicating the 60-session
fixture across multiple test files. Existing `tests/test_trading_env.py`
defines its own copy — left in place for atomic PR boundaries; future
cleanup can drop the duplicate when a follow-up package touches that file.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src import config
from src.env_data_loader import MarketData


@pytest.fixture
def synthetic_market_data() -> MarketData:
    """60-session × 5-ticker fixture with a deterministic 0.1%/day uptrend.

    Indicators are random z-scored. Use anywhere an env needs to step
    without depending on PKG-1 parquet output.
    """
    return _build(n_sessions=60)


def _build(n_sessions: int = 60) -> MarketData:
    rng = np.random.default_rng(seed=0)
    base = np.array([50.0, 60.0, 70.0, 80.0, 90.0], dtype=np.float32)
    n_tickers = len(base)
    close = np.zeros((n_sessions, n_tickers), dtype=np.float32)
    close[0] = base
    for t in range(1, n_sessions):
        close[t] = close[t - 1] * 1.001
    high = close * 1.01
    low = close * 0.99
    open_ = close * (
        1.0 + rng.normal(0, 0.001, close.shape).astype(np.float32)
    )
    ind = rng.normal(0, 1, (n_sessions, n_tickers, 9)).astype(np.float32)
    dates = pd.date_range("2025-01-02", periods=n_sessions, freq="B")
    return MarketData(
        dates=pd.DatetimeIndex(dates),
        tickers=tuple(config.TICKERS),
        close=close,
        open=open_,
        high=high,
        low=low,
        indicators_norm=ind,
        warmup_offset=0,
    )
