"""Lookahead-safe windowing — single most important invariant in the project.

CLAUDE.md §"No lookahead bias — ever" routes ALL data slicing through this
module. If these tests pass loosely, every downstream backtest is suspect.
"""

from __future__ import annotations

import pandas as pd

from src.data_pipeline.calendar import build_trading_calendar, window_until


def test_window_until_is_strict_less_than() -> None:
    """At open of session T, only sessions with date < T are observable.

    Strict `<` (NOT `<=`) — current session's own data is not yet known to a
    decision-maker acting at session open. Flipping this is the most common
    way to introduce subtle lookahead bias.
    """
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(
                ["2024-06-13", "2024-06-14", "2024-06-15", "2024-06-17"]
            ),
            "x": [1, 2, 3, 4],
        }
    )
    out = window_until(df, "2024-06-15")
    assert out["x"].tolist() == [1, 2]  # NOT [1, 2, 3]


def test_window_until_empty_when_asof_is_before_all() -> None:
    """Empty result is correct when no historical data exists yet."""
    df = pd.DataFrame({"date": pd.to_datetime(["2024-06-15"]), "x": [1]})
    assert window_until(df, "2024-06-01").empty


def test_window_until_returns_copy_not_view() -> None:
    """Caller mutations on the slice must not propagate to the source df.

    Important because trading env may mutate state copies during stepping.
    """
    df = pd.DataFrame({"date": pd.to_datetime(["2024-06-13"]), "x": [1]})
    out = window_until(df, "2024-06-15")
    out.loc[0, "x"] = 999
    assert df.loc[0, "x"] == 1


def test_build_trading_calendar_dedups_across_tickers() -> None:
    """Calendar is the union of dates across tickers, not duplicates per row."""
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-06-13", "2024-06-13", "2024-06-14"]),
            "ticker": ["VCB", "FPT", "VCB"],
        }
    )
    cal = build_trading_calendar(df)
    assert len(cal) == 2
    assert cal.is_monotonic_increasing
