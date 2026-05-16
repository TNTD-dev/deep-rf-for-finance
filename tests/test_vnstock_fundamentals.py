"""vnstock_fundamentals invariants — schema, melt math, cache freshness."""

from __future__ import annotations

import time

import pandas as pd
import pytest

from src.data_pipeline import vnstock_fundamentals as vf


def _fake_finance(income_rows: int = 3) -> object:
    """Stand-in for vnstock.api.financial.Finance with controllable shape."""

    class _Fake:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def income_statement(self) -> pd.DataFrame:
            return pd.DataFrame(
                {
                    "item": [f"item_{i}" for i in range(income_rows)],
                    "item_en": [f"item_en_{i}" for i in range(income_rows)],
                    "item_id": list(range(income_rows)),
                    "2025-Q1": [100.0 + i for i in range(income_rows)],
                    "2025-Q2": [110.0 + i for i in range(income_rows)],
                    "2025-Q3": [120.0 + i for i in range(income_rows)],
                    "2025-Q4": [130.0 + i for i in range(income_rows)],
                }
            )

        def balance_sheet(self) -> pd.DataFrame:
            return pd.DataFrame(
                {"item": ["assets"], "item_en": ["Assets"], "item_id": [1],
                 "2025-Q1": [1.0e12], "2025-Q2": [1.1e12],
                 "2025-Q3": [1.2e12], "2025-Q4": [1.3e12]}
            )

        def cash_flow(self) -> pd.DataFrame:
            raise RuntimeError("simulated cash_flow outage")

        def ratio(self) -> pd.DataFrame:
            return pd.DataFrame(
                {"item": ["roe"], "item_en": ["ROE"], "item_id": [1],
                 "2025-Q1": [0.10], "2025-Q2": [0.11],
                 "2025-Q3": [0.12], "2025-Q4": [0.13]}
            )

    return _Fake


def test_unified_schema(monkeypatch, tmp_path) -> None:
    """Output columns must exactly match _UNIFIED_SCHEMA so PKG-5 tools layer
    can rely on a stable contract."""
    monkeypatch.setattr(vf, "Finance", _fake_finance())
    monkeypatch.setattr(vf, "CACHE_DIR", tmp_path)
    df = vf.fetch_fundamentals("VCB", refresh=True)
    assert df.columns.tolist() == vf._UNIFIED_SCHEMA


def test_melt_handles_4_quarter_columns(monkeypatch, tmp_path) -> None:
    """Wide → long: 3 income rows × 4 quarters = 12 income melted rows
    + 1 balance × 4 = 4 + 1 ratio × 4 = 4 = 20 total (cash_flow fails)."""
    monkeypatch.setattr(vf, "Finance", _fake_finance(income_rows=3))
    monkeypatch.setattr(vf, "CACHE_DIR", tmp_path)
    df = vf.fetch_fundamentals("VCB", refresh=True)
    assert len(df) == 20
    assert sorted(df["statement"].unique()) == ["balance_sheet", "income_statement", "ratio"]
    assert sorted(df["period"].unique()) == ["2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4"]


def test_cache_hit_skips_live_fetch(monkeypatch, tmp_path) -> None:
    """Second call within TTL must read parquet, never instantiate Finance.
    If broken, demo runs blow through vnstock rate limits."""
    monkeypatch.setattr(vf, "Finance", _fake_finance())
    monkeypatch.setattr(vf, "CACHE_DIR", tmp_path)
    df1 = vf.fetch_fundamentals("VCB", refresh=True)
    # Replace Finance with a stub that fails — proves cache hit
    monkeypatch.setattr(
        vf, "Finance", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("must not call"))
    )
    df2 = vf.fetch_fundamentals("VCB", refresh=False)
    pd.testing.assert_frame_equal(df1.reset_index(drop=True), df2.reset_index(drop=True))


def test_refresh_forces_live_fetch(monkeypatch, tmp_path) -> None:
    """refresh=True bypasses cache. Required when fundamentals release lands
    mid-week and we want to re-fetch before staleness expires."""
    monkeypatch.setattr(vf, "Finance", _fake_finance())
    monkeypatch.setattr(vf, "CACHE_DIR", tmp_path)
    vf.fetch_fundamentals("VCB", refresh=True)
    cache_path = tmp_path / "VCB.parquet"
    mtime_first = cache_path.stat().st_mtime
    time.sleep(0.05)
    vf.fetch_fundamentals("VCB", refresh=True)
    assert cache_path.stat().st_mtime > mtime_first


def test_melt_raises_when_no_period_columns(monkeypatch) -> None:
    """If vnstock changes schema and period columns disappear, fail loud
    instead of silently returning empty."""
    bad = pd.DataFrame({"item": ["x"], "item_en": ["X"], "item_id": [1], "garbage": [None]})
    with pytest.raises(ValueError, match="no period columns"):
        vf._melt(bad, "VCB", "income_statement")
