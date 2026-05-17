"""Live-mode input loader (PKG-12).

Offline-first: reuses ``load_market_data("full")`` so the graph sees
arrays through the latest cached session. News from offline parquet.
``info`` dict is synthesized — flat starting portfolio (holdings=0,
cash=INITIAL_CAPITAL) so live mode is reproducible.

Real-time vnstock overlay (``use_realtime=True``) is a documented hook
but ships as a no-op in MVP — fetch-at-request-time adds 5-10s per
ticker and risks vnstock rate-limit cascading into a 500 mid-stream.
Defer until daily-cron data refresh exists.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from src import config
from src.env_data_loader import MarketData, load_market_data

log = logging.getLogger(__name__)

NEWS_PATH = config.PROJECT_ROOT / "data" / "processed" / "news.parquet"


def load_live_inputs(
    tickers: list[str] | None = None,
    use_realtime: bool = False,
) -> tuple[MarketData, pd.DataFrame, dict]:
    """Build inputs for one live multi-agent run.

    Args:
      tickers: optional override; currently informational only (MarketData
        always loads the configured TICKERS — overriding requires re-pivoting
        the parquet, deferred until a future ticker-universe feature).
      use_realtime: best-effort flag; MVP logs + ignores.

    Returns:
      md: MarketData through the latest available offline session.
      news: news DataFrame (may be empty if NEWS_PATH missing).
      info: env-info-like dict (date, t, holdings=zeros, cash, pv, close_t).
    """
    md = load_market_data("full")
    news = pd.read_parquet(NEWS_PATH) if NEWS_PATH.exists() else pd.DataFrame()
    n = len(md.tickers)
    info = {
        "date": md.dates[-1],
        "t": int(len(md.dates) - 1),
        "holdings": np.zeros(n, dtype=np.int64),
        "cash": float(config.INITIAL_CAPITAL),
        "portfolio_value": float(config.INITIAL_CAPITAL),
        "close_t": md.close[-1].astype(np.float64),
    }
    if tickers is not None and list(tickers) != list(md.tickers):
        log.warning(
            "ticker override %s requested but MarketData is locked to %s — using config tickers",
            tickers,
            list(md.tickers),
        )
    if use_realtime:
        log.info("use_realtime=True requested — MVP ships offline-only; ignored")
    return md, news, info
