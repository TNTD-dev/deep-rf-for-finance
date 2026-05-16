"""Zero-shot LLM trader — one OpenAI chat call per ISO week.

Reads env state via PKG-5 serialize, sends single prompt, parses JSON
weights. No tools. Cost target ~$0.25/backtest with gpt-4o-mini default
(≈ 51 ISO weeks × $0.005/call on the test split).

Weekly cadence (D1 in plan): ISO week change triggers a re-decide; same
week returns cached weights, so the 248-session env loop fires ~51 LLM
calls instead of 248.

Failure handling: network failure after client's 5 retries → hold-shares
fallback + parse_failure metric. Parser already falls back to hold-shares
on malformed JSON; this module's only own failure path is the catch around
``client.chat``.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from src.data_pipeline.news_align import visible_news_at
from src.env_data_loader import MarketData
from src.llm import metrics
from src.llm.client import OpenAIClient
from src.llm.parser import _hold_shares_action, parse_weights_json
from src.llm.serialize import state_to_text

log = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "zero_shot.md"
SYSTEM_PROMPT: str = _PROMPT_PATH.read_text(encoding="utf-8")
_MAX_NEWS_ITEMS: int = 10


class ZeroShotTrader:
    """LLM agent that emits target weights from a single chat call per week."""

    name: str = "zero_shot"

    def __init__(
        self,
        market_data: MarketData,
        news_data: pd.DataFrame,
        model: str = "gpt-4o-mini",
        client: OpenAIClient | None = None,
        weekly_rebalance: bool = True,
    ) -> None:
        self.market_data = market_data
        self.news_data = news_data
        self.model = model
        self._client = client or OpenAIClient()
        self.weekly_rebalance = weekly_rebalance
        self._last_week: tuple[int, int] | None = None
        self._cached: np.ndarray | None = None

    def decide(self, obs: np.ndarray, info: dict) -> np.ndarray:
        # _is_rebalance_day has a side effect of advancing _last_week; always
        # call so cached state stays in sync, even when we skip the LLM call.
        is_rebal = self._is_rebalance_day(info)
        if (
            self.weekly_rebalance
            and self._cached is not None
            and not is_rebal
        ):
            return self._cached.copy()

        user_text = self._build_user_message(info)
        try:
            result = self._client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_text},
                ],
                temperature=0.0,
            )
            action, _ok = parse_weights_json(
                result.text,
                info,
                ticker_order=list(self.market_data.tickers),
            )
        except RuntimeError as e:
            log.warning(
                "LLM call failed for %s at %s: %s — hold-shares fallback",
                self.name,
                info.get("date"),
                e,
            )
            metrics.record_parse_failure(reason=f"network_{type(e).__name__}")
            action = _hold_shares_action(
                info, list(self.market_data.tickers)
            )
        self._cached = action
        return action.copy()

    def _is_rebalance_day(self, info: dict) -> bool:
        ts = pd.Timestamp(info["date"])
        iso = ts.isocalendar()
        key = (int(iso.year), int(iso.week))
        if key != self._last_week:
            self._last_week = key
            return True
        return False

    def _build_user_message(self, info: dict) -> str:
        asof = pd.Timestamp(info["date"]).normalize()
        visible = (
            visible_news_at(self.news_data, asof)
            if not self.news_data.empty
            else self.news_data
        )
        if not visible.empty:
            universe = set(self.market_data.tickers)
            mask = visible["tickers"].apply(
                lambda lst: bool(set(lst) & universe)
            )
            visible = (
                visible.loc[mask]
                .sort_values("published_at_utc", ascending=False)
                .head(_MAX_NEWS_ITEMS)
            )
        state_text = state_to_text(info, self.market_data, news_df=visible)
        return (
            state_text
            + "\n\n## Yêu cầu\nDựa trên thông tin trên, trả về DUY NHẤT một "
              "khối JSON với weights cho 5 mã (VCB, FPT, HPG, VIC, VNM)."
        )
