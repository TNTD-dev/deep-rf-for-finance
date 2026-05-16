"""Single-LLM agentic trader — tool-using.

One LLM. 4 tools (price, indicators, news, fundamentals) bound to a per-decision
LookaheadSafeTools instance. Per ISO week: client.chat loops up to 10
iterations, feeding tool results back as ``role: tool`` messages, until LLM
emits text → parse JSON weights.

Weekly cadence (D1): same as zero_shot. Network/parse/cap failures all fall
back to hold-shares (parser semantics). Tool dispatch errors are fed back to
the LLM as ``{"error": ...}`` so it can self-correct mid-decision instead of
crashing the backtest.

Audit log: one JSONL row per LLM iteration + one decision summary row,
written to ``results/single_agentic/tool_calls.jsonl`` (Issue #8 acceptance
+ feeds PKG-10 hallucination metric).
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from src import config
from src.env_data_loader import MarketData
from src.llm import metrics
from src.llm.client import ChatResult, OpenAIClient
from src.llm.parser import _hold_shares_action, parse_weights_json
from src.llm.serialize import state_to_text
from src.llm.tools import LookaheadSafeTools

log = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "single_agentic.md"
SYSTEM_PROMPT: str = _PROMPT_PATH.read_text(encoding="utf-8")
_DEFAULT_AUDIT_PATH = (
    config.PROJECT_ROOT / "results" / "single_agentic" / "tool_calls.jsonl"
)
_DEFAULT_MAX_ITERATIONS: int = 10


class SingleAgenticTrader:
    """LLM agent that uses 4 tools to investigate before emitting weights."""

    name: str = "single_agentic"

    def __init__(
        self,
        market_data: MarketData,
        news_data: pd.DataFrame,
        model: str = "gpt-4o-mini",
        client: OpenAIClient | None = None,
        weekly_rebalance: bool = True,
        max_iterations: int = _DEFAULT_MAX_ITERATIONS,
        audit_log_path: Path | None = _DEFAULT_AUDIT_PATH,
    ) -> None:
        self.market_data = market_data
        self.news_data = news_data
        self.model = model
        self._client = client or OpenAIClient()
        self.weekly_rebalance = weekly_rebalance
        self.max_iterations = int(max_iterations)
        self.audit_log_path = (
            Path(audit_log_path) if audit_log_path is not None else None
        )
        self._last_week: tuple[int, int] | None = None
        self._cached: np.ndarray | None = None

    def decide(self, obs: np.ndarray, info: dict) -> np.ndarray:
        # _is_rebalance_day advances _last_week as a side effect; always call.
        is_rebal = self._is_rebalance_day(info)
        if (
            self.weekly_rebalance
            and self._cached is not None
            and not is_rebal
        ):
            return self._cached.copy()

        asof = pd.Timestamp(info["date"]).normalize()
        tools = LookaheadSafeTools(self.market_data, self.news_data, asof)
        tool_specs = LookaheadSafeTools.tool_specs()
        messages: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": self._build_user_message(info)},
        ]

        tool_name_counts: Counter[str] = Counter()
        iterations_used = 0
        cap_hit = False
        final_text: str | None = None

        try:
            while iterations_used < self.max_iterations:
                result = self._client.chat(
                    model=self.model,
                    messages=messages,
                    tools=tool_specs,
                    tool_choice="auto",
                    temperature=0.0,
                )
                if not result.tool_calls:
                    self._audit_iteration(iterations_used, info, result, [])
                    final_text = result.text
                    break

                # Reconstruct assistant message + dispatch each tool call.
                messages.append(self._assistant_message(result))
                per_call_results: list[dict] = []
                for tc in result.tool_calls:
                    payload, errored = self._dispatch_tool_call(tools, tc)
                    tool_name_counts[tc["name"]] += 1
                    per_call_results.append({"errored": errored})
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": json.dumps(
                                payload, ensure_ascii=False, default=str
                            ),
                        }
                    )
                self._audit_iteration(
                    iterations_used, info, result, per_call_results
                )
                iterations_used += 1
            else:
                # while/else: ran out of iterations without break → cap hit.
                cap_hit = True
                log.warning(
                    "single_agentic iteration cap %d hit at %s",
                    self.max_iterations,
                    info.get("date"),
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
            self._audit_decision(
                info,
                iterations_used,
                cap_hit,
                None,
                action,
                False,
                tool_name_counts,
                network_error=str(e),
            )
            self._cached = action
            return action.copy()

        if cap_hit and final_text is None:
            metrics.record_parse_failure(reason="iteration_cap")
            action = _hold_shares_action(
                info, list(self.market_data.tickers)
            )
            ok = False
        else:
            action, ok = parse_weights_json(
                final_text,
                info,
                ticker_order=list(self.market_data.tickers),
            )

        self._audit_decision(
            info,
            iterations_used,
            cap_hit,
            final_text,
            action,
            ok,
            tool_name_counts,
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
        # PKG-7 does NOT pre-inject news — the LLM should call get_news()
        # when it wants headlines. Keeps the prompt small and forces tool use.
        state_text = state_to_text(info, self.market_data, news_df=None)
        return (
            state_text
            + "\n\n## Yêu cầu\n"
            "Bạn có thể gọi các công cụ (get_price_history, "
            "get_indicators, get_news, get_fundamentals) nếu cần thêm "
            "thông tin. Khi đã đủ căn cứ, trả về DUY NHẤT một khối JSON "
            "với weights cho 5 mã (VCB, FPT, HPG, VIC, VNM)."
        )

    @staticmethod
    def _assistant_message(result: ChatResult) -> dict:
        """Reconstruct OpenAI assistant wire shape from ChatResult.

        ChatResult.tool_calls[i].arguments is a parsed dict (from
        OpenAIClient._to_result); OpenAI's function-calling wire format wants
        it back as a JSON STRING. Re-encode here.
        """
        return {
            "role": "assistant",
            "content": result.text,
            "tool_calls": [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(
                            tc["arguments"], ensure_ascii=False
                        ),
                    },
                }
                for tc in result.tool_calls
            ],
        }

    @staticmethod
    def _dispatch_tool_call(
        tools: LookaheadSafeTools, tc: dict
    ) -> tuple[object, bool]:
        """Dispatch a single tool call; convert errors to LLM-readable payloads.

        Returns (payload, errored). errored=True if dispatch raised — PKG-10
        reads this to compute hallucination_rate.

        Broad ``except Exception`` is intentional: PRD/CLAUDE.md invariant
        "never crash a backtest". LLMs may pass any arg shape (bad date
        strings, off-universe tickers, missing args, partially-parsed JSON);
        the tool layer may surface pandas / dateparser / type errors; all of
        these should be fed back as tool results so the LLM can self-correct.
        """
        try:
            return (
                tools.dispatch(tc["name"], tc.get("arguments") or {}),
                False,
            )
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"}, True

    def _audit_iteration(
        self,
        iteration: int,
        info: dict,
        result: ChatResult,
        per_call_results: list[dict],
    ) -> None:
        if self.audit_log_path is None:
            return
        rec = {
            "ts": datetime.now(UTC).isoformat(),
            "agent": self.name,
            "event": "iteration",
            "date": str(info.get("date", ""))[:10],
            "iteration": iteration,
            "model": result.model,
            "finish_reason": result.finish_reason,
            "n_tool_calls": len(result.tool_calls),
            "tool_calls": [
                {
                    "id": tc["id"],
                    "name": tc["name"],
                    "args": tc["arguments"],
                    "errored": (
                        per_call_results[i]["errored"]
                        if i < len(per_call_results)
                        else False
                    ),
                }
                for i, tc in enumerate(result.tool_calls)
            ],
            "usage": result.usage,
        }
        self._write_audit(rec)

    def _audit_decision(
        self,
        info: dict,
        iterations_used: int,
        cap_hit: bool,
        final_text: str | None,
        action: np.ndarray,
        parse_ok: bool,
        tool_name_counts: Counter[str],
        network_error: str | None = None,
    ) -> None:
        if self.audit_log_path is None:
            return
        preview = (final_text or "")[:200]
        rec = {
            "ts": datetime.now(UTC).isoformat(),
            "agent": self.name,
            "event": "decision",
            "date": str(info.get("date", ""))[:10],
            "iterations_used": iterations_used,
            "cap_hit": cap_hit,
            "network_error": network_error,
            "final_text_preview": preview,
            "parse_ok": parse_ok,
            "action_sum": float(action.sum()) if action is not None else None,
            "tool_name_counts": dict(tool_name_counts),
        }
        self._write_audit(rec)

    def _write_audit(self, rec: dict) -> None:
        try:
            self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.audit_log_path.open("a", encoding="utf-8") as f:
                f.write(
                    json.dumps(rec, ensure_ascii=False, default=str) + "\n"
                )
        except OSError as e:
            log.warning("audit log write failed: %s", e)
