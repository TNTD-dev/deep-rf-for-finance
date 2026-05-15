"""VN trading calendar derived from observed price data + lookahead-safe slicing.

No external calendar package — VN-specific holidays aren't reliably available in
`exchange_calendars`. We derive the calendar from the actual union of trading
dates across our universe, which is the empirical ground truth.

The `window_until` helper is the SINGLE source of truth for lookahead-safe
slicing. Every consumer (trading env, backtest, LLM tools) routes through it.
"""

from __future__ import annotations

import pandas as pd


def build_trading_calendar(prices_long: pd.DataFrame) -> pd.DatetimeIndex:
    """Union of all dates that appear for any ticker. Sorted ascending, unique."""
    dates = pd.to_datetime(prices_long["date"]).drop_duplicates().sort_values()
    return pd.DatetimeIndex(dates)


def window_until(
    df: pd.DataFrame,
    asof_date: str | pd.Timestamp,
    date_col: str = "date",
) -> pd.DataFrame:
    """Return rows strictly BEFORE asof_date.

    Lookahead invariant: at the open of session T, only data from sessions with
    timestamp < T is observable. PRD §6 + CLAUDE.md §"No lookahead bias".

    Strict `<`, not `<=`. If you change this, every downstream backtest assumption
    breaks. Person 2 verifies on every PR that touches data access.
    """
    asof = pd.to_datetime(asof_date)
    mask = pd.to_datetime(df[date_col]) < asof
    return df.loc[mask].copy()
