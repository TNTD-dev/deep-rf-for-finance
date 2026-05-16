"""Convert env state + holdings + indicators + news → markdown bullets for LLM.

Markdown chosen over JSON: more compact (no quoting overhead), LLM ingests
cleanly, human-readable in transcripts. Layout is stable so OpenAI prompt
caching can hit on the system + preamble portion (cache triggers at ≥ 1024
tokens automatic).
"""

from __future__ import annotations

import pandas as pd

from src import config
from src.data_pipeline.indicators import INDICATOR_COLS
from src.env_data_loader import MarketData


def state_to_text(
    info: dict,
    market_data: MarketData,
    news_df: pd.DataFrame | None = None,
    session_idx: int | None = None,
    total_sessions: int | None = None,
) -> str:
    """Top-level serializer combining portfolio + indicators + news sections."""
    parts = [
        _header(info, session_idx, total_sessions),
        holdings_to_text(info, market_data),
        indicators_to_text(info, market_data),
    ]
    if news_df is not None and not news_df.empty:
        parts.append(news_to_bullets(news_df))
    return "\n\n".join(parts)


def _header(
    info: dict, session_idx: int | None, total_sessions: int | None
) -> str:
    date_str = str(info.get("date", "?"))[:10]
    weekday = pd.Timestamp(info["date"]).day_name() if info.get("date") else "?"
    progress = ""
    if session_idx is not None and total_sessions is not None:
        progress = f", session {session_idx} of {total_sessions}"
    return f"## Decision date: {date_str} ({weekday}{progress})"


def holdings_to_text(info: dict, market_data: MarketData) -> str:
    pv = float(info.get("portfolio_value", 0.0))
    cash = float(info.get("cash", 0.0))
    holdings = info.get("holdings", [0] * len(market_data.tickers))
    close_t = info.get("close_t", [1.0] * len(market_data.tickers))
    cash_pct = (cash / pv * 100) if pv > 0 else 0.0

    lines = [
        "## Portfolio",
        f"- Total value: {pv:,.0f} VND",
        f"- Cash: {cash:,.0f} VND ({cash_pct:.1f}%)",
        "- Holdings:",
    ]
    for i, ticker in enumerate(market_data.tickers):
        shares = int(holdings[i])
        price = float(close_t[i])
        value = shares * price
        pct = (value / pv * 100) if pv > 0 else 0.0
        lines.append(
            f"  - {ticker}: {shares:,} shares × {price:,.2f} VND = "
            f"{value:,.0f} VND ({pct:.1f}%)"
        )
    return "\n".join(lines)


def indicators_to_text(info: dict, market_data: MarketData) -> str:
    """Pipe table — LLMs parse markdown tables well; one row per ticker."""
    t = int(info.get("t", market_data.warmup_offset))
    t = min(t, len(market_data.dates) - 1)
    close_t = info.get("close_t", market_data.close[t].tolist())

    # Pick a compact subset of indicators for prompt brevity
    show_cols = ["rsi14", "macd", "sma20", "bb_upper", "bb_lower", "atr14"]
    col_idx = [INDICATOR_COLS.index(c) for c in show_cols]

    header = "| Ticker | Close | " + " | ".join(show_cols) + " |"
    sep = "|" + "|".join(["---"] * (len(show_cols) + 2)) + "|"
    rows = [header, sep]
    for i, ticker in enumerate(market_data.tickers):
        vals = market_data.indicators_norm[t, i, :]
        cells = [f"{float(vals[k]):+.2f}" for k in col_idx]
        rows.append(
            f"| {ticker} | {float(close_t[i]):,.2f} | " + " | ".join(cells) + " |"
        )
    return "## Recent indicators (z-scored, latest pre-decision session)\n" + "\n".join(rows)


def news_to_bullets(news_df: pd.DataFrame, max_items: int = 10) -> str:
    """Render news as bullets, filtered to universe tickers, capped at max_items.

    Input ``news_df`` already filtered for visibility (caller passes
    ``visible_news_at(...)`` output). We further filter to rows whose
    ``tickers`` list overlaps ``config.TICKERS``.
    """
    if news_df.empty:
        return "## Recent news\n- (no recent news visible)"
    universe = set(config.TICKERS)
    mask = news_df["tickers"].apply(lambda lst: bool(set(lst) & universe))
    relevant = news_df.loc[mask].sort_values("published_at_utc", ascending=False).head(max_items)
    if relevant.empty:
        return "## Recent news\n- (no relevant news for universe)"
    lines = ["## Recent news (most recent first, visible to today's open)"]
    for r in relevant.itertuples():
        ts = pd.Timestamp(r.published_at_utc).strftime("%Y-%m-%d %H:%M")
        tickers_str = ",".join(t for t in r.tickers if t in universe)
        title = (r.title or "").strip()
        lines.append(f"- [{ts}] [{tickers_str}] {title}")
    return "\n".join(lines)
