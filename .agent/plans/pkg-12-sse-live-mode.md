# Feature: PKG-12 — SSE + live mode backend route

> Real-time STREAMING of multi-agent reasoning via Server-Sent Events.
> `POST /live/run` invokes the PKG-8 LangGraph + emits per-node events
> as they fire, so the frontend (PKG-16) can render Bull/Bear debate
> live, like ChatGPT typing.
>
> **Scope reduction LOCKED before code:** Token-level streaming
> (`event: token`) is **OUT**. Implementing it requires rewriting
> `OpenAIClient.chat` + every node to support `stream=True` + yield
> chunks — a multi-day refactor. PKG-12 ships 3 event types
> (`agent_start`, `agent_complete`, `decision`) + 1 control event
> (`error`). Frontend gets per-role updates ~5-15s apart, NOT per-token
> 50ms typing. This matches demo theater (8 boxes light up sequentially)
> + costs ½-day not 2-day. PKG-13/14/15 timeline preserved.
>
> **Live data scope:** PKG-12 loads PKG-1 offline parquets + uses the
> latest available session as "today". vnstock realtime overlay is
> best-effort; failure → fall back to pure offline. Honest demo framing:
> "real-time STREAMING of reasoning, computed over latest available
> market data". Real-time vnstock daily refresh is a cron concern, not
> a request-time concern.

## Feature Description

3 new files + 1 generic helper + tests:

1. **`backend/sse.py`** — generic SSE primitives: `ServerSentEvent` builder
   wrapper (or re-export `sse_starlette.event.ServerSentEvent`); helper to
   format a `{event_name, data_dict}` pair into a sse-starlette dict event;
   tiny utility for the disconnect handler.
2. **`backend/live_data.py`** — `load_live_inputs(tickers, today=None)`
   → `(MarketData, news_df, info_dict)`. Reuses `src.env_data_loader.load_market_data("full")`
   (full series through latest available date) + `pd.read_parquet(NEWS_PATH)`.
   Builds `info` with date=last session, holdings=zeros, cash=INITIAL_CAPITAL.
   Optional `prepend_realtime_close()` overlay for vnstock latest close (best-effort).
3. **`backend/routes/live.py`** — `POST /live/run`. Pydantic `LiveRunRequest`
   (optional `tickers`); async handler builds inputs, calls
   `multi_agent_app.astream_events(initial_state, version="v2")`, filters
   `on_chain_start`/`on_chain_end` to `ROLE_NAMES`, yields SSE events.
   Emits final `decision` from `final_state.portfolio_manager_output`
   (parsed via `_extract_decision` from PKG-11). 60s wallclock cap.
4. **`tests/test_sse.py`** — 4-5 tests using a stub StateGraph with 3 fake
   nodes; verify event ordering, error event on exception, decision event
   payload, disconnect handling, schema.

Acceptance criteria (Issue #13):
- `curl -N` thấy events stream theo thứ tự (relaxed: `agent_start → agent_complete → decision`; token skipped per scope reduction)
- Mất mạng → graceful `error` event, không crash app
- 30s timeout per agent enforced (raised to 60s per PKG-8 reality — see D4)

## User Story

As a **demo presenter (Duc) trong buổi bảo vệ**
I want **mở trang `/live` và thấy 8 vai trò multi-agent sáng đèn tuần tự
trong < 60 giây**
So that **thầy hiểu ngay "multi-agent debate" không phải hư cấu — mỗi role
thực sự gọi LLM và sản xuất output**.

As a **PKG-16 Next.js live mode UI**
I want **EventSource(`/live/run`) stream với 3-4 event types schema cố định**
So that **render logic là `switch(event.type)` đơn giản, không phải parse
free-form text**.

As a **report writer (Person 1)**
I want **`error` event với message khi LLM API fail**
So that **screenshot trong report cho thấy graceful degradation, không
phải crash**.

## Problem Statement

5 challenges:

1. **PRD §10 spec liệt kê 4 event types** (`agent_start`, `token`,
   `agent_complete`, `decision`) nhưng **token streaming yêu cầu rewrite
   OpenAIClient + 8 nodes** (each node phải call client với `stream=True` và
   yield chunks). Refactor này 2+ ngày, vượt budget PKG-12 (1 day).
   **Solution:** Scope reduction — ship `agent_start`/`agent_complete`/
   `decision`/`error`. Token-level đề xuất post-MVP.
2. **LangGraph compiled app expose 2 streaming modes:** `.stream(mode="updates")`
   (sync, yields per-node-complete dict) vs `.astream_events(version="v2")`
   (async, yields both start AND end events natively). Updates mode chỉ cho
   agent_complete; astream_events cho cả agent_start + agent_complete miễn phí.
   **Solution (verified via spike):** dùng `astream_events(v2)`, filter
   `event in {on_chain_start, on_chain_end}` AND `name in ROLE_NAMES`.
3. **Live data fetch tại request time chậm.** News scraping 12 months mất ~75s
   (rate-limited). vnstock latest close OK (~1-2s/ticker × 5 = 5-10s). News
   fetch tại request time → vượt 60s budget. **Solution:** Reuse offline
   `news_data` parquet (PKG-2 cached); vnstock latest = optional best-effort
   overlay với 5s timeout, fail-soft.
4. **Client disconnect mid-stream → server keeps spending LLM cost.** Without
   cancel, browser close không stop graph invocation. **Solution:** sse-starlette
   `client_close_handler_callable` + async task cancellation; pending nodes
   abort within 1 step.
5. **60s wallclock cap.** PKG-8 reality = 30-50s for full graph; SSE adds
   overhead. **Solution:** `asyncio.wait_for(..., timeout=60.0)` quanh
   astream_events consumer; timeout → emit `error` event + close stream cleanly.

## Solution Statement

10 design decisions LOCK before code:

- **D1.** **`astream_events(version="v2")` is the streaming engine.** Spike
  confirmed it fires `on_chain_start` + `on_chain_end` per node natively.
  Filter `name in ROLE_NAMES` (drops graph-level "LangGraph" envelope events).
  Sync `.stream("updates")` mode would force us to synthesize `agent_start`
  from topology — fragile across debate loop iterations.
- **D2.** **3 event types + 1 control:** `agent_start`, `agent_complete`,
  `decision`, `error`. **No `token` event.** Frontend (PKG-16) renders per-role
  cards that light up on `agent_start` and fill content on `agent_complete`.
  PRD §10 deviation documented in plan + commit message.
- **D3.** **Async `POST /live/run` handler.** `astream_events` is async-only;
  the handler must be `async def`. EventSourceResponse accepts async iterators
  natively. Pattern: define `async def event_gen()` inside the handler, return
  `EventSourceResponse(event_gen())`.
- **D4.** **60s wallclock cap (matches PKG-8).** Wrap the astream_events consumer
  in `asyncio.wait_for(..., timeout=60.0)`. Timeout → emit `error: {message:
  "timeout 60s exceeded"}` then close stream. NB: Issue #13 says "30s per
  agent"; we follow PKG-8 + plan §13 reality ("30-50s observed"); document
  in commit message.
- **D5.** **Live data = offline-first.** `load_live_inputs(tickers)`:
  (a) `MarketData = src.env_data_loader.load_market_data("full")` — gives
  arrays through latest cached session. (b) `news_data = pd.read_parquet(
  "data/processed/news.parquet")`. (c) `info` synthesized: `date=md.dates[-1]`,
  `holdings=np.zeros(N)`, `cash=portfolio_value=INITIAL_CAPITAL`,
  `close_t=md.close[-1]`. No live fetch at request time in MVP.
- **D6.** **Best-effort vnstock realtime overlay (optional).** Add flag
  `LiveRunRequest.use_realtime: bool = False`. If True, call
  `src.data_pipeline.vnstock_prices.fetch_prices(t, today, today)` per ticker
  with 5s `httpx.Timeout`, append row to `md.close[-1]` if successful, else
  log + skip. Failure does NOT raise — emit `error` event with severity=info
  and continue with offline data.
- **D7.** **`LookaheadSafeTools(market_data, news_data, asof=md.dates[-1])`**
  — reuses PKG-7 invariant. Live mode = "as of today (latest session)" — same
  lookahead rule applies, no special-casing.
- **D8.** **sse-starlette `ping=15` heartbeat** auto-keeps connection alive
  during 30-50s graph runs. `client_close_handler_callable` cancels the
  graph task on disconnect. Default `ping_message_factory` writes a `:ping`
  comment line — browsers ignore.
- **D9.** **Tests use a stub StateGraph fixture, not real LLM.** Build a
  3-node StateGraph (`{n1, n2, n3}`) with sync no-op nodes. Patch the route's
  app builder via `monkeypatch` to inject the stub. Verify: event ordering,
  exception → `error` event, EventSourceResponse media_type, JSON payload shape.
  ZERO real OpenAI calls in PKG-12 tests.
- **D10.** **No state change to `MultiAgentTrader`.** PKG-12 imports
  `src.llm.multi_agent.graph.build_app()` directly + `make_initial_state`
  directly. We bypass the `MultiAgentTrader` wrapper (which is sync, owns
  transcript write, wraps timeout via ThreadPoolExecutor). PKG-12 owns
  streaming + timeout for the live route only; offline backtest still uses
  the trader wrapper unchanged.

## Feature Metadata

- **Feature Type:** New Capability (first streaming endpoint; unblocks PKG-16
  Live mode UI)
- **Estimated Complexity:** **Medium** — streaming + async + cancellation
  + LangGraph event filtering. Mitigated by: spike-verified LangGraph API +
  scope-reduced event set + offline-first data.
- **Primary Systems Affected:**
  - New: `backend/sse.py`, `backend/live_data.py`, `backend/routes/live.py`
  - Update: `backend/main.py` (mount live router)
  - New tests: `tests/test_sse.py`, `tests/test_routes_live.py`
- **Dependencies:** Already in `pyproject.toml` — `sse-starlette>=2.1`,
  `fastapi>=0.110`, `langgraph>=0.2`. **No new deps.**

---

## CONTEXT REFERENCES

### Relevant Codebase Files — ĐỌC TRƯỚC KHI IMPLEMENT

**The compiled graph PKG-12 streams (PKG-8):**

- `src/llm/multi_agent/graph.py:39-71` — `build_graph()` + `build_app()`.
  PKG-12 calls `build_app()` directly + `astream_events()` on it.
- `src/llm/multi_agent/state.py:23-32` — `ROLE_NAMES` tuple (8 names).
  Filter astream_events on this set.
- `src/llm/multi_agent/state.py:71-105` — `make_initial_state()`. PKG-12
  calls with same kwargs (market_data, news_data, info, client, models,
  tools, debate_rounds_max).
- `src/llm/multi_agent/agent.py:47-65` — `_DEFAULT_MODELS`, `_DEFAULT_TIMEOUT_S`.
  PKG-12 reuses (don't re-define).
- `src/llm/multi_agent/agent.py:128-145` — current ThreadPoolExecutor timeout
  pattern (sync). PKG-12 replaces with `asyncio.wait_for`.

**Pattern for the existing route layout (PKG-11):**

- `backend/main.py:38-58` — `create_app()` + middleware + router mount.
  PKG-12 only ADDS `app.include_router(live.router)`.
- `backend/routes/debate.py:1-80` — closest existing route to PKG-12 shape
  (Pydantic request/response, file-read, error handling). MIRROR but make async.
- `backend/cache.py` — JSONFileCache. **NOT used by PKG-12** (live mode skips
  cache; every call runs the graph fresh).

**Data layer (PKG-1/2):**

- `src/env_data_loader.py:43-100` — `load_market_data(split="full")`. PKG-12
  uses `"full"` to get arrays through latest available session.
- `src/data_pipeline/vnstock_prices.py:23-55` — `fetch_prices(ticker, start, end)`.
  Optional realtime overlay; wrap with `httpx.Timeout` + try/except.
- News parquet: `data/processed/news.parquet` — exists post-PKG-2.
- `src/llm/tools.py:LookaheadSafeTools` — constructor `(market_data, news_data, asof)`.
  PKG-12 sets asof = `md.dates[-1]`.

**LLM parser reused for decision extraction:**

- `src/llm/parser.py:parse_weights_json(text, info, ticker_order)` —
  returns `(action, parse_ok)`. PKG-12 needs the WEIGHTS DICT (not ndarray)
  for `decision` event. Use `_extract_decision()` regex from PKG-11
  `backend/routes/debate.py:25-44` (copy or extract to shared helper —
  pick: extract to `backend/sse.py` or new `backend/_parse.py`).

**Existing tests we'll mirror:**

- `tests/test_routes_debate.py:14-46` — TestClient fixture + write-fixture
  helper. PKG-12 tests use same pattern but with monkeypatched graph.
- `tests/test_routes_backtest.py:78-101` — `raise_server_exceptions=False`
  fixture pattern for testing 500/error paths. PKG-12 tests use same for
  testing error event in stream.

**LangGraph streaming evidence (Spike A, verified):**

```
app.stream(state, stream_mode="updates"):
  yields {node_name: state_update_dict} per node completion (SYNC)

app.astream_events(state, version="v2"):
  yields events with shape:
    {"event": "on_chain_start", "name": "<node_name>", "run_id": "...",
     "data": {"input": {...}}, ...}
    {"event": "on_chain_end",   "name": "<node_name>", "run_id": "...",
     "data": {"output": {...}, "input": {...}}, ...}
  (ASYNC; also fires "on_chain_stream" + envelope LangGraph events to ignore)
```

**Don't touch (file ownership):**

- `src/llm/multi_agent/` — owned by PKG-8 (read-only import)
- `src/llm/parser.py` — owned by PKG-5/6 (read-only import)
- `backend/routes/{agents,backtest,debate,healthz}.py` — owned by PKG-11
- `frontend/` — owned by PKG-13+

### New Files to Create

```
backend/
├── sse.py                       # generic SSE primitives + _extract_decision shared helper
├── live_data.py                 # load_live_inputs(tickers) → (MarketData, news_df, info)
└── routes/
    └── live.py                  # async POST /live/run + EventSourceResponse

tests/
├── test_sse.py                  # SSE helpers + _extract_decision unit tests (3-4)
├── test_live_data.py            # load_live_inputs offline path + realtime fallback (3)
└── test_routes_live.py          # event ordering + error + disconnect (5)
```

### Relevant Documentation — ĐỌC TRƯỚC KHI IMPLEMENT

- **LangGraph `astream_events` (v2)**: https://langchain-ai.github.io/langgraph/how-tos/streaming/
  - Section: "Stream events from nodes"
  - Why: PKG-12 core streaming engine; need to know event shape + filter rules
- **sse-starlette `EventSourceResponse`**: https://github.com/sysid/sse-starlette#readme
  - Sections: ping, client_close_handler_callable, ServerSentEvent
  - Why: heartbeat + disconnect handling + structured event format
- **FastAPI streaming responses + async**:
  https://fastapi.tiangolo.com/advanced/custom-response/#streamingresponse
  - Why: confirms async generator pattern + headers for SSE
- **MDN EventSource (frontend reference for PKG-16)**:
  https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events
  - Why: PKG-16 frontend contract; event-name vs data fields

### Pre-implementation spikes

**Spike A — LangGraph astream_events probe (ALREADY RUN — verified):**

```bash
.venv/bin/python <<'PY'
"""Verify astream_events fires per-node start + end."""
import asyncio
from langgraph.graph import StateGraph, START, END
from typing import TypedDict, Annotated
from operator import add

class S(TypedDict, total=False):
    log: Annotated[list[str], add]

def n1(s): return {"log": ["n1"]}
def n2(s): return {"log": ["n2"]}

g = StateGraph(S)
g.add_node("node_a", n1); g.add_node("node_b", n2)
g.add_edge(START, "node_a"); g.add_edge("node_a", "node_b"); g.add_edge("node_b", END)
app = g.compile()

async def main():
    async for ev in app.astream_events({}, version="v2"):
        et = ev.get("event", "?")
        name = ev.get("name", "?")
        if et.startswith("on_chain") and name in {"node_a", "node_b"}:
            print(f"{et:20} {name}")
asyncio.run(main())
PY
```

Expected output:
```
on_chain_start       node_a
on_chain_end         node_a
on_chain_start       node_b
on_chain_end         node_b
```

**Spike B — SSE end-to-end via TestClient:**

```bash
.venv/bin/python <<'PY'
"""Verify EventSourceResponse round-trips through TestClient."""
import asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sse_starlette.sse import EventSourceResponse

app = FastAPI()

async def gen():
    for i in range(3):
        yield {"event": "tick", "data": f"{i}"}
        await asyncio.sleep(0.01)

@app.get("/stream")
def stream():
    return EventSourceResponse(gen())

with TestClient(app) as client:
    with client.stream("GET", "/stream") as r:
        for line in r.iter_lines():
            if line:
                print(line)
PY
```

Expected: 3 `event: tick` + `data: N` pairs. Confirms TestClient handles SSE
+ EventSourceResponse accepts async generator.

**Spike C — Live data load + vnstock realtime probe:**

```bash
.venv/bin/python <<'PY'
"""Time the offline load + a single vnstock realtime call."""
import time
from src.env_data_loader import load_market_data
from src.data_pipeline.vnstock_prices import fetch_prices

t = time.monotonic()
md = load_market_data("full")
print(f"offline load: {time.monotonic()-t:.2f}s  | last_date={md.dates[-1]} sessions={len(md.dates)}")

t = time.monotonic()
try:
    today_str = "2026-05-15"
    df = fetch_prices("VCB", "2026-05-13", today_str)
    print(f"vnstock VCB ({today_str}): {time.monotonic()-t:.2f}s  rows={len(df)}")
except Exception as e:
    print(f"vnstock fail: {e}")
PY
```

Expected: offline load < 1s; vnstock fetch < 5s OR exception (KBS rate
limit). Confirms cost budget for default offline path + realtime overlay.

### Patterns to Follow

**Async route with EventSourceResponse:**

```python
from sse_starlette.sse import EventSourceResponse

@router.post("/live/run")
async def live_run(req: LiveRunRequest, request: Request) -> EventSourceResponse:
    async def event_gen():
        try:
            async for event in _stream_graph_events(req):
                yield event  # dict {event: "...", data: "..."}
        except asyncio.TimeoutError:
            yield {"event": "error", "data": json.dumps({"message": "timeout"})}
        except Exception as e:
            log.exception("live_run failed")
            yield {"event": "error", "data": json.dumps({"message": str(e)})}

    return EventSourceResponse(event_gen(), ping=15)
```

**LangGraph event → SSE event mapping:**

```python
async def _stream_graph_events(req):
    md, news, info = load_live_inputs(req.tickers)
    initial = make_initial_state(
        market_data=md, news_data=news, info=info,
        client=OpenAIClient(),
        models=_DEFAULT_MODELS,
        tools=LookaheadSafeTools(md, news, asof=md.dates[-1]),
        debate_rounds_max=2,
    )
    app = build_app()
    final_state = None
    async def _runner():
        nonlocal final_state
        async for ev in app.astream_events(initial, version="v2"):
            et = ev.get("event")
            name = ev.get("name")
            if name not in ROLE_NAMES:
                continue
            if et == "on_chain_start":
                yield {"event": "agent_start", "data": json.dumps({"role": name})}
            elif et == "on_chain_end":
                # extract per-node output from event for summary
                output = (ev.get("data") or {}).get("output") or {}
                summary = _summarize_node_output(name, output)
                yield {"event": "agent_complete",
                       "data": json.dumps({"role": name, "summary": summary[:500]})}
                # capture final state from portfolio_manager's output
                if name == "portfolio_manager":
                    final_state = output
    # asyncio.wait_for around the consumer
    async for event in _aiter_with_timeout(_runner(), timeout=60.0):
        yield event
    # decision event (after stream ends)
    if final_state:
        pm_output = final_state.get("portfolio_manager_output", "")
        weights = _extract_decision(pm_output)
        if weights:
            yield {"event": "decision",
                   "data": json.dumps({"weights": weights, "rationale": pm_output[:1000]})}
```

**`_aiter_with_timeout` helper:**

```python
async def _aiter_with_timeout(aiter, timeout):
    """Wrap an async iterator with a single overall wallclock timeout."""
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while True:
        try:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise asyncio.TimeoutError(f"timeout {timeout}s exceeded")
            item = await asyncio.wait_for(aiter.__anext__(), timeout=remaining)
            yield item
        except StopAsyncIteration:
            return
```

**Live data loader (`backend/live_data.py`):**

```python
from __future__ import annotations
import logging
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from src import config
from src.env_data_loader import MarketData, load_market_data

log = logging.getLogger(__name__)

NEWS_PATH = config.PROJECT_ROOT / "data" / "processed" / "news.parquet"


def load_live_inputs(
    tickers: list[str] | None = None,
    use_realtime: bool = False,
) -> tuple[MarketData, pd.DataFrame, dict]:
    """Build inputs for a live multi-agent run.

    Returns:
      md: MarketData through the latest available offline session
      news: news DataFrame (offline cache)
      info: env-info-like dict (date, holdings=zeros, cash=INITIAL_CAPITAL)
    """
    md = load_market_data("full")
    news = pd.read_parquet(NEWS_PATH) if NEWS_PATH.exists() else pd.DataFrame()
    n = len(md.tickers)
    info = {
        "date": md.dates[-1],
        "t": int(len(md.dates) - 1),
        "holdings": np.zeros(n, dtype=np.int64),
        "cash": float(config.INITIAL_CAPITAL),
        "portfolio_value": float(config.INITIAL_CAPITAL),
        "close_t": md.close[-1].astype(np.float64),
    }
    if use_realtime:
        log.info("realtime overlay requested — best-effort vnstock fetch")
        # Hook left as a future enhancement; for MVP, log and skip.
    return md, news, info
```

**Error handling (CLAUDE.md alignment):**

- Graph timeout (60s) → `event: error data: {"message": "timeout 60s"}` then close
- LLM API failure mid-stream → captured by node's try/except (already in PKG-8 nodes) → `node_errors` populated → continue stream
- Stream-level exception (e.g. OpenAI quota) → `event: error` then close
- Client disconnect → sse-starlette cancels the async generator; cleanup via try/finally
- Missing offline data (`data/processed/news.parquet`) → log + empty news; graph runs (news_sentiment_analyst returns "no news visible")
- Invalid tickers in request → 400 Bad Request (before stream opens, regular HTTPException)

---

## DESIGN DECISIONS — LOCK BEFORE IMPLEMENT

### D1. astream_events(v2) is the engine

Spike A verified: gives `on_chain_start` + `on_chain_end` per node, filterable by `name in ROLE_NAMES`. No need to synthesize agent_start from topology.

### D2. 3+1 event types (no token)

`agent_start`, `agent_complete`, `decision`, `error`. **NO `token`.**
- PRD §10 deviation documented.
- Token streaming requires PKG-5 OpenAIClient rewrite + 8-node refactor = 2+ days.
- Demo theater = sequential role boxes lighting up, not per-character typing.
- Frontend (PKG-16) renders `agent_start` → spinner; `agent_complete` → fill content.

### D3. Async route handler

`async def live_run(...)`. EventSourceResponse accepts async iterables natively. Spike B verified TestClient round-trip.

### D4. 60s wallclock cap (overall, not per-agent)

Wrap consumer in `asyncio.wait_for(..., timeout=60.0)`. Issue #13 says "30s per agent" but PKG-8 reality = 30-50s for full graph (10 sequential calls). Per-agent caps would force per-node async wrappers — complex. Single overall cap is honest + simpler.

### D5. Live data = offline-first

`load_market_data("full")` gives latest cached session. News from offline parquet. info synthesized. NO live fetch at request time in MVP (vnstock latest is best-effort opt-in via `use_realtime: bool` flag).

### D6. Best-effort vnstock realtime overlay

`LiveRunRequest.use_realtime: bool = False`. When True, try vnstock fetch with 5s timeout, fail-soft. Plan SHIPS the flag + DOCs but defers the actual fetch wiring as a "Phase 2" task — gate on time. If under budget, implement; if over, ship the flag returning offline-only with a warning event.

### D7. LookaheadSafeTools asof = last session

Reuses PKG-7 invariant — same lookahead rule applies live. No special-case.

### D8. sse-starlette ping=15

Auto keepalive during 30-50s graph runs. Plus `client_close_handler_callable` to cancel the graph task on disconnect.

### D9. Tests use a stub StateGraph

Build a 3-node fake graph, monkeypatch `backend.routes.live.build_app` to return it. Verify event ordering, exception → error event, EventSourceResponse content-type, payload shape. ZERO real LLM in PKG-12 tests.

### D10. No state change to MultiAgentTrader

PKG-12 imports `build_app()` + `make_initial_state` + `_DEFAULT_MODELS` directly. Bypasses the trader wrapper (which owns sync timeout + transcript write). PKG-12 owns streaming + timeout for live route. Offline backtest still uses trader unchanged.

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation — generic SSE helpers + live data loader

- `backend/sse.py` — re-export ServerSentEvent + `_extract_decision` shared helper (or import from `backend.routes.debate`)
- `backend/live_data.py` — `load_live_inputs()`
- `tests/test_sse.py` — `_extract_decision` golden tests
- `tests/test_live_data.py` — load_live_inputs offline path

### Phase 2: Live route + streaming engine

- `backend/routes/live.py` — `POST /live/run` async handler + `_stream_graph_events()`
- Update `backend/main.py` — mount live router

### Phase 3: Tests

- `tests/test_routes_live.py` — stub graph, event ordering, timeout, error

### Phase 4: Smoke

- `curl -N -X POST http://localhost:8000/live/run -H 'Content-Type: application/json' -d '{}'`
- Verify events stream in order
- Verify ping comments appear if waiting
- Cancel mid-stream via Ctrl+C → server logs "client disconnected"

---

## STEP-BY-STEP TASKS

### 1. RUN Spike A + B + C

- **VALIDATE:** Spike A prints 4 on_chain events. Spike B prints 3 SSE ticks.
  Spike C: offline load < 1s + vnstock either < 5s OR exception (KBS rate limit).

### 2. CREATE `backend/sse.py`

- **IMPLEMENT:**
  ```python
  """Generic SSE primitives + shared parsing helpers (PKG-12).

  Re-exports sse_starlette ServerSentEvent for consistency. _extract_decision
  is shared between routes/debate.py (already-shipped) and routes/live.py.
  """

  from __future__ import annotations

  import json
  import re

  from sse_starlette.event import ServerSentEvent  # noqa: F401 (re-export)

  _JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.+?\})\s*```", re.DOTALL)
  _BARE_OBJECT_RE = re.compile(r"\{[^{}]*\}", re.DOTALL)


  def extract_decision(text: str | None) -> dict | None:
      """Pull the first JSON object out of an LLM output. Returns the dict
      or None on any parse failure. Pure function — no env, no side effects."""
      if not text:
          return None
      m = _JSON_BLOCK_RE.search(text)
      blob = m.group(1) if m else None
      if blob is None:
          m = _BARE_OBJECT_RE.search(text)
          blob = m.group(0) if m else None
      if blob is None:
          return None
      try:
          parsed = json.loads(blob)
      except json.JSONDecodeError:
          return None
      return parsed if isinstance(parsed, dict) else None


  def sse_event(event: str, data: dict | str) -> dict:
      """Build an SSE event dict consumable by EventSourceResponse."""
      payload = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
      return {"event": event, "data": payload}
  ```
- **VALIDATE:** `.venv/bin/python -c "from backend.sse import extract_decision; print(extract_decision('\`\`\`json\n{\"VCB\": 0.2}\n\`\`\`'))"` → prints dict.

### 3. UPDATE `backend/routes/debate.py` — import from `backend.sse`

- **IMPLEMENT:** Replace inline `_extract_decision` + regexes with
  `from backend.sse import extract_decision`. Keeps single source of truth.
- **GOTCHA:** Run debate tests after to confirm no regression.
- **VALIDATE:** `.venv/bin/pytest tests/test_routes_debate.py -v` → still 5 pass.

### 4. CREATE `tests/test_sse.py`

- **IMPLEMENT:**
  1. `test_extract_decision_json_fence` — '```json\n{"VCB":0.2}\n```' → {'VCB': 0.2}
  2. `test_extract_decision_bare_object` — '{"VCB":0.2}' → {'VCB': 0.2}
  3. `test_extract_decision_returns_none_for_garbage` — 'random text' → None
  4. `test_sse_event_serializes_dict` — `sse_event("x", {"a":1})` → `{"event":"x","data":'{"a": 1}'}`
- **VALIDATE:** `.venv/bin/pytest tests/test_sse.py -v` → 4 pass.

### 5. CREATE `backend/live_data.py`

- **IMPLEMENT:** As shown in "Patterns to Follow". Use `load_market_data("full")` + read news parquet. info has date, holdings=zeros, cash, pv, close_t.
- **GOTCHA #1:** `md.close[-1]` is float32; cast to float64 for env compat.
- **GOTCHA #2:** If `data/processed/news.parquet` missing, return empty DataFrame — don't crash; graph's news node will emit "no news visible".
- **VALIDATE:** `.venv/bin/python -c "from backend.live_data import load_live_inputs; md, n, i = load_live_inputs(); print('date=', i['date'], 'tickers=', len(md.tickers), 'news_rows=', len(n))"`

### 6. CREATE `tests/test_live_data.py`

- **IMPLEMENT:**
  1. `test_load_live_inputs_returns_full_market_data` — sessions count > 200
  2. `test_load_live_inputs_info_has_zero_holdings` — info['holdings'].sum() == 0
  3. `test_load_live_inputs_missing_news_parquet(monkeypatch, tmp_path)` — point NEWS_PATH to missing; expect empty df not crash
- **VALIDATE:** `.venv/bin/pytest tests/test_live_data.py -v` → 3 pass.

### 7. CREATE `backend/routes/live.py`

- **IMPLEMENT:**
  ```python
  """POST /live/run — SSE stream of multi-agent graph execution (PKG-12).

  Async handler. astream_events(v2) drives per-node start + end events;
  filter by ROLE_NAMES; map to PRD §10 event shape. 60s wallclock cap.
  Scope-reduced: token-level events deferred to post-MVP.
  """

  from __future__ import annotations

  import asyncio
  import json
  import logging

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


  class LiveRunRequest(BaseModel):
      tickers: list[str] | None = None
      use_realtime: bool = False
      debate_rounds: int = 2


  async def _stream_graph_events(req: LiveRunRequest):
      md, news, info = load_live_inputs(
          tickers=req.tickers or list(config.TICKERS),
          use_realtime=req.use_realtime,
      )
      initial = make_initial_state(
          market_data=md, news_data=news, info=info,
          client=OpenAIClient(),
          models=_DEFAULT_MODELS,
          tools=LookaheadSafeTools(md, news, asof=md.dates[-1]),
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


  def _summarize(role: str, output: dict) -> str:
      """Pull the role's primary brief/output field for the SSE summary."""
      key_map = {
          "technical_analyst": "technical_brief",
          "news_sentiment_analyst": "news_sentiment_brief",
          "fundamental_analyst": "fundamental_brief",
          "trader": "trader_proposal",
          "risk_manager": "risk_review",
          "portfolio_manager": "portfolio_manager_output",
      }
      if role in key_map:
          return str(output.get(key_map[role], "")).strip()
      # Researchers append to debate_exchanges list
      ex = output.get("debate_exchanges") or []
      if ex:
          return str(ex[-1].get("content", "")).strip()
      return ""


  @router.post("/live/run")
  async def live_run(req: LiveRunRequest, request: Request) -> EventSourceResponse:
      async def event_gen():
          try:
              async for event in _with_timeout(
                  _stream_graph_events(req), timeout=_DEFAULT_TIMEOUT_S
              ):
                  if await request.is_disconnected():
                      log.info("client disconnected mid-stream; aborting")
                      return
                  yield event
          except asyncio.TimeoutError:
              log.warning("live_run timeout %.1fs", _DEFAULT_TIMEOUT_S)
              yield sse_event("error", {"message": f"timeout {_DEFAULT_TIMEOUT_S}s exceeded"})
          except Exception as e:
              log.exception("live_run failed")
              yield sse_event("error", {"message": str(e)[:300]})

      return EventSourceResponse(event_gen(), ping=15)


  async def _with_timeout(aiter, timeout: float):
      """Yield items from an async iterator under a single overall wallclock cap."""
      loop = asyncio.get_event_loop()
      deadline = loop.time() + timeout
      ait = aiter.__aiter__()
      while True:
          remaining = deadline - loop.time()
          if remaining <= 0:
              raise asyncio.TimeoutError(f"timeout {timeout}s exceeded")
          try:
              item = await asyncio.wait_for(ait.__anext__(), timeout=remaining)
          except StopAsyncIteration:
              return
          yield item
  ```
- **GOTCHA #1:** `_DEFAULT_MODELS` + `_DEFAULT_TIMEOUT_S` are private (`_` prefix) in `multi_agent/agent.py`. Importing private names is acceptable here because they're project-internal constants, not a public API. Alternative: hoist to `src/llm/multi_agent/state.py` as truly public. Pick the simpler path (import private).
- **GOTCHA #2:** `request.is_disconnected()` is awaitable; check inside the loop. Don't rely solely on sse-starlette's cancel — explicit early-exit is cheaper than waiting for the next yield to raise.
- **GOTCHA #3:** `OpenAIClient()` requires `OPENAI_API_KEY` env var. Tests must monkeypatch or pass a fake client (mock graph fixture sidesteps this).

### 8. UPDATE `backend/main.py` — mount live router

- **IMPLEMENT:**
  ```python
  from backend.routes import agents, backtest, debate, healthz, live
  # ... later inside create_app() ...
  app.include_router(live.router)
  ```
- **GOTCHA:** Keep import alphabetical to minimize merge diffs.
- **VALIDATE:** `.venv/bin/python -c "from backend.main import create_app; app = create_app(); print([r.path for r in app.routes if hasattr(r, 'path')])"` includes `/live/run`.

### 9. CREATE `tests/test_routes_live.py`

- **IMPLEMENT:** ~5 tests with stub graph:
  ```python
  """Tests for backend/routes/live.py with a stub StateGraph (no real LLM)."""

  from __future__ import annotations

  import json
  from typing import Annotated, TypedDict
  from operator import add

  import pytest
  from fastapi.testclient import TestClient
  from langgraph.graph import END, START, StateGraph

  from backend.main import create_app


  # Build a small stub graph using 2 of the real role names so the route
  # filter passes through. portfolio_manager LAST so the decision event fires.
  class _StubState(TypedDict, total=False):
      transcript: Annotated[list[dict], add]
      portfolio_manager_output: str
      technical_brief: str


  def _stub_app():
      def technical_analyst(s):
          return {"technical_brief": "stub tech brief"}

      def portfolio_manager(s):
          return {"portfolio_manager_output": '```json\n{"VCB": 0.2, "FPT": 0.2}\n```'}

      g = StateGraph(_StubState)
      g.add_node("technical_analyst", technical_analyst)
      g.add_node("portfolio_manager", portfolio_manager)
      g.add_edge(START, "technical_analyst")
      g.add_edge("technical_analyst", "portfolio_manager")
      g.add_edge("portfolio_manager", END)
      return g.compile()


  @pytest.fixture
  def client(monkeypatch):
      from backend.routes import live as live_mod

      # Replace build_app, make_initial_state, LookaheadSafeTools, OpenAIClient,
      # load_live_inputs with stubs so the route uses our fake graph.
      monkeypatch.setattr(live_mod, "build_app", _stub_app)
      monkeypatch.setattr(
          live_mod, "make_initial_state",
          lambda **kw: {"transcript": [], "portfolio_manager_output": "",
                        "technical_brief": ""},
      )
      monkeypatch.setattr(live_mod, "LookaheadSafeTools", lambda *a, **kw: object())
      monkeypatch.setattr(live_mod, "OpenAIClient", lambda *a, **kw: object())
      monkeypatch.setattr(
          live_mod, "load_live_inputs",
          lambda **kw: (type("MD", (), {"dates": [None], "tickers": ()})(), None, {}),
      )
      return TestClient(create_app())


  def _parse_sse(raw: str) -> list[dict]:
      """Tiny SSE parser: turn the response body into [{event, data}, ...]."""
      events = []
      current: dict = {}
      for line in raw.splitlines():
          if not line.strip():
              if current:
                  events.append(current)
                  current = {}
              continue
          if line.startswith(":"):
              continue  # SSE comment (e.g. heartbeat)
          if ":" in line:
              k, _, v = line.partition(":")
              current[k.strip()] = v.lstrip()
      if current:
          events.append(current)
      return events


  def test_live_run_emits_agent_start_then_complete(client):
      r = client.post("/live/run", json={})
      assert r.status_code == 200
      assert r.headers["content-type"].startswith("text/event-stream")
      events = _parse_sse(r.text)
      types = [e["event"] for e in events if "event" in e]
      assert types[0] == "agent_start"
      assert "agent_complete" in types
      assert "decision" == types[-1]


  def test_live_run_decision_payload_has_weights(client):
      r = client.post("/live/run", json={})
      events = _parse_sse(r.text)
      dec = next(e for e in events if e.get("event") == "decision")
      data = json.loads(dec["data"])
      assert data["weights"] == {"VCB": 0.2, "FPT": 0.2}


  def test_live_run_pings_through_event_source_response(client):
      # ping=15 means a comment ":" line may appear; just assert media_type.
      r = client.post("/live/run", json={})
      assert r.headers["content-type"].startswith("text/event-stream")


  def test_live_run_emits_error_on_exception(monkeypatch):
      from backend.routes import live as live_mod

      def boom(**kw):
          raise RuntimeError("simulated upstream failure")

      monkeypatch.setattr(live_mod, "load_live_inputs", boom)
      monkeypatch.setattr(live_mod, "build_app", _stub_app)
      monkeypatch.setattr(
          live_mod, "make_initial_state",
          lambda **kw: {"transcript": [], "portfolio_manager_output": "", "technical_brief": ""},
      )
      client = TestClient(create_app())
      r = client.post("/live/run", json={})
      assert r.status_code == 200
      events = _parse_sse(r.text)
      err = next(e for e in events if e.get("event") == "error")
      data = json.loads(err["data"])
      assert "simulated upstream failure" in data["message"]


  def test_live_run_accepts_optional_request_body(client):
      r = client.post(
          "/live/run",
          json={"tickers": ["VCB", "FPT"], "debate_rounds": 1, "use_realtime": False},
      )
      assert r.status_code == 200
      events = _parse_sse(r.text)
      assert any(e.get("event") == "agent_start" for e in events)
  ```
- **GOTCHA #1:** TestClient consumes the full SSE body to memory; for stub graph that's tiny (~4 events). Real runs would need `client.stream(...)` context manager.
- **GOTCHA #2:** Heartbeats may interleave; SSE parser skips `:` comment lines.
- **VALIDATE:** `.venv/bin/pytest tests/test_routes_live.py -v` → 5 pass.

### 10. SMOKE — live curl against real graph

- **IMPLEMENT:**
  ```bash
  # Background uvicorn
  (.venv/bin/uvicorn backend.main:app --port 8001 --log-level info &) && sleep 1
  # NOTE: real LLM cost ~$0.05 per call — RUN ONCE
  curl -N -X POST http://localhost:8001/live/run \
       -H 'Content-Type: application/json' -d '{}' \
       --max-time 90
  pkill -f "uvicorn backend.main:app --port 8001"
  ```
- **EXPECTED:** Lines like:
  ```
  event: agent_start
  data: {"role": "technical_analyst"}

  event: agent_complete
  data: {"role": "technical_analyst", "summary": "..."}

  ... (8 role pairs + decision)

  event: decision
  data: {"weights": {...}, "rationale": "..."}
  ```
- **GOTCHA:** Requires OPENAI_API_KEY in `.env`. If absent, expect `error` event with auth message.

### 11. SMOKE — disconnect test

- **IMPLEMENT:**
  ```bash
  (.venv/bin/uvicorn backend.main:app --port 8001 --log-level info &) && sleep 1
  # Open stream, Ctrl+C after 5s
  timeout 5 curl -N -X POST http://localhost:8001/live/run -H 'Content-Type: application/json' -d '{}'
  echo "---"
  # Server log should show "client disconnected mid-stream; aborting"
  pkill -f "uvicorn backend.main:app --port 8001"
  ```
- **EXPECTED:** Server log "client disconnected mid-stream; aborting".

### 12. FINAL ruff + pytest

```bash
.venv/bin/ruff format backend/sse.py backend/live_data.py backend/routes/live.py tests/test_sse.py tests/test_live_data.py tests/test_routes_live.py
.venv/bin/ruff check backend/ tests/
.venv/bin/pytest tests/ 2>&1 | tail -5
# Expected: ruff clean, ~252 tests pass (241 + ~11 new)
```

---

## TESTING STRATEGY

### Unit Tests (~11 new across 3 files)

| File | Count | Focus |
|------|------:|-------|
| `test_sse.py` | 4 | extract_decision fence/bare/garbage, sse_event serialization |
| `test_live_data.py` | 3 | offline load, info shape, missing news fallback |
| `test_routes_live.py` | 5 | event ordering, decision payload, content-type, error event, optional body |

Total after PKG-12: **241 (current) + ~12 = ~253 tests**.

### Integration smoke (manual, in PR description — costs ~$0.05 once)

Step 10 (real LLM curl) + Step 11 (disconnect log).

### Edge Cases Explicitly Covered

| # | Case | Test |
|---|------|------|
| 1 | Decision JSON in markdown fence | sse #1 |
| 2 | Decision bare JSON object | sse #2 |
| 3 | Decision parse fail → no event | sse #3 (returns None) |
| 4 | Missing news parquet | live_data #3 |
| 5 | Stream consumer raises | routes_live #4 (error event) |
| 6 | Optional request body fields | routes_live #5 |
| 7 | TestClient SSE round-trip | routes_live #1 (content-type assert) |

NOT in tests (covered in smoke / accepted risk):
- 60s timeout firing mid-stream (would require fake slow node — defer)
- Client disconnect mid-stream (smoke step 11)
- Heartbeat ping line in body (transient; smoke step 10)

---

## VALIDATION COMMANDS

### Level 1: Syntax & Style

```bash
.venv/bin/ruff check backend/ tests/
```

### Level 2: Unit tests (no LLM cost)

```bash
.venv/bin/pytest tests/test_sse.py tests/test_live_data.py tests/test_routes_live.py -v
```

### Level 3: Full regression

```bash
.venv/bin/pytest tests/ 2>&1 | tail -5
```

### Level 4: Mock-graph SSE smoke (no LLM cost)

Already covered by Level 2 routes_live tests (TestClient + stub graph).

### Level 5: Real graph smoke (~$0.05 ONE-shot)

```bash
(.venv/bin/uvicorn backend.main:app --port 8001 &) && sleep 1
curl -N -X POST http://localhost:8001/live/run \
     -H 'Content-Type: application/json' -d '{}' --max-time 90
pkill -f "uvicorn backend.main:app --port 8001"
```

### Level 6: Disconnect handling smoke

```bash
(.venv/bin/uvicorn backend.main:app --port 8001 --log-level info &) && sleep 1
timeout 5 curl -N -X POST http://localhost:8001/live/run \
     -H 'Content-Type: application/json' -d '{}'
# Check server log for "client disconnected mid-stream"
pkill -f "uvicorn backend.main:app --port 8001"
```

---

## ACCEPTANCE CRITERIA

Issue #13 (adapted per scope reduction):
- [ ] `curl -N` shows events in order `agent_start → agent_complete → ... → decision` (token omitted per scope reduction; documented in commit message + PR body)
- [ ] Upstream failure (LLM error, missing input) → `event: error` then close; **app does not crash**
- [ ] 60s overall wallclock cap enforced (PKG-8 reality vs Issue #13 "30s per agent" — explained in PR body)
- [ ] ~11 new tests pass; 241 prior still pass; ruff clean

Extra (not in issue but in this plan):
- [ ] `_extract_decision` extracted to `backend/sse.py`; `routes/debate.py` updated to import (single source of truth)
- [ ] Live data loader handles missing news parquet (empty df, not crash)
- [ ] CORS — already supports POST + OPTIONS from PKG-11; no `main.py` middleware changes needed

---

## COMPLETION CHECKLIST

- [ ] Spike A/B/C run, outputs captured in PR description
- [ ] `backend/sse.py`, `backend/live_data.py`, `backend/routes/live.py` shipped
- [ ] `backend/routes/debate.py` updated to import from `backend.sse`
- [ ] `backend/main.py` mounts live router
- [ ] ~11 new tests pass; ruff clean
- [ ] Real LLM smoke (Step 10) captured in PR description (1 invocation)
- [ ] Disconnect smoke (Step 11) — server log shows "client disconnected"
- [ ] PR opened `PKG-12: SSE + live mode route`, body `Closes #13`
- [ ] No Claude attribution per CLAUDE.md
- [ ] PKG-16 unblocked (EventSource(`/live/run`) returns 4-event-type stream)
- [ ] Document scope reduction (no `token`) + 60s vs 30s cap in commit + PR

---

## NOTES

### Design decisions worth flagging in PR

1. **Scope reduction: no `token` event** — required PKG-5 OpenAIClient rewrite + 8-node refactor (2+ days). Demo theater + frontend rendering both work without it. Token streaming can ship as PKG-12.5 post-MVP if a stretch sprint opens.
2. **astream_events(v2) over stream(updates)** — gives native start AND end events per node; updates mode would require synthesizing agent_start from topology (debate loop = unreliable).
3. **60s overall wallclock cap** — PKG-8 reality is 30-50s for full graph; per-agent caps would force per-node async wrappers (complex). Single overall is honest + simpler. Issue #13 "30s per agent" is updated assumption.
4. **Live data = offline-first** — news scraping at request time = 75s (rate limit). `use_realtime` flag exists for opt-in vnstock overlay (deferred wiring; ship flag).
5. **No state change to `MultiAgentTrader`** — PKG-12 streams via raw `build_app() + astream_events`. Trader stays sync for offline backtest. Future option: add `MultiAgentTrader.stream()` method that wraps for async.

### Risks specific to PKG-12

| # | Risk | Mitigation |
|---|------|-----------|
| 1 | LangGraph `astream_events` event shape changes in next minor | Pin version in pyproject.toml (already `langgraph>=0.2` — should pin to `<1.4` or similar after smoke; verify before release) |
| 2 | sse-starlette ping interferes with TestClient body parsing | SSE parser in tests skips `:` comment lines (covered) |
| 3 | OpenAI quota exhausted mid-stream | Try/except in event_gen emits error event, stream closes cleanly |
| 4 | Client disconnect doesn't cancel graph (memory leak) | `request.is_disconnected()` check inside loop + sse-starlette client_close_handler |
| 5 | `_DEFAULT_MODELS` is private (underscore) in multi_agent/agent.py | Acceptable; if PKG-8 changes it, PKG-12 breaks loudly at import — visible regression |
| 6 | astream_events emits MANY events; iteration overhead | Spike A showed 4 events per real node + envelope events; filter is O(n) on a tiny set, no real cost |

### Khi gặp blocker

- `astream_events` returns no `name in ROLE_NAMES` → check filter: maybe LangGraph 1.2 emits `name=<run_id_uuid>` instead of node name. Switch to `metadata.langgraph_node` field (run `print(ev)` once to see real shape).
- TestClient hangs on SSE → ensure `event_gen` is `async def` returning async iterator; `EventSourceResponse(generator(), ...)` not `EventSourceResponse(generator, ...)`.
- Disconnect not detected → check `await request.is_disconnected()` inside the loop, not just at the end; some uvicorn versions only set the flag on next read.
- Real LLM smoke times out at 60s → expected for first run with cold cache; rerun (PKG-5 caches by prompt hash). Bump `_DEFAULT_TIMEOUT_S` for demo if needed (env override).

### Phase 3 status after PKG-12

| PKG | Status |
|-----|--------|
| PKG-10 backtest + metrics | ✅ merged |
| PKG-11 FastAPI shell | ✅ merged |
| **PKG-12 SSE live route (this PR)** | 🟡 ready after impl |
| PKG-13 Next.js comparison dashboard | unblocked (uses `/agents` + `/backtest/{agent}` from PKG-11) |
| PKG-14 Agent detail page | unblocked |
| PKG-15 Debate replay UI | unblocked (uses `/debate/multi_agent/{date}` from PKG-11) |
| PKG-16 Live mode UI | unblocked (EventSource(`/live/run`) from this PR) |
| **CHECKPOINT 24/05 (7 days)** | **gate on PKG-12 + PKG-13 status**; if PKG-12 ships clean, live mode is in scope; else fallback to "demo plays pre-recorded transcript via /debate" |

---

## Confidence Score

**8/10** for one-pass implementation.

Subtract:
- −0.5 LangGraph astream_events event-shape risk — spike confirmed at module level but real-world filter (with 8 nodes + debate loop) may need adjustment. Mitigation: print first event in route during smoke
- −0.5 Disconnect handling is async cancellation, classically prone to race conditions — `request.is_disconnected()` checked per yield + sse-starlette helper, but full coverage requires real-browser smoke
- −0.5 OpenAI API key surface — first real smoke needs `.env` populated; tests fully mock, but Step 10 will fail without key. Documented as expected
- −0.5 Scope reduction (no token) is a PRD §10 deviation — must be explicitly approved in PR description; reviewer pushback risk

Add back:
- +1.0 Spike A + B verified the two hardest unknowns (LangGraph event shape + SSE TestClient round-trip) BEFORE plan was written
- +0.5 PKG-11 patterns (route + Pydantic + test fixture) directly applicable
- +0.5 sse-starlette has battle-tested ping + disconnect handlers; we use defaults

PKG-12 is the highest-risk package in Phase 3 due to streaming complexity, but the spikes + scope reduction make ½–1 day realistic. Path: spikes (already done — 15 min) → sse.py + tests (30 min) → live_data.py + tests (30 min) → routes/live.py (60 min) → tests (60 min) → smoke (30 min) → PR (15 min) ≈ 4 hours hands-on, 6 hours with debugging buffer.
