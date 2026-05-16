"""Canonical news schema + lookahead-safe visibility helpers.

Lookahead invariant (CLAUDE.md §1, PRD §11): news published on day D is only
visible to decisions made from session D+1 close onward. For a decision at
session T open, visible news has `available_for_session <= T`.

We pre-compute `available_for_session` at ingest time so consumers never do
timestamp arithmetic themselves. The math:

    news published locally on date D
    → first trading session strictly after D is D+1 (the "close" session)
    → first session whose OPEN sees this news is D+2

So `available_for_session = calendar[i+1]` where `i = calendar.searchsorted(D, "right")`.

The two-session lag is intentional. A morning-rebalance agent at session T open
must NOT see news published before T's open same day (would leak signal from
overnight events that the market may not have priced in yet). Strict.
"""

from __future__ import annotations

import unicodedata

import pandas as pd

TZ_VN: str = "Asia/Ho_Chi_Minh"

NEWS_SCHEMA: list[str] = [
    "published_at_utc",       # datetime64[ns, UTC]
    "available_for_session",  # datetime64[ns] — first trading session usable
    "source",                 # "vnstock" | "cafef" | "cafef_live"
    "url",                    # canonical URL (None for vnstock disclosures)
    "title",                  # str
    "summary",                # str | None
    "tickers",                # list[str] — non-empty, sorted, unique
]


def to_utc(ts: pd.Series, source_tz: str = TZ_VN) -> pd.Series:
    """Normalize timestamps to UTC.

    vnstock `public_date` is ISO without tz — local Asia/Ho_Chi_Minh time.
    CafeF `lastmod` carries `+07:00`. We strip both to UTC for consistent
    ordering across sources.
    """
    s = pd.to_datetime(ts, errors="coerce", utc=False)
    if s.dt.tz is None:
        s = s.dt.tz_localize(
            source_tz, ambiguous="NaT", nonexistent="shift_forward"
        )
    return s.dt.tz_convert("UTC")


def compute_available_for_session(
    published_at_utc: pd.Series,
    trading_calendar: pd.DatetimeIndex,
) -> pd.Series:
    """For each news row, find the first trading session usable by an OPEN-decision agent.

    Math: news published on local date D becomes part of the information set at
    D+1's CLOSE. The next decision-maker session is D+2's OPEN. So we return
    the calendar entry two sessions after D.

    Implementation: convert UTC → Asia/HCM date D; find calendar position
    strictly greater than D; advance one more session.

    Returns NaT for news so recent that two future sessions don't exist yet
    in the calendar — caller should drop or label as "not yet usable".
    """
    vn_dates = (
        published_at_utc.dt.tz_convert(TZ_VN).dt.normalize().dt.tz_localize(None)
    )
    cal = trading_calendar.normalize()
    out = pd.Series(pd.NaT, index=vn_dates.index, dtype="datetime64[ns]")
    for i, d in enumerate(vn_dates):
        if pd.isna(d):
            continue
        idx = cal.searchsorted(d, side="right")  # first session > d (= D+1 close)
        if idx + 1 < len(cal):
            out.iloc[i] = cal[idx + 1]  # D+2 open consumer
    return out


def visible_news_at(
    news_df: pd.DataFrame,
    asof_session: str | pd.Timestamp,
) -> pd.DataFrame:
    """Return news visible at the OPEN of asof_session.

    Filters `available_for_session <= asof_session`. This is the only access
    pattern downstream code should use — mirrors window_until in calendar.py.

    Note `<=` here, NOT `<`: `available_for_session` is already the first
    session at which the news is usable, so equality means "usable today".
    """
    asof = pd.to_datetime(asof_session).normalize()
    if "available_for_session" not in news_df.columns:
        # Empty news_df with no schema — return same shape so downstream
        # column access (sort_values, etc.) doesn't KeyError.
        return news_df.copy()
    mask = (news_df["available_for_session"] <= asof) & news_df[
        "available_for_session"
    ].notna()
    return news_df.loc[mask].copy()


def normalize_for_match(s: str) -> str:
    """Strip Vietnamese diacritics and lowercase for alias matching.

    'Vietcombank' → 'vietcombank', 'Ngân hàng Ngoại Thương' → 'ngan hang
    ngoai thuong'. Risk: false positives on common Vietnamese words; we
    restrict matching to word boundaries in the alias regex.
    """
    nfd = unicodedata.normalize("NFD", s)
    no_diacritic = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    return no_diacritic.lower()
