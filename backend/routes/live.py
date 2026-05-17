"""POST /live/run — SSE stream of multi-agent graph execution (PKG-12).

Async handler. ``astream_events(version="v2")`` drives per-node start +
end events; filter by ROLE_NAMES; map to PRD §10 event shape. Single
overall 60s wallclock cap (PKG-8 reality > the 30s/agent Issue #13 target).

Scope-reduced: token-level events deferred to post-MVP. Frontend (PKG-16)
renders 4 event types: agent_start, agent_complete, decision, error.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from backend.live_data import load_live_inputs
from backend.sse import extract_decision, sse_event
from src import config
from src.llm.client import OpenAIClient
from src.llm.multi_agent.agent import _DEFAULT_MODELS, _DEFAULT_TIMEOUT_S
from src.llm.multi_agent.graph import build_app
from src.llm.multi_agent.state import ROLE_NAMES, make_initial_state
from src.llm.tools import LookaheadSafeTools

log = logging.getLogger(__name__)
router = APIRouter()

# Per-role output field for the agent_complete summary. Researchers append
# to debate_exchanges instead of a single field — handled in _summarize.
_ROLE_OUTPUT_KEY: dict[str, str] = {
    "technical_analyst": "technical_brief",
    "news_sentiment_analyst": "news_sentiment_brief",
    "fundamental_analyst": "fundamental_brief",
    "trader": "trader_proposal",
    "risk_manager": "risk_review",
    "portfolio_manager": "portfolio_manager_output",
}


class LiveRunRequest(BaseModel):
    tickers: list[str] | None = None
    use_realtime: bool = False
    debate_rounds: int = 2


def _summarize(role: str, output: dict) -> str:
    """Pull the role's primary brief from its state-update dict."""
    key = _ROLE_OUTPUT_KEY.get(role)
    if key is not None:
        return str(output.get(key, "") or "").strip()
    # Researchers append to debate_exchanges (Annotated list); the per-node
    # update dict contains only the items added by this node. The exchange
    # uses key "text" (see src/llm/multi_agent/nodes/researchers.py); also
    # check "content" so a future schema change degrades gracefully.
    ex = output.get("debate_exchanges") or []
    if ex:
        item = ex[-1]
        return str(item.get("text") or item.get("content") or "").strip()
    return ""


async def _stream_graph_events(req: LiveRunRequest) -> AsyncIterator[dict]:
    """Drive the LangGraph + yield SSE-shaped dicts."""
    md, news, info = load_live_inputs(
        tickers=req.tickers or list(config.TICKERS),
        use_realtime=req.use_realtime,
    )
    initial = make_initial_state(
        market_data=md,
        news_data=news,
        info=info,
        client=OpenAIClient(),
        models=_DEFAULT_MODELS,
        tools=LookaheadSafeTools(md, news, md.dates[-1]),
        debate_rounds_max=req.debate_rounds,
    )
    app = build_app()
    final_pm_output: str = ""
    role_set = set(ROLE_NAMES)
    async for ev in app.astream_events(initial, version="v2"):
        et = ev.get("event")
        name = ev.get("name")
        if name not in role_set:
            continue
        if et == "on_chain_start":
            yield sse_event("agent_start", {"role": name})
        elif et == "on_chain_end":
            output = (ev.get("data") or {}).get("output") or {}
            summary = _summarize(name, output)
            yield sse_event(
                "agent_complete",
                {"role": name, "summary": summary[:500]},
            )
            if name == "portfolio_manager":
                final_pm_output = output.get("portfolio_manager_output", "") or ""
    weights = extract_decision(final_pm_output)
    if weights is not None:
        yield sse_event(
            "decision",
            {"weights": weights, "rationale": final_pm_output[:1000]},
        )


async def _with_timeout(aiter: AsyncIterator[dict], timeout: float) -> AsyncIterator[dict]:
    """Yield from an async iterator under a single overall wallclock cap."""
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    ait = aiter.__aiter__()
    while True:
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise TimeoutError(f"timeout {timeout}s exceeded")
        try:
            item = await asyncio.wait_for(ait.__anext__(), timeout=remaining)
        except StopAsyncIteration:
            return
        yield item


@router.post("/live/run")
async def live_run(req: LiveRunRequest, request: Request) -> EventSourceResponse:
    async def event_gen() -> AsyncIterator[dict]:
        try:
            async for event in _with_timeout(_stream_graph_events(req), timeout=_DEFAULT_TIMEOUT_S):
                if await request.is_disconnected():
                    log.info("client disconnected mid-stream; aborting")
                    return
                yield event
        except TimeoutError:
            log.warning("live_run timeout %.1fs", _DEFAULT_TIMEOUT_S)
            yield sse_event("error", {"message": f"timeout {_DEFAULT_TIMEOUT_S}s exceeded"})
        except Exception as e:  # noqa: BLE001 — surface any upstream failure as a single error event
            log.exception("live_run failed")
            yield sse_event("error", {"message": str(e)[:300]})

    return EventSourceResponse(event_gen(), ping=15)


@router.get("/live/run")
async def live_run_get(request: Request) -> EventSourceResponse:
    # PKG-16: GET form for browser EventSource (which is GET-only). Reuses
    # the POST handler with default LiveRunRequest. POST endpoint retained
    # for PKG-S future custom-tickers UI.
    return await live_run(LiveRunRequest(), request)
