"""Tests for backend/live_data.py."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from backend import live_data
from src import config


def test_load_live_inputs_returns_full_market_data() -> None:
    md, news, info = live_data.load_live_inputs()
    assert len(md.dates) > 200  # full series is hundreds of sessions
    assert tuple(md.tickers) == tuple(config.TICKERS)
    assert info["date"] == md.dates[-1]
    assert isinstance(news, pd.DataFrame)


def test_load_live_inputs_info_has_zero_holdings_and_full_cash() -> None:
    md, _, info = live_data.load_live_inputs()
    n = len(md.tickers)
    assert info["holdings"].shape == (n,)
    assert info["holdings"].sum() == 0
    assert info["cash"] == float(config.INITIAL_CAPITAL)
    assert info["portfolio_value"] == float(config.INITIAL_CAPITAL)
    assert info["close_t"].shape == (n,)
    assert info["close_t"].dtype == np.float64


def test_load_live_inputs_missing_news_parquet_returns_empty_df(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(live_data, "NEWS_PATH", tmp_path / "does-not-exist.parquet")
    _, news, _ = live_data.load_live_inputs()
    assert isinstance(news, pd.DataFrame)
    assert news.empty
