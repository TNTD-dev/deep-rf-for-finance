"""Schema + timezone + lookahead-math invariants for news_align.

The lookahead math (`compute_available_for_session`) is the highest-risk
function in PKG-2. If it's wrong by one session, every backtest decision
that depends on news sees the future. Tests here are intentionally explicit
about the WHY behind each boundary check.
"""

from __future__ import annotations

import pandas as pd

from src.data_pipeline.news_align import (
    compute_available_for_session,
    normalize_for_match,
    to_utc,
    visible_news_at,
)


def test_to_utc_strips_local_offset() -> None:
    """Naive Asia/HCM input → UTC subtracts 7 hours.

    vnstock returns `2025-06-15T14:30:00` without tz; that's local Hanoi time
    (UTC+7). After to_utc, we want `2025-06-15T07:30:00+00:00`.
    """
    out = to_utc(pd.Series(["2025-06-15 14:30:00"]))
    assert str(out.iloc[0]) == "2025-06-15 07:30:00+00:00"


def test_to_utc_handles_tz_aware_input() -> None:
    """CafeF lastmod includes `+07:00` — must pass through to UTC cleanly."""
    out = to_utc(pd.Series(["2025-06-15T14:30:00+07:00"]))
    assert str(out.iloc[0]) == "2025-06-15 07:30:00+00:00"


def _make_calendar() -> pd.DatetimeIndex:
    """Mon-Fri Jun 9-13 + Mon-Fri Jun 16-20 — gap over Sat/Sun."""
    return pd.DatetimeIndex(
        pd.to_datetime(
            [
                "2025-06-09",  # Mon
                "2025-06-10",  # Tue
                "2025-06-11",  # Wed
                "2025-06-12",  # Thu
                "2025-06-13",  # Fri
                "2025-06-16",  # Mon
                "2025-06-17",  # Tue
                "2025-06-18",  # Wed
                "2025-06-19",  # Thu
                "2025-06-20",  # Fri
            ]
        )
    )


def test_compute_available_for_session_is_d_plus_2() -> None:
    """News published Monday → visible Wednesday open (D+1 close + 1).

    Decision agent at Wed open sees news from Mon (D+1=Tue close, D+2=Wed open).
    """
    cal = _make_calendar()
    news = to_utc(pd.Series(["2025-06-09 14:00:00"]))  # Mon afternoon HCM
    out = compute_available_for_session(news, cal)
    assert out.iloc[0] == pd.Timestamp("2025-06-11")  # Wed


def test_compute_available_for_session_handles_weekend() -> None:
    """News on Friday → visible Tuesday (D+1=Mon close, D+2=Tue open).

    Sat/Sun are not in the trading calendar; advancing by 2 sessions naturally
    skips them.
    """
    cal = _make_calendar()
    news = to_utc(pd.Series(["2025-06-13 16:00:00"]))  # Fri afternoon HCM
    out = compute_available_for_session(news, cal)
    assert out.iloc[0] == pd.Timestamp("2025-06-17")  # Tue


def test_compute_available_for_session_returns_nat_when_no_future() -> None:
    """If only 1 future session exists in calendar, we can't satisfy D+2 → NaT."""
    cal = _make_calendar()
    # News on Jun 19 (Thu) — only Jun 20 (Fri) is after, no second future session
    news = to_utc(pd.Series(["2025-06-19 14:00:00"]))
    out = compute_available_for_session(news, cal)
    assert pd.isna(out.iloc[0])


def test_visible_news_at_le_semantics() -> None:
    """available_for_session == asof IS visible (already usable that session)."""
    df = pd.DataFrame(
        {
            "available_for_session": pd.to_datetime(
                ["2025-06-11", "2025-06-12", "2025-06-13"]
            ),
            "title": ["A", "B", "C"],
        }
    )
    out = visible_news_at(df, "2025-06-12")
    assert out["title"].tolist() == ["A", "B"]


def test_visible_news_at_skips_nat() -> None:
    """News with NaT available_for_session must NEVER appear, regardless of asof."""
    df = pd.DataFrame(
        {
            "available_for_session": pd.to_datetime(["2025-06-11", pd.NaT]),
            "title": ["real", "future-news-no-calendar"],
        }
    )
    out = visible_news_at(df, "2099-01-01")
    assert out["title"].tolist() == ["real"]


def test_normalize_for_match_strips_diacritics() -> None:
    """Vietnamese diacritics → ASCII so alias regex can word-boundary match."""
    assert normalize_for_match("Ngân hàng Ngoại Thương") == "ngan hang ngoai thuong"
    assert normalize_for_match("Hòa Phát") == "hoa phat"
    assert normalize_for_match("Vietcombank") == "vietcombank"
