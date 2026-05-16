"""OpenAI Chat Completions wrapper with model whitelist + exp backoff retry.

Model whitelist is enforced via ValueError — never log a warning, never
fallback to a default. PRD §14 Risk #3 + CLAUDE.md §2: gpt-4o cutoff Oct-2023
keeps test period (2025-05 → 2026-04) out-of-distribution; any non-whitelisted
model would leak future knowledge.

Auto prompt caching: OpenAI caches prompts > 1024 tokens automatically. We
do NOT pass `cache_control` (that's Anthropic). We just structure prompts so
stable system content comes first.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

from openai import APIError, APITimeoutError, OpenAI, RateLimitError

from src import config
from src.llm import metrics

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChatResult:
    """Output of OpenAIClient.chat."""

    text: str | None              # None when model returned only a tool_call
    tool_calls: list[dict]        # each: {id, name, arguments(dict)}
    usage: dict                   # prompt_tokens, completion_tokens, cached_tokens, total_tokens
    model: str
    finish_reason: str


class OpenAIClient:
    def __init__(self, api_key: str | None = None) -> None:
        key = api_key or config.OPENAI_API_KEY
        if not key:
            raise RuntimeError(
                "OPENAI_API_KEY not set; populate .env from .env.example"
            )
        self._client = OpenAI(api_key=key)

    def chat(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: str | dict = "auto",
        max_retries: int = 5,
        temperature: float = 0.0,
    ) -> ChatResult:
        if model not in config.LLM_ALLOWED_MODELS:
            raise ValueError(
                f"model {model!r} not in whitelist "
                f"{sorted(config.LLM_ALLOWED_MODELS)} — see CLAUDE.md §2"
            )
        last_err: Exception | None = None
        for attempt in range(max_retries):
            try:
                kwargs: dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                }
                if tools:
                    kwargs["tools"] = tools
                    kwargs["tool_choice"] = tool_choice
                resp = self._client.chat.completions.create(**kwargs)
                return self._to_result(resp, model)
            except (RateLimitError, APITimeoutError) as e:
                wait = 2**attempt + 1
                log.warning(
                    "OpenAI rate limit/timeout (attempt %d), sleeping %ds: %s",
                    attempt, wait, e,
                )
                time.sleep(wait)
                last_err = e
            except APIError as e:
                status = getattr(e, "status_code", 0) or 0
                if 500 <= status < 600:
                    wait = 2**attempt
                    log.warning(
                        "OpenAI 5xx (attempt %d), retrying in %ds: %s",
                        attempt, wait, e,
                    )
                    time.sleep(wait)
                    last_err = e
                else:
                    raise
        raise RuntimeError(
            f"OpenAI call failed after {max_retries} retries: {last_err}"
        )

    def _to_result(self, resp: Any, model: str) -> ChatResult:
        choice = resp.choices[0]
        msg = choice.message
        tool_calls: list[dict] = []
        for tc in msg.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {"_raw": tc.function.arguments}
            tool_calls.append(
                {"id": tc.id, "name": tc.function.name, "arguments": args}
            )
        usage = self._extract_usage(resp.usage)
        metrics.record_llm_call(model, usage)
        return ChatResult(
            text=msg.content,
            tool_calls=tool_calls,
            usage=usage,
            model=model,
            finish_reason=choice.finish_reason or "",
        )

    @staticmethod
    def _extract_usage(usage: Any) -> dict:
        if usage is None:
            return {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "cached_tokens": 0,
                "total_tokens": 0,
            }
        cached = 0
        ptd = getattr(usage, "prompt_tokens_details", None)
        if ptd is not None:
            cached = int(getattr(ptd, "cached_tokens", 0) or 0)
        return {
            "prompt_tokens": int(usage.prompt_tokens or 0),
            "completion_tokens": int(usage.completion_tokens or 0),
            "cached_tokens": cached,
            "total_tokens": int(usage.total_tokens or 0),
        }
