"""OpenAIClient invariants — model whitelist + tool-call extraction + retry.

All tests mock the OpenAI client class — never makes a real network call.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
import pytest
from openai import RateLimitError

from src import config
from src.llm import metrics
from src.llm.client import ChatResult, OpenAIClient


@dataclass
class _Func:
    name: str
    arguments: str


@dataclass
class _ToolCall:
    id: str
    function: _Func


@dataclass
class _Msg:
    content: str | None
    tool_calls: list[_ToolCall] | None


@dataclass
class _Choice:
    message: _Msg
    finish_reason: str


@dataclass
class _PromptTokensDetails:
    cached_tokens: int


@dataclass
class _Usage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    prompt_tokens_details: _PromptTokensDetails | None = None


@dataclass
class _Resp:
    choices: list[_Choice]
    usage: _Usage


def _ok_resp(text: str = "hello", cached: int = 0) -> _Resp:
    return _Resp(
        choices=[_Choice(_Msg(text, None), "stop")],
        usage=_Usage(
            prompt_tokens=100,
            completion_tokens=10,
            total_tokens=110,
            prompt_tokens_details=_PromptTokensDetails(cached_tokens=cached),
        ),
    )


class _FakeOpenAI:
    """Minimal OpenAI client stand-in used to replace `OpenAI` in tests."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key
        self.calls: list[dict] = []
        self.chat = self._Chat(self)

    class _Chat:
        def __init__(self, parent: _FakeOpenAI) -> None:
            self.parent = parent
            self.completions = self._Completions(parent)

        class _Completions:
            def __init__(self, parent: _FakeOpenAI) -> None:
                self.parent = parent
                self.responses: list[Any] = [_ok_resp()]
                self.exceptions: list[Exception] = []

            def create(self, **kwargs) -> Any:  # noqa: ANN401
                self.parent.calls.append(kwargs)
                if self.exceptions:
                    raise self.exceptions.pop(0)
                if not self.responses:
                    raise RuntimeError("no more fake responses queued")
                return self.responses.pop(0)


def _patch(monkeypatch, fake: _FakeOpenAI | None = None) -> _FakeOpenAI:
    fake = fake or _FakeOpenAI(api_key="sk-test")
    monkeypatch.setattr("src.llm.client.OpenAI", lambda **_: fake)
    return fake


def test_model_whitelist_rejects_gpt35(monkeypatch) -> None:
    """Pass a non-whitelisted model → ValueError with whitelist hint.

    CLAUDE.md §2: model lock prevents data leakage from newer cutoffs.
    """
    _patch(monkeypatch)
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-test")
    client = OpenAIClient()
    with pytest.raises(ValueError, match="not in whitelist"):
        client.chat(model="gpt-3.5-turbo", messages=[])


def test_model_whitelist_rejects_future_model(monkeypatch) -> None:
    """Future hypothetical model → also rejected (future cutoffs leak future)."""
    _patch(monkeypatch)
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-test")
    client = OpenAIClient()
    with pytest.raises(ValueError, match="not in whitelist"):
        client.chat(model="gpt-5-pro", messages=[])


def test_model_whitelist_accepts_gpt4o(monkeypatch) -> None:
    """Happy path with whitelisted model and mocked client."""
    _patch(monkeypatch)
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-test")
    client = OpenAIClient()
    result = client.chat(model="gpt-4o", messages=[{"role": "user", "content": "hi"}])
    assert isinstance(result, ChatResult)
    assert result.text == "hello"
    assert result.model == "gpt-4o"


def test_chat_extracts_tool_calls_with_parsed_args(monkeypatch) -> None:
    """OpenAI tool_call.function.arguments is a JSON STRING; we parse to dict
    so downstream agent code uses native types."""
    fake = _patch(monkeypatch)
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-test")
    fake.chat.completions.responses = [
        _Resp(
            choices=[
                _Choice(
                    _Msg(
                        None,
                        [
                            _ToolCall(
                                id="call_1",
                                function=_Func(
                                    name="get_price_history",
                                    arguments='{"ticker":"VCB","days":30}',
                                ),
                            )
                        ],
                    ),
                    "tool_calls",
                )
            ],
            usage=_Usage(prompt_tokens=50, completion_tokens=20, total_tokens=70),
        )
    ]
    client = OpenAIClient()
    result = client.chat(model="gpt-4o-mini", messages=[], tools=[{"x": 1}])
    assert len(result.tool_calls) == 1
    tc = result.tool_calls[0]
    assert tc["name"] == "get_price_history"
    assert tc["arguments"] == {"ticker": "VCB", "days": 30}


def test_chat_records_usage_to_metrics(monkeypatch) -> None:
    """Every chat() call must increment metrics — PKG-10 aggregates these
    for cost reporting."""
    fake = _patch(monkeypatch)
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-test")
    fake.chat.completions.responses = [_ok_resp(cached=80)]
    metrics.reset()
    client = OpenAIClient()
    client.chat(model="gpt-4o-mini", messages=[])
    snap = metrics.get_snapshot()
    assert snap["llm_calls"] == 1
    assert snap["by_model"]["gpt-4o-mini"] == 1
    assert snap["total_prompt_tokens"] == 100
    assert snap["total_cached_tokens"] == 80


def test_chat_retries_on_rate_limit_then_succeeds(monkeypatch) -> None:
    """First call raises RateLimitError, second succeeds — verifies retry path
    so production traffic survives bursty 429s."""
    fake = _patch(monkeypatch)
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr("time.sleep", lambda _: None)  # don't actually sleep
    _req = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    _resp = httpx.Response(429, request=_req)
    fake.chat.completions.exceptions = [
        RateLimitError("rate limit", response=_resp, body=None)
    ]
    fake.chat.completions.responses = [_ok_resp()]
    client = OpenAIClient()
    result = client.chat(model="gpt-4o-mini", messages=[])
    assert result.text == "hello"
    # one failure + one success = 1 entry in calls (failure didn't reach .calls
    # because it raised inside create); responses queue exhausted means success
    assert len(fake.chat.completions.responses) == 0
