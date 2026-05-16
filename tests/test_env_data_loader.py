"""env_data_loader invariants — pivot column order, split bounds, warmup, z-score scale."""

from __future__ import annotations

import numpy as np
import pytest

from src import config
from src.env_data_loader import load_market_data


def test_full_split_covers_train_to_test_end() -> None:
    """Full split spans TRAIN_START → TEST_END (PRD §15 locked range)."""
    m = load_market_data("full")
    assert m.dates[0] >= np.datetime64(config.TRAIN_START)
    assert m.dates[-1] <= np.datetime64(config.TEST_END)


def test_test_split_has_248_sessions() -> None:
    """Test period (2025-05 → 2026-04) yields 248 trading sessions — value
    pinned because every later metric (Sharpe annualization, e.g.) depends on
    this length being stable."""
    m = load_market_data("test")
    assert m.close.shape == (248, 5)
    assert m.indicators_norm.shape == (248, 5, 9)


def test_pivot_preserves_config_ticker_order() -> None:
    """Column index → ticker mapping is contractual. Pivot must NOT sort
    alphabetically. If this breaks, DDPG sees scrambled features mid-training.
    """
    m = load_market_data("test")
    assert m.tickers == tuple(config.TICKERS)
    # config order: VCB, FPT, HPG, VIC, VNM — NOT alphabetical (FPT, HPG, VCB...)
    assert m.tickers[0] == "VCB"
    assert m.tickers[1] == "FPT"


def test_warmup_offset_on_full_split() -> None:
    """Full split warmup combines SMA50 (49 sessions) + z-score min_samples
    (≥30 non-NaN per feature) → first fully-valid row near session 78.

    First valid date should be around late April 2019. If warmup balloons
    beyond 100, something is wrong with the rolling z-score min_samples.
    """
    m = load_market_data("full")
    assert 60 <= m.warmup_offset <= 100
    first_valid = m.dates[m.warmup_offset]
    assert first_valid.year == 2019
    assert first_valid.month in (4, 5)


def test_val_and_test_have_zero_warmup() -> None:
    """Z-score is computed BEFORE split so val/test have warmup_offset=0 —
    indicators were already cooked by the full series rolling window."""
    assert load_market_data("val").warmup_offset == 0
    assert load_market_data("test").warmup_offset == 0


def test_indicators_norm_is_z_score_scale() -> None:
    """After z-score normalization, indicator values should typically lie in
    roughly [-4, 4] for stationary financial series. If we see |z| > 50, the
    rolling window isn't being applied per-feature correctly."""
    m = load_market_data("test")
    vals = m.indicators_norm[~np.isnan(m.indicators_norm)]
    assert vals.size > 0
    # Tolerance loose — fat-tailed financial data, but |z| > 50 means a bug
    assert np.abs(vals).max() < 50.0
    # Mean should be close to 0 (z-score property), but rolling window means
    # not exactly 0 on any single split — within ±1.0 is plenty.
    assert abs(vals.mean()) < 1.0


def test_close_no_nan_after_warmup() -> None:
    """OHLCV prices must NEVER be NaN inside the date range (PKG-1 guarantee)."""
    m = load_market_data("test")
    assert not np.isnan(m.close).any()
    assert not np.isnan(m.open).any()
    assert not np.isnan(m.high).any()
    assert not np.isnan(m.low).any()


def test_unknown_split_raises() -> None:
    """Typos in `split` arg must fail loud, not silently load 'full'."""
    with pytest.raises(ValueError, match="unknown split"):
        load_market_data("trian")  # typo intentional — test rejects unknown
