"""LookaheadSafeTools — 4 OpenAI-compatible tools every LLM agent uses.

All data access flows through PKG-1/2 lookahead helpers
(``window_until``, ``visible_news_at``). Single source of truth so Person 2
can audit lookahead enforcement at one file instead of N agent files.

PKG-6/7/8 instantiate per decision with the current ``asof_session``; never
bypass — direct ``MarketData`` access in agent code is a project rule violation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

from src import config
from src.data_pipeline.indicators import INDICATOR_COLS
from src.data_pipeline.news_align import visible_news_at
from src.data_pipeline.vnstock_fundamentals import fetch_fundamentals
from src.env_data_loader import MarketData

FUNDAMENTAL_REPORT_LAG_DAYS: int = 30  # typical VN listed-co reporting lag


@dataclass
class LookaheadSafeTools:
    """Bundle of 4 tool methods bound to a (market_data, news, asof) context.

    Methods return plain dicts/lists so they serialize cleanly into OpenAI
    tool-call results.
    """

    market_data: MarketData
    news_data: pd.DataFrame
    asof_session: pd.Timestamp

    def __post_init__(self) -> None:
        self.asof_session = pd.Timestamp(self.asof_session).normalize()

    # ---- 4 tools ----------------------------------------------------------

    def get_price_history(self, ticker: str, days: int = 30) -> dict:
        """Last ``days`` sessions of OHLC for ``ticker``, strictly before asof."""
        col = self._ticker_idx(ticker)
        mask = self.market_data.dates < self.asof_session
        if not mask.any():
            return {"ticker": ticker, "rows": []}
        dates = self.market_data.dates[mask][-days:]
        close = self.market_data.close[mask][-days:, col]
        high = self.market_data.high[mask][-days:, col]
        low = self.market_data.low[mask][-days:, col]
        return {
            "ticker": ticker,
            "rows": [
                {
                    "date": d.isoformat()[:10],
                    "close": float(c),
                    "high": float(h),
                    "low": float(low_v),
                }
                for d, c, h, low_v in zip(dates, close, high, low, strict=True)
            ],
        }

    def get_indicators(self, ticker: str) -> dict:
        """All 9 indicators at the most recent pre-asof session."""
        col = self._ticker_idx(ticker)
        mask = self.market_data.dates < self.asof_session
        if not mask.any():
            return {"ticker": ticker, "indicators": {}}
        last_idx = int(mask.cumsum()[-1] - 1)
        row = self.market_data.indicators_norm[last_idx, col, :]
        return {
            "ticker": ticker,
            "as_of_date": self.market_data.dates[last_idx].isoformat()[:10],
            "indicators": {
                name: float(v) for name, v in zip(INDICATOR_COLS, row, strict=True)
            },
        }

    def get_news(
        self, date: str | None = None, ticker: str | None = None
    ) -> list[dict]:
        """News visible at ``date`` (defaults to asof_session) for optional
        ``ticker`` filter. Visibility = ``available_for_session <= date``."""
        asof = pd.Timestamp(date).normalize() if date else self.asof_session
        visible = visible_news_at(self.news_data, asof)
        if ticker is not None:
            visible = visible[
                visible["tickers"].apply(lambda lst: ticker in lst)
            ]
        items = []
        for r in visible.sort_values(
            "published_at_utc", ascending=False
        ).itertuples():
            items.append(
                {
                    "published_at": str(r.published_at_utc),
                    "title": str(r.title),
                    "tickers": list(r.tickers),
                    "url": r.url if pd.notna(r.url) else None,
                }
            )
            if len(items) >= 20:
                break
        return items

    def get_fundamentals(self, ticker: str) -> dict:
        """4-quarter snapshot from vnstock; quarters released within
        ``FUNDAMENTAL_REPORT_LAG_DAYS`` of asof are filtered out (not yet
        public knowledge)."""
        df = fetch_fundamentals(ticker)
        df = df[df["period"].apply(self._quarter_visible)]
        return {
            "ticker": ticker,
            "quarters_available": sorted(df["period"].unique().tolist()),
            "items": [
                {
                    "statement": r.statement,
                    "period": r.period,
                    "item": r.item,
                    "value": float(r.value) if pd.notna(r.value) else None,
                }
                for r in df.itertuples()
            ][:50],
        }

    # ---- OpenAI tool spec + dispatch -------------------------------------

    @classmethod
    def tool_specs(cls) -> list[dict]:
        """OpenAI function-calling JSON specs for all 4 methods."""
        ticker_enum = list(config.TICKERS)
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_price_history",
                    "description": (
                        "Last N daily OHLC bars for a ticker, strictly before "
                        "decision date. Use to inspect recent price action."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "ticker": {"type": "string", "enum": ticker_enum},
                            "days": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 252,
                                "default": 30,
                            },
                        },
                        "required": ["ticker"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_indicators",
                    "description": (
                        "9 z-scored technical indicators (RSI/MACD/SMA/Bollinger/ATR) "
                        "for a ticker at the most recent pre-decision session."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "ticker": {"type": "string", "enum": ticker_enum}
                        },
                        "required": ["ticker"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_news",
                    "description": (
                        "News headlines visible at the decision date "
                        "(news on day D visible from D+2 session open). "
                        "Optionally filter by ticker."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "date": {
                                "type": "string",
                                "description": "YYYY-MM-DD; defaults to decision date",
                            },
                            "ticker": {"type": "string", "enum": ticker_enum},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_fundamentals",
                    "description": (
                        "Quarterly fundamentals snapshot (last 4 quarters, "
                        "filtered for ~30-day reporting lag)."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "ticker": {"type": "string", "enum": ticker_enum}
                        },
                        "required": ["ticker"],
                    },
                },
            },
        ]

    def dispatch(self, name: str, arguments: dict) -> dict | list:
        """Map ``tool_call.function.name + arguments`` to instance method.

        Used by single-agentic + multi-agent loops. Unknown names raise loud —
        LLMs sometimes hallucinate method names like ``get_market_cap``.
        """
        if name not in {
            "get_price_history",
            "get_indicators",
            "get_news",
            "get_fundamentals",
        }:
            raise ValueError(f"unknown tool {name!r}")
        method = getattr(self, name)
        return method(**(arguments or {}))

    # ---- helpers ---------------------------------------------------------

    def _ticker_idx(self, ticker: str) -> int:
        if ticker not in self.market_data.tickers:
            raise ValueError(
                f"unknown ticker {ticker!r}; expected one of "
                f"{list(self.market_data.tickers)}"
            )
        return self.market_data.tickers.index(ticker)

    def _quarter_visible(self, period_str: str) -> bool:
        """True iff quarter ``YYYY-Qn`` was published ≥ ``FUNDAMENTAL_REPORT_LAG_DAYS``
        before asof. Conservative — under-shows fresh quarters by ~30 days."""
        m = re.match(r"(\d{4})-Q([1-4])", str(period_str))
        if not m:
            return False
        year, q = int(m.group(1)), int(m.group(2))
        q_end_month = q * 3
        q_end = pd.Timestamp(year=year, month=q_end_month, day=1) + pd.offsets.MonthEnd(0)
        visible_from = q_end + pd.Timedelta(days=FUNDAMENTAL_REPORT_LAG_DAYS)
        return visible_from <= self.asof_session
