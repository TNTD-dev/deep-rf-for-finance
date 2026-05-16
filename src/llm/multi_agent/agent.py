"""MultiAgentTrader — Agent Protocol wrapper around the LangGraph app.

Weekly cadence + timeout + transcript writes + parser. The compiled graph
is stateless across decisions; this class owns the per-decision lifecycle:
build initial state → invoke graph with wallclock cap → parse portfolio
manager output → write transcript + decisions log → cache + return action.

Mirrors PKG-6/7 patterns (weekly cadence, fallback hold-shares,
audit-log toggle).
"""

from __future__ import annotations

import concurrent.futures
import logging
import time
from pathlib import Path

import numpy as np
import pandas as pd

from src import config
from src.env_data_loader import MarketData
from src.llm import metrics
from src.llm.client import OpenAIClient
from src.llm.multi_agent.graph import build_app
from src.llm.multi_agent.state import (
    ROLE_NAMES,
    make_initial_state,
)
from src.llm.multi_agent.transcript import (
    append_decision_log,
    now_iso,
    write_transcript,
)
from src.llm.parser import _hold_shares_action, parse_weights_json
from src.llm.tools import LookaheadSafeTools

log = logging.getLogger(__name__)

_DEFAULT_TRANSCRIPT_DIR = (
    config.PROJECT_ROOT / "results" / "multi_agent" / "transcripts"
)
_DEFAULT_DECISIONS_PATH = (
    config.PROJECT_ROOT / "results" / "multi_agent" / "decisions.jsonl"
)
_DEFAULT_MODELS: dict[str, str] = {
    "technical_analyst":      "gpt-4o-mini",
    "news_sentiment_analyst": "gpt-4o-mini",
    "fundamental_analyst":    "gpt-4o-mini",
    "bullish_researcher":     "gpt-4o",
    "bearish_researcher":     "gpt-4o",
    "trader":                 "gpt-4o",
    "risk_manager":           "gpt-4o",
    "portfolio_manager":      "gpt-4o",
}
_DEFAULT_DEBATE_ROUNDS: int = 2
# Per-decision wallclock cap. PRD §14 Risk #5 + Issue #9 target "< 30s with
# real OpenAI". Real-world: 10 sequential LLM calls × ~5s OpenAI tail latency
# = ~50s observed in smoke. Default raised to 60s to accept this reality;
# follow-up optimization (parallel analyst fan-out via LangGraph) can pull
# this back. Hold-shares fallback still fires on overflow, so backtest never
# crashes.
_DEFAULT_TIMEOUT_S: float = 60.0


class MultiAgentTrader:
    """LangGraph multi-agent trader implementing the Agent Protocol."""

    name: str = "multi_agent"

    def __init__(
        self,
        market_data: MarketData,
        news_data: pd.DataFrame,
        models: dict[str, str] | None = None,
        client: OpenAIClient | None = None,
        weekly_rebalance: bool = True,
        debate_rounds: int = _DEFAULT_DEBATE_ROUNDS,
        decision_timeout_s: float = _DEFAULT_TIMEOUT_S,
        transcript_dir: Path | None = _DEFAULT_TRANSCRIPT_DIR,
        decisions_log_path: Path | None = _DEFAULT_DECISIONS_PATH,
    ) -> None:
        self.market_data = market_data
        self.news_data = news_data
        self.models = {**_DEFAULT_MODELS, **(models or {})}
        self._validate_models()
        self._client = client or OpenAIClient()
        self.weekly_rebalance = weekly_rebalance
        self.debate_rounds = int(debate_rounds)
        self.decision_timeout_s = float(decision_timeout_s)
        self.transcript_dir = (
            Path(transcript_dir) if transcript_dir is not None else None
        )
        self.decisions_log_path = (
            Path(decisions_log_path) if decisions_log_path is not None else None
        )
        self._last_week: tuple[int, int] | None = None
        self._cached: np.ndarray | None = None
        self._app = build_app()

    def decide(self, obs: np.ndarray, info: dict) -> np.ndarray:
        is_rebal = self._is_rebalance_day(info)
        if (
            self.weekly_rebalance
            and self._cached is not None
            and not is_rebal
        ):
            return self._cached.copy()

        date_str = pd.Timestamp(info["date"]).strftime("%Y-%m-%d")
        asof = pd.Timestamp(info["date"]).normalize()
        tools = LookaheadSafeTools(self.market_data, self.news_data, asof)

        initial = make_initial_state(
            market_data=self.market_data,
            news_data=self.news_data,
            info=info,
            client=self._client,
            models=self.models,
            tools=tools,
            debate_rounds_max=self.debate_rounds,
        )

        cost_before = metrics.get_snapshot().get("estimated_cost_usd", 0.0)
        t0 = time.monotonic()
        timed_out = False
        final_state: dict | None = None
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(self._app.invoke, initial)
                final_state = fut.result(timeout=self.decision_timeout_s)
        except concurrent.futures.TimeoutError:
            timed_out = True
            log.warning(
                "multi_agent timeout %.1fs at %s",
                self.decision_timeout_s,
                date_str,
            )
            metrics.record_parse_failure(reason="multi_agent_timeout")

        duration_s = time.monotonic() - t0

        if timed_out or final_state is None:
            action = _hold_shares_action(
                info, list(self.market_data.tickers)
            )
            cost_delta = (
                metrics.get_snapshot().get("estimated_cost_usd", 0.0)
                - cost_before
            )
            self._write_outputs(
                info,
                final_state,
                duration_s,
                timed_out=True,
                action=action,
                parse_ok=False,
                cost_delta=cost_delta,
            )
            self._cached = action
            return action.copy()

        raw_text = final_state.get("portfolio_manager_output", "")
        action, parse_ok = parse_weights_json(
            raw_text, info, ticker_order=list(self.market_data.tickers)
        )
        cost_delta = (
            metrics.get_snapshot().get("estimated_cost_usd", 0.0) - cost_before
        )
        self._write_outputs(
            info,
            final_state,
            duration_s,
            timed_out=False,
            action=action,
            parse_ok=parse_ok,
            cost_delta=cost_delta,
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

    def _validate_models(self) -> None:
        for role, model in self.models.items():
            if model not in config.LLM_ALLOWED_MODELS:
                raise ValueError(
                    f"model {model!r} for role {role!r} not in whitelist "
                    f"{sorted(config.LLM_ALLOWED_MODELS)} — see CLAUDE.md §2"
                )
        # Defensive: every canonical role must be assigned a model
        missing = set(ROLE_NAMES) - set(self.models.keys())
        if missing:
            raise ValueError(f"missing model assignment for roles: {sorted(missing)}")

    def _write_outputs(
        self,
        info: dict,
        final_state: dict | None,
        duration_s: float,
        timed_out: bool,
        action: np.ndarray,
        parse_ok: bool,
        cost_delta: float,
    ) -> None:
        date_str = pd.Timestamp(info["date"]).strftime("%Y-%m-%d")
        fs = final_state or {}
        transcript = fs.get("transcript", [])
        node_errors = fs.get("node_errors", [])
        debate_rounds_used = fs.get("debate_round", 0)

        if self.transcript_dir is not None:
            payload = {
                "date": date_str,
                "agent": self.name,
                "duration_s": duration_s,
                "debate_rounds": debate_rounds_used,
                "timed_out": timed_out,
                "node_errors": node_errors,
                "models_used": self.models,
                # Transcript is the meat. Strip live inputs (market_data,
                # client, tools) since they aren't JSON-serializable.
                "transcript": transcript,
                # Include synthesis chain outputs for replay UI
                "trader_proposal": fs.get("trader_proposal", ""),
                "risk_review": fs.get("risk_review", ""),
                "portfolio_manager_output": fs.get(
                    "portfolio_manager_output", ""
                ),
                "debate_exchanges": fs.get("debate_exchanges", []),
            }
            write_transcript(self.transcript_dir, date_str, payload)

        if self.decisions_log_path is not None:
            record = {
                "ts": now_iso(),
                "date": date_str,
                "agent": self.name,
                "duration_s": duration_s,
                "debate_rounds": debate_rounds_used,
                "node_errors_count": len(node_errors),
                "node_error_roles": [e.get("role") for e in node_errors],
                "timed_out": timed_out,
                "parse_ok": parse_ok,
                "action_sum": float(action.sum()) if action is not None else None,
                "cost_delta_usd": cost_delta,
            }
            append_decision_log(self.decisions_log_path, record)
