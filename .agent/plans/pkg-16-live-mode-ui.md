# Feature: PKG-16 — Live mode UI + SSE client (US-4 + US-5)

> Button "Run for today" → kicks off PKG-12 SSE endpoint → browser
> renders 8 role cards sáng đèn tuần tự + final portfolio weights.
> Đây là **demo moment** chính cho thầy: agentic system chạy live,
> không phải replay từ file.
>
> ½ day scope. PKG-16 là **package frontend cuối** trước PKG-S
> integration. Sau merge, repo có 17/18 packages shipped.

## Feature Description

1 new route + 3 components + 1 lib helper + 2 small flexes:

- **`app/live/page.tsx`** — `/live` page với "Run for today" button +
  live event stream display. State machine: `idle` → `streaming` →
  `done` | `error`.
- **`components/RunButton.tsx`** — button với disabled state khi đang
  streaming (prevent double-click + accidental $0.05 spend).
- **`components/SSEStream.tsx`** — render list of received events theo
  thứ tự fired. Reuses `RoleBadge` + `DecisionPanel` from PKG-15.
- **`components/LiveEntry.tsx`** — single event card; 4 branches:
  `agent_start` (skeleton/pulse), `agent_complete` (filled), `decision`
  (DecisionPanel), `error` (red banner).
- **`lib/sse.ts`** — thin wrapper exposing `streamLive(handlers)` that
  returns an `EventSource` + sets `addEventListener` per event type.
  Caller owns close.
- **`lib/types.ts`** (extend) — `LiveEvent` discriminated union.
- **`backend/routes/live.py`** (PKG-12 FLEX — 5 lines) — add
  `GET /live/run` alongside existing POST. EventSource is GET-only.
- **`app/layout.tsx`** (PKG-13/15 FLEX — 1 line) — add "Live" link in nav.

Acceptance criteria (Issue #17):
- Click "Run for today" → text streaming theo từng agent
- Mất mạng giữa stream → error banner, không crash
- Decision cuối hiển thị weights cho 5 ticker

## User Story

As a **thầy hướng dẫn xem demo (US-4)**
I want **bấm nút "Run for today" và xem hệ thống chạy thật trên dữ liệu
VN hôm nay**
So that **tin đây là sản phẩm ứng dụng được, không phải kết quả tĩnh**.

As a **người xem demo (US-5)**
I want **thấy agentic debate stream ra theo thời gian thực kiểu chat app**
So that **demo cảm giác sống động và đúng xu hướng LLM 2026**.

As a **demo presenter (Duc)**
I want **nút disabled trong khi stream chạy + cost hint trên page**
So that **không double-click ăn $0.10 cho buổi tới**.

## Problem Statement

5 challenges:

1. **EventSource là GET-only — PKG-12 endpoint là POST.** EventSource
   web API không support custom HTTP method. **Solution (D1):** Add a
   thin `GET /live/run` route ở backend (alongside existing POST) —
   5 lines, reuses `live_run` handler with `LiveRunRequest()` default.
   POST stays cho future custom-tickers UX.
2. **EventSource built-in `error` event clashes with backend `error`
   event name.** Browser fires generic `error` event on connection
   failure; backend explicitly emits `event: error data: {...}` for
   app errors. **Solution (D5):** Check `e instanceof MessageEvent &&
   e.data` to distinguish. App errors come with `data`; network errors
   don't (and trigger `readyState === EventSource.CLOSED`).
3. **Streaming = per-agent, NOT per-token.** PKG-12 scope-reduced
   token-level events; PKG-16 receives `agent_start` + `agent_complete`
   per role. **Solution:** Frame UX as "cards light up sequentially"
   (skeleton on start, fill on complete). Document trên page: "8 vai
   trò sáng đèn theo thứ tự, ~5-10s per role". Issue #17's "streaming
   theo agent" matches this exactly.
4. **Real LLM cost per click = ~$0.05** (PKG-12 smoke). Multiple clicks
   = real money. **Solution:** Disable button while `state === "streaming"`;
   surface "1 run ≈ $0.05" hint below button.
5. **EventSource auto-reconnects on disconnect.** TASKS.md scope says
   "EventSource với reconnect" but for our case reconnect = retrigger
   LLM run (cost). **Solution:** Explicit `es.close()` on `decision` or
   `error` event. Auto-reconnect only fires on transport-level errors;
   we override by closing the connection ourselves on terminal events.
   Document deviation from TASKS.md wording.

## Solution Statement

10 design decisions LOCK before code:

- **D1.** **Add `GET /live/run` to backend** (alongside POST). 5-line
  helper that calls existing `live_run` with `LiveRunRequest()` defaults.
  POST stays for PKG-S future custom-tickers UI.
- **D2.** **`new EventSource(BACKEND_URL + "/live/run")` in `useEffect`
  on button click**, NOT on mount. Stream starts when user clicks; state
  resets first.
- **D3.** **Discriminated union `LiveEvent` type** in `lib/types.ts`.
  4 variants: `agent_start`, `agent_complete`, `decision`, `error`.
  TypeScript narrow via `event.type`.
- **D4.** **State machine: `"idle" | "streaming" | "done" | "error"`**.
  RunButton disabled when `streaming`. State resets to `idle` after
  user clicks "Run again".
- **D5.** **EventSource "error" listener distinguishes app vs network**:
  ```ts
  if (e instanceof MessageEvent && e.data) {
    // backend emitted event: error
    const payload = JSON.parse(e.data);
    setEvents((prev) => [...prev, {type: "error", message: payload.message}]);
  } else {
    // network/connection failure
    setEvents((prev) => [...prev, {type: "error", message: "Connection lost"}]);
  }
  setState("error");
  es.close();
  ```
- **D6.** **Close stream explicitly on terminal events** (`decision` or
  `error`). Prevents EventSource auto-reconnect from re-triggering LLM
  run + cost.
- **D7.** **Reuse PKG-15 RoleBadge + DecisionPanel.** Single source of
  role color + weights chart. No new viz components.
- **D8.** **`agent_start` shows skeleton card with role badge + pulse
  animation** (Tailwind `animate-pulse`). When `agent_complete` for
  same role arrives, REPLACE the skeleton with filled card. State =
  flat append of events; render groups by role on the fly.
  
  **Trade-off:** Simpler render = always append, render in order. Skeleton
  card stays in DOM until matching `agent_complete` arrives next; replace
  is just "show summary instead of skeleton" via lookup. We model events
  as a flat array; render iterates with role-grouping to collapse pairs.
  
  **Simpler MVP:** render flat list — skeleton + filled both visible
  (2 cards per role). Demo sees "Technical Analyst (starting…)" then
  "Technical Analyst (done: ...)". Less polished but trivial code.
  Pick this for ½-day budget.
- **D9.** **Cost hint UI**: "1 run ≈ $0.05 (real OpenAI call)" below
  button. Honest framing prevents accidental spend.
- **D10.** **Add "Live" to nav** in `app/layout.tsx` (PKG-13/15 flex
  extension — 1 line).

## Feature Metadata

- **Feature Type:** New Capability (last frontend package; final demo piece)
- **Estimated Complexity:** **Medium** — SSE plumbing + state machine;
  mitigated by PKG-15 component reuse and small spike surface
- **Primary Systems Affected:**
  - New: `frontend/app/live/page.tsx`
  - New: `frontend/components/{SSEStream, LiveEntry, RunButton}.tsx`
  - New: `frontend/lib/sse.ts`
  - Update: `frontend/lib/types.ts` (LiveEvent discriminated union)
  - Update: `frontend/app/layout.tsx` (add "Live" link)
  - Update: `backend/routes/live.py` (add GET handler alongside POST)
- **Dependencies:** Native browser `EventSource` (no JS lib). No new
  npm or Python packages.

---

## CONTEXT REFERENCES

### Relevant Codebase Files — ĐỌC TRƯỚC KHI IMPLEMENT

**Backend (PKG-12):**

- `backend/routes/live.py:125-141` — `POST /live/run` handler. PKG-16
  adds `GET /live/run` calling the same `event_gen` logic. Reuse
  `_stream_graph_events` + `_with_timeout` + `EventSourceResponse(ping=15)`.
- `backend/routes/live.py:45-48` — `LiveRunRequest` Pydantic. GET route
  uses default `LiveRunRequest()`.
- `backend/sse.py:42-48` — `sse_event(name, data)` already returns
  `{event, data}` dict. PKG-16 doesn't touch.
- `backend/main.py:45-50` — CORS allows `["GET", "POST", "OPTIONS"]`.
  ✓ GET works without middleware change.

**Frontend shell (PKG-13/14/15):**

- `frontend/app/debate/page.tsx:14-50` — pattern for state-driven page
  with keyed inner. PKG-16's page mirrors this BUT no keyed inner needed
  (button click = single fetch, no remount on prop change).
- `frontend/components/RoleBadge.tsx` — reuse as-is for agent identity
- `frontend/components/DecisionPanel.tsx` — reuse for final weights
- `frontend/lib/colors.ts:51-64` — `ROLE_COLORS` + `roleColor()` ready
- `frontend/lib/types.ts:55-77` — pattern for adding type unions
- `frontend/lib/api.ts:1-19` — pattern; `lib/sse.ts` parallels this
- `frontend/app/layout.tsx:18-30` — current nav; add `<Link href="/live">Live</Link>`

**Reference for SSE event types (PKG-12 emits):**

```
event: agent_start
data: {"role": "technical_analyst"}

event: agent_complete
data: {"role": "technical_analyst", "summary": "..."}

(repeat 7 more times for other roles, including 4 debate turns)

event: decision
data: {"weights": {"VCB": 0.18, ...}, "rationale": "..."}

(OR on failure)
event: error
data: {"message": "timeout 60.0s exceeded"}
```

**Don't touch (file ownership):**

- `src/` — research layer
- `frontend/app/{page, agents/[id]/page, debate/page}.tsx` — PKG-13/14/15
- `frontend/components/{PortfolioChart, MetricsTable, AgentToggle,
  AgentBadge, DrawdownChart, HoldingsHeatmap, AgentMetricsDetail,
  RoleBadge, DecisionPanel, DebateEntry, DebateStream, DatePicker}.tsx`
  — PKG-13/14/15
- `backend/{cache, models, sse, main, live_data}.py` — owned

**Flexed (documented deviations):**

- `backend/routes/live.py` — add GET handler (5 lines). PKG-12 flex.
- `frontend/app/layout.tsx` — add 1 nav Link. PKG-13 flex (extending
  PKG-15's earlier flex).

### New Files to Create

```
frontend/
├── app/
│   └── live/
│       └── page.tsx                  # /live page + state machine + SSE driver
├── components/
│   ├── RunButton.tsx                 # button with disabled-while-streaming
│   ├── SSEStream.tsx                 # render list of LiveEvents
│   └── LiveEntry.tsx                 # single event card; 4 branches
└── lib/
    └── sse.ts                        # streamLive(handlers) → EventSource

Modify:
└── frontend/lib/types.ts             # append LiveEvent discriminated union
└── frontend/app/layout.tsx           # +1 nav Link "Live"
└── backend/routes/live.py            # +GET handler alongside POST (PKG-12 flex)
```

### Relevant Documentation — ĐỌC TRƯỚC KHI IMPLEMENT

- **MDN EventSource**: https://developer.mozilla.org/en-US/docs/Web/API/EventSource
  - Sections: addEventListener for named events, error handling, close()
  - Why: PKG-16's core API
- **MDN Server-sent events using events**: https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events
  - Section: "Listening for custom events" — `addEventListener("foo", handler)`
  - Why: PKG-12 emits named events (agent_start, etc.) not default "message"
- **sse-starlette EventSourceResponse**: https://github.com/sysid/sse-starlette#readme
  - Already in pyproject; reused via PKG-12 GET handler
- **FastAPI multiple HTTP methods on path**:
  https://fastapi.tiangolo.com/tutorial/path-operation-configuration/
  - Why: `@router.get` + `@router.post` on same path = 2 separate handlers

### Pre-implementation spikes

**Spike A — Verify CORS + EventSource handshake with backend GET:**

```bash
# Terminal: backend
cd /home/duckk/personal/deep-rf-for-finance
.venv/bin/uvicorn backend.main:app --port 8000 --log-level info &
UV=$!
sleep 3

# Add temporary GET handler to test (will be replaced with real one)
# OR: just verify OPTIONS preflight + GET work for existing POST path

# Test 1: OPTIONS preflight from Origin:3000
curl -i -X OPTIONS http://localhost:8000/live/run \
     -H "Origin: http://localhost:3000" \
     -H "Access-Control-Request-Method: GET" 2>&1 | head -10

# Test 2: GET (will 405 since POST-only currently — confirms we need GET handler)
curl -s -o /dev/null -w "GET HTTP %{http_code}\n" \
     http://localhost:8000/live/run

kill $UV 2>/dev/null
```

Expected: OPTIONS returns 200 with CORS headers including GET in
allow-methods. GET returns 405 Method Not Allowed (confirms POST-only
status quo → need to add GET).

**Spike B — Browser EventSource API surface (via console test):**

```typescript
// Paste in browser console at http://localhost:3000/live after Spike C lands:
const es = new EventSource("http://localhost:8000/live/run");
es.addEventListener("agent_start", (e) => console.log("START", JSON.parse(e.data)));
es.addEventListener("agent_complete", (e) => console.log("COMPLETE", JSON.parse(e.data)));
es.addEventListener("decision", (e) => console.log("DECISION", JSON.parse(e.data)));
es.addEventListener("error", (e) => console.log("ERROR", e));
// After 30-60s, expect: 8 starts + 8 completes + 1 decision (or error if timeout)
// Close manually: es.close()
```

Expected: events fire in real time. Helps verify event-type listener
syntax works as expected. SKIP if confident in MDN docs.

**Spike C — Add backend GET route and test:**

```python
# Add to backend/routes/live.py (alongside the POST):
@router.get("/live/run")
async def live_run_get(request: Request) -> EventSourceResponse:
    # GET form for EventSource (browser API is GET-only). Reuses the
    # same event_gen via the POST handler with default request body.
    return await live_run(LiveRunRequest(), request)
```

Test:
```bash
.venv/bin/uvicorn backend.main:app --port 8000 --log-level info &
sleep 3
# Should now stream events instead of 405
curl -N -H "Accept: text/event-stream" http://localhost:8000/live/run \
     --max-time 90 2>&1 | head -20
pkill -f "uvicorn backend"
```

Expected: lines like
```
event: agent_start
data: {"role": "technical_analyst"}
```
appear over ~5-50s. Stream ends with `event: decision` OR `event: error`.

### Patterns to Follow

**Backend GET handler (`backend/routes/live.py` — append):**

```python
@router.get("/live/run")
async def live_run_get(request: Request) -> EventSourceResponse:
    # GET form for browser EventSource (which is GET-only). Reuses the
    # same event_gen via the POST handler with default request body.
    # POST endpoint retained for PKG-S future custom-tickers UI.
    return await live_run(LiveRunRequest(), request)
```

**LiveEvent discriminated union (`lib/types.ts` — append):**

```typescript
// PKG-16: SSE event shape emitted by backend/routes/live.py.
// Discriminated union — TypeScript narrows on `type`.

export type LiveEvent =
  | { type: "agent_start"; role: string }
  | { type: "agent_complete"; role: string; summary: string }
  | { type: "decision"; weights: Record<string, number>; rationale: string }
  | { type: "error"; message: string };
```

**SSE wrapper (`lib/sse.ts`):**

```typescript
import { BACKEND_URL } from "@/lib/api";
import type { LiveEvent } from "@/lib/types";

interface Handlers {
  onEvent: (event: LiveEvent) => void;
  onClose: () => void; // fires after decision OR error OR network drop
}

export function streamLive(handlers: Handlers): EventSource {
  const es = new EventSource(`${BACKEND_URL}/live/run`);

  const safeClose = () => {
    es.close();
    handlers.onClose();
  };

  es.addEventListener("agent_start", (e) => {
    const data = JSON.parse((e as MessageEvent).data) as { role: string };
    handlers.onEvent({ type: "agent_start", role: data.role });
  });

  es.addEventListener("agent_complete", (e) => {
    const data = JSON.parse((e as MessageEvent).data) as {
      role: string;
      summary: string;
    };
    handlers.onEvent({
      type: "agent_complete",
      role: data.role,
      summary: data.summary,
    });
  });

  es.addEventListener("decision", (e) => {
    const data = JSON.parse((e as MessageEvent).data) as {
      weights: Record<string, number>;
      rationale: string;
    };
    handlers.onEvent({
      type: "decision",
      weights: data.weights,
      rationale: data.rationale,
    });
    safeClose();
  });

  // EventSource's "error" event fires for BOTH:
  //  - app-level errors (backend emits `event: error data: {...}`)
  //  - transport errors (network drop, server gone). MessageEvent.data
  //    presence distinguishes — app errors carry data, transport doesn't.
  es.addEventListener("error", (e) => {
    if (e instanceof MessageEvent && e.data) {
      try {
        const data = JSON.parse(e.data) as { message: string };
        handlers.onEvent({ type: "error", message: data.message });
      } catch {
        handlers.onEvent({ type: "error", message: "Malformed error event" });
      }
    } else {
      handlers.onEvent({
        type: "error",
        message:
          es.readyState === EventSource.CLOSED
            ? "Connection closed"
            : "Network error",
      });
    }
    safeClose();
  });

  return es;
}
```

**RunButton (`components/RunButton.tsx`):**

```tsx
"use client";

interface Props {
  state: "idle" | "streaming" | "done" | "error";
  onClick: () => void;
}

export function RunButton({ state, onClick }: Props) {
  const isStreaming = state === "streaming";
  const label =
    state === "idle"
      ? "Run for today"
      : state === "streaming"
        ? "Running…"
        : state === "done"
          ? "Run again"
          : "Retry";
  return (
    <button
      type="button"
      disabled={isStreaming}
      onClick={onClick}
      className="rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-gray-400"
    >
      {label}
    </button>
  );
}
```

**LiveEntry (`components/LiveEntry.tsx`):**

```tsx
"use client";

import { DecisionPanel } from "@/components/DecisionPanel";
import { RoleBadge } from "@/components/RoleBadge";
import type { LiveEvent } from "@/lib/types";

interface Props {
  event: LiveEvent;
}

export function LiveEntry({ event }: Props) {
  switch (event.type) {
    case "agent_start":
      return (
        <article className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
          <header className="flex items-center gap-3">
            <RoleBadge role={event.role} />
            <span className="text-xs text-gray-500">starting…</span>
            <span className="ml-auto h-2 w-2 animate-pulse rounded-full bg-blue-500" />
          </header>
        </article>
      );
    case "agent_complete":
      return (
        <article className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
          <header className="flex items-center gap-3">
            <RoleBadge role={event.role} />
            <span className="text-xs text-gray-500">done</span>
          </header>
          <pre className="mt-3 whitespace-pre-wrap font-sans text-sm leading-relaxed text-gray-800">
            {event.summary}
          </pre>
        </article>
      );
    case "decision":
      return (
        <article className="rounded-lg border-2 border-violet-300 bg-violet-50 p-4 shadow-sm">
          <header className="mb-3 flex items-center gap-3">
            <RoleBadge role="portfolio_manager" />
            <span className="text-xs font-semibold text-violet-700">
              FINAL DECISION
            </span>
          </header>
          <DecisionPanel decision={event.weights} />
          {event.rationale && (
            <details className="mt-3 text-xs text-gray-600">
              <summary className="cursor-pointer">Rationale</summary>
              <pre className="mt-1 whitespace-pre-wrap rounded bg-white/60 p-2">
                {event.rationale}
              </pre>
            </details>
          )}
        </article>
      );
    case "error":
      return (
        <article className="rounded-lg border border-red-200 bg-red-50 p-4 shadow-sm">
          <p className="text-sm font-semibold text-red-700">
            ⚠ {event.message}
          </p>
        </article>
      );
  }
}
```

**SSEStream (`components/SSEStream.tsx`):**

```tsx
"use client";

import { LiveEntry } from "@/components/LiveEntry";
import type { LiveEvent } from "@/lib/types";

interface Props {
  events: LiveEvent[];
}

export function SSEStream({ events }: Props) {
  if (events.length === 0) {
    return (
      <p className="text-sm text-gray-500">
        Press "Run for today" to start a live multi-agent decision.
      </p>
    );
  }
  return (
    <div className="space-y-3">
      {events.map((ev, i) => (
        <LiveEntry key={i} event={ev} />
      ))}
    </div>
  );
}
```

**/live page (`app/live/page.tsx`):**

```tsx
"use client";

import { useEffect, useRef, useState } from "react";

import { RunButton } from "@/components/RunButton";
import { SSEStream } from "@/components/SSEStream";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { streamLive } from "@/lib/sse";
import type { LiveEvent } from "@/lib/types";

type LiveState = "idle" | "streaming" | "done" | "error";

export default function LivePage() {
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [state, setState] = useState<LiveState>("idle");
  const esRef = useRef<EventSource | null>(null);

  // Cleanup on unmount — if user navigates away mid-stream, close
  // EventSource so backend's is_disconnected() fires + LLM stops.
  useEffect(() => {
    return () => {
      esRef.current?.close();
    };
  }, []);

  const start = () => {
    setEvents([]);
    setState("streaming");
    const es = streamLive({
      onEvent: (ev) => {
        setEvents((prev) => [...prev, ev]);
        if (ev.type === "error") setState("error");
      },
      onClose: () => {
        // Only flip to "done" if we didn't already go "error".
        setState((s) => (s === "streaming" ? "done" : s));
      },
    });
    esRef.current = es;
  };

  return (
    <main className="container mx-auto max-w-5xl space-y-6 px-4 py-6">
      <header className="border-b border-gray-200 pb-4">
        <h1 className="text-2xl font-bold tracking-tight">Live Multi-Agent Run</h1>
        <p className="mt-1 text-sm text-gray-600">
          Triggers a real multi-agent decision against today's market data.
          Streams per-role progress until the portfolio_manager emits final
          weights.
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold text-gray-700">
            Controls
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <RunButton state={state} onClick={start} />
          <p className="text-xs text-gray-500">
            ≈ <span className="font-medium">$0.05</span> per run (real
            OpenAI call). 60s timeout. 8 roles fire sequentially.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold text-gray-700">
            Event Stream
          </CardTitle>
        </CardHeader>
        <CardContent>
          <SSEStream events={events} />
        </CardContent>
      </Card>
    </main>
  );
}
```

**Nav patch (`app/layout.tsx` — add 1 line):**

```tsx
// existing nav becomes:
<Link href="/" className="font-semibold hover:underline">Dashboard</Link>
<Link href="/debate" className="hover:underline">Debate</Link>
<Link href="/live" className="hover:underline">Live</Link>  {/* NEW */}
```

**Error handling (CLAUDE.md alignment):**

- Backend down → EventSource error fires immediately → red "Network error" card; state=error; button re-enabled as "Retry"
- 60s timeout backend → `event: error` arrives → red card; close
- LLM API quota exhausted → backend `error` event with reason → red card; close
- User navigates away mid-stream → `useEffect` cleanup calls `es.close()` → backend `is_disconnected()` aborts
- Multiple rapid clicks → button disabled while `state === "streaming"` (prevents)
- Malformed event data (shouldn't happen) → try/catch in handlers; fallback "Malformed error event"

---

## DESIGN DECISIONS — LOCK BEFORE IMPLEMENT

### D1. Add GET /live/run alongside POST (PKG-12 flex, 5 lines)

EventSource is GET-only. Adding GET preserves POST for future
custom-tickers UI. PKG-12 file ownership flex documented in PR.

### D2. EventSource started by button click, not mount

User has to explicitly opt-in to spending $0.05.

### D3. LiveEvent discriminated union

4 variants; `switch (event.type)` in LiveEntry. TypeScript narrows
each branch cleanly.

### D4. State machine: idle → streaming → done | error

`streaming` disables button. `error` makes button label "Retry".
`done` makes it "Run again".

### D5. Distinguish app vs network errors in EventSource error listener

`if (e instanceof MessageEvent && e.data) → app error; else → network`.
Documented in `lib/sse.ts` comment.

### D6. Close stream on terminal events (decision OR error)

Prevents EventSource auto-reconnect from re-triggering LLM run.
Explicit `es.close()` in handlers + `useEffect` cleanup on unmount.

### D7. Reuse RoleBadge + DecisionPanel from PKG-15

Single source of role color + weights chart. No new viz.

### D8. Flat events list with skeleton + filled both visible

Trade simpler render for slightly more visual noise. ½-day scope.
Each role shows 2 cards: "starting…" then "done with summary".
Demo flow stays clear.

### D9. Cost hint UI: "≈ $0.05 per run"

Below button. Honest disclosure prevents accidental spending.

### D10. Add "Live" to layout nav

1-line addition to `app/layout.tsx`. PKG-15's nav already had Dashboard
+ Debate; PKG-16 extends with Live.

---

## IMPLEMENTATION PLAN

### Phase 1: Backend GET handler + spike (~15 min)

- Append `GET /live/run` to `backend/routes/live.py`
- Spike A: verify with curl that GET returns stream

### Phase 2: Frontend foundation (~20 min)

- `lib/types.ts` — append `LiveEvent` union
- `lib/sse.ts` — `streamLive(handlers)` wrapper

### Phase 3: Components (~45 min)

- `components/RunButton.tsx`
- `components/LiveEntry.tsx` (4-branch switch)
- `components/SSEStream.tsx`

### Phase 4: Page + nav (~25 min)

- `app/live/page.tsx`
- Patch `app/layout.tsx` (add "Live" Link)

### Phase 5: Build + smoke (~15 min)

- `npm run lint` + `npm run build` clean
- Start backend + dev server; click button; verify cards fire

**Budget: ~2 hours hands-on. ½ day with buffer + real LLM smoke ($0.05).**

---

## STEP-BY-STEP TASKS

### 1. RUN Spike A — verify current 405 + CORS allows GET

```bash
cd /home/duckk/personal/deep-rf-for-finance
.venv/bin/uvicorn backend.main:app --port 8000 --log-level warning &
UV=$!
sleep 4
curl -s -i -X OPTIONS http://localhost:8000/live/run \
     -H "Origin: http://localhost:3000" \
     -H "Access-Control-Request-Method: GET" | grep -i "access-control"
curl -s -o /dev/null -w "GET HTTP %{http_code}\n" http://localhost:8000/live/run
kill $UV
```

- **VALIDATE:** OPTIONS shows `access-control-allow-methods` including GET.
  GET returns 405 (POST-only).

### 2. UPDATE `backend/routes/live.py` — add GET handler

Append after the existing POST handler:

```python
@router.get("/live/run")
async def live_run_get(request: Request) -> EventSourceResponse:
    # GET form for browser EventSource (which is GET-only).
    # Reuses the same event_gen via the POST handler with default body.
    # POST endpoint retained for PKG-S future custom-tickers UI.
    return await live_run(LiveRunRequest(), request)
```

- **GOTCHA:** Don't import `LiveRunRequest` twice — already imported at top.
- **VALIDATE:**
  ```bash
  .venv/bin/uvicorn backend.main:app --port 8000 --log-level warning &
  sleep 3
  curl -N -H "Accept: text/event-stream" http://localhost:8000/live/run --max-time 90 2>&1 | head -15
  pkill -f "uvicorn backend"
  ```
  Expected: streams `event: agent_start` lines, then more, ending with
  `event: decision` OR `event: error`. Costs ~$0.05 — do once.

### 3. RUN Backend pytest regression

```bash
.venv/bin/pytest tests/ 2>&1 | tail -3
```

- **VALIDATE:** 255 still pass (GET handler doesn't affect tests).

### 4. UPDATE `frontend/lib/types.ts` — append LiveEvent

```typescript
// PKG-16: SSE event shape from POST/GET /live/run.
export type LiveEvent =
  | { type: "agent_start"; role: string }
  | { type: "agent_complete"; role: string; summary: string }
  | { type: "decision"; weights: Record<string, number>; rationale: string }
  | { type: "error"; message: string };
```

- **VALIDATE:** `cd frontend && npm run lint` clean.

### 5. CREATE `frontend/lib/sse.ts`

- **IMPLEMENT:** As shown in Patterns. `streamLive(handlers)` returns
  EventSource. Handlers receive narrowed `LiveEvent` objects.
- **GOTCHA:** Cast `e` to `MessageEvent` inside event listeners for
  type-safe `.data` access. EventSource named-event payloads are
  MessageEvent.
- **VALIDATE:** `npm run lint` clean.

### 6. CREATE `frontend/components/RunButton.tsx`

- **IMPLEMENT:** As shown. 4 label states: "Run for today", "Running…",
  "Run again", "Retry".
- **VALIDATE:** Compiles.

### 7. CREATE `frontend/components/LiveEntry.tsx`

- **IMPLEMENT:** 4-branch switch as shown.
- **GOTCHA:** Decision branch uses `border-2 border-violet-300` to visually
  distinguish from other entries — the climax card.

### 8. CREATE `frontend/components/SSEStream.tsx`

- **IMPLEMENT:** As shown. Empty state shows hint text.

### 9. CREATE `frontend/app/live/page.tsx`

- **IMPLEMENT:** As shown. `useRef<EventSource | null>` for cleanup,
  state machine for idle/streaming/done/error.
- **GOTCHA:** `useEffect` returns cleanup that calls `es.close()` on unmount
  — fires backend's `is_disconnected()` so LLM stops.

### 10. PATCH `frontend/app/layout.tsx` — add Live link

Add inside the existing `<nav>` div:

```tsx
<Link href="/live" className="hover:underline">Live</Link>
```

- **GOTCHA:** `Link` already imported (from PKG-15).
- **VALIDATE:** `npm run build` clean. Routes table shows `/`, `/agents/[id]`,
  `/debate`, `/live`.

### 11. BUILD + LINT

```bash
cd frontend && npm run lint && npm run build
```

- **VALIDATE:** Both clean. `/live` in routes table.

### 12. LIVE SMOKE (real LLM, ~$0.05)

```bash
# Terminal A
.venv/bin/uvicorn backend.main:app --port 8000

# Terminal B
cd frontend && npm run dev -- --port 3200

# Browser: http://localhost:3200/live
# 1. See empty state + button enabled
# 2. Click "Run for today" → button disables
# 3. Cards appear sequentially as each role fires
# 4. After ~30-60s, decision card appears (or error if timeout)
# 5. Button re-enables as "Run again"
```

- **VALIDATE:** Screenshot for PR.

### 13. COMMIT + PR

Commit message + PR body should DOCUMENT:
- D1 PKG-12 backend flex (added GET route)
- D10 layout nav flex extension (added Live link)
- Cost note (1 click ≈ $0.05)
- Acceptance criteria coverage

---

## TESTING STRATEGY

### Unit tests: NONE (continuing D9 zero-test convention from PKG-13-15)

Manual smoke + screenshot.

### Integration smoke (mandatory, in PR description — costs ~$0.05 once)

Step 12 manual checklist.

### Edge Cases Explicitly Covered

| # | Case | Coverage |
|---|------|----------|
| 1 | EventSource POST-only mismatch | Backend GET route added (D1) |
| 2 | EventSource auto-reconnect | Explicit `es.close()` on terminal events (D6) |
| 3 | App error vs network error | MessageEvent.data presence check (D5) |
| 4 | User navigates away mid-stream | useEffect cleanup closes es; backend aborts |
| 5 | Multiple rapid clicks | Button disabled while streaming (D4) |
| 6 | Backend down | Network error → red card → button "Retry" |
| 7 | 60s timeout | Backend emits `event: error` → close → red card |
| 8 | Malformed event data | try/catch in error handler → "Malformed" message |

NOT in MVP (post-package):
- Reconnect after network error (would re-spend $0.05)
- Cancel mid-stream button
- Custom tickers input (POST endpoint preserved for this)

---

## VALIDATION COMMANDS

### Level 1: Lint + type check

```bash
cd frontend && npm run lint && npm run build
```

### Level 2: Backend regression

```bash
.venv/bin/pytest tests/ 2>&1 | tail -3
# Expect: 255 passed (GET handler doesn't break existing tests)
```

### Level 3: SSE handshake smoke (no LLM cost)

```bash
.venv/bin/uvicorn backend.main:app --port 8000 --log-level warning &
sleep 3
# OPTIONS preflight check
curl -s -i -X OPTIONS http://localhost:8000/live/run \
     -H "Origin: http://localhost:3000" \
     -H "Access-Control-Request-Method: GET" | grep -i "access-control"
pkill -f "uvicorn backend"
```

### Level 4: Real LLM smoke (~$0.05)

Step 12 manual browser checklist.

### Level 5: Build artifact route table check

```bash
cd frontend && npm run build 2>&1 | grep "^├\|^└"
# Expect routes /, /agents/[id], /debate, /live all listed
```

---

## ACCEPTANCE CRITERIA

Issue #17:
- [ ] Click "Run for today" → text streaming theo agent (cards appear sequentially)
- [ ] Mất mạng giữa stream → error banner, không crash
- [ ] Decision cuối hiển thị weights cho 5 ticker
- [ ] `npm run lint && npm run build` clean
- [ ] Backend regression: 255 pytest still pass

Extra (this plan):
- [ ] Button disabled while streaming (prevents double-click)
- [ ] Cost hint "≈ $0.05 per run" below button
- [ ] PR documents D1 PKG-12 flex (backend GET handler added)
- [ ] PR documents D10 layout nav flex (Live link added)

---

## COMPLETION CHECKLIST

- [ ] Spike A verified (OPTIONS + current 405 status)
- [ ] Backend GET handler shipped + pytest still 255
- [ ] 3 frontend components (RunButton, LiveEntry, SSEStream)
- [ ] lib/sse.ts streamLive() wrapper
- [ ] lib/types.ts LiveEvent union
- [ ] app/live/page.tsx + layout.tsx nav patch
- [ ] `npm run build` clean — `/live` in routes table
- [ ] Real LLM smoke (1×) — screenshot in PR
- [ ] PR opened, body `Closes #17`
- [ ] No Claude attribution per CLAUDE.md
- [ ] PKG-S unblocked (all frontend pages shipped)

---

## NOTES

### Design decisions worth flagging in PR

1. **D1 backend GET flex (5 lines)** — EventSource is GET-only; smallest
   change vs polyfill or library
2. **D5 error event disambiguation** — EventSource built-in "error" vs
   our app "error" event collision; MessageEvent.data check resolves
3. **D6 explicit close** — auto-reconnect would re-spend $0.05; we
   close on terminal events
4. **D8 skeleton + filled both visible** — simpler render, slightly
   noisier UX; acceptable for ½-day
5. **D9 cost hint** — honest disclosure prevents accidental spending
6. **D10 layout nav extension** — single source of nav stays clean
7. **No reconnect** — TASKS.md scope said "EventSource với reconnect";
   we deviate because reconnect = LLM cost. Document.
8. **Reuse RoleBadge + DecisionPanel from PKG-15** — single source of
   role visual identity

### Risks specific to PKG-16

| # | Risk | Mitigation |
|---|------|-----------|
| 1 | Backend timeout 60s fires before decision | Already returns `event: error` cleanly; UI handles |
| 2 | OPENAI_API_KEY missing in .env | Backend logs + returns error event; UI shows red card |
| 3 | EventSource doesn't fire CORS preflight (simple req) | GET is simple if no custom headers; check console for CORS errors during smoke |
| 4 | Real-LLM smoke timing — Demo might exceed 60s | Document; PR mention "60s soft cap, hard error event clean" |
| 5 | Vietnamese summary text very long (~500 chars) | `whitespace-pre-wrap` + scroll on card; acceptable |
| 6 | User refresh page mid-stream | EventSource auto-cleaned by browser; backend `is_disconnected` fires; ~10s delay until next yield |

### Khi gặp blocker

- 405 from GET → backend GET handler not added/import error
- CORS error in browser console → check `backend/main.py` allow_origins
  includes `http://localhost:3000` (or whichever port dev server uses)
- EventSource fires "error" immediately → backend not running or CORS
  preflight rejected
- Decision event doesn't arrive → check backend logs for timeout/LLM
  error; look for `event: error` in network tab
- Multiple decision events on same run → EventSource auto-reconnected;
  ensure `es.close()` called in handler (D6)

### Phase 3 status after PKG-16

| PKG | Status |
|-----|--------|
| PKG-10..15 | ✅ merged |
| **PKG-16 Live mode UI (this PR)** | 🟡 ready after impl |
| PKG-S Serialized integration | unblocked (all 4 frontend routes shipped: `/`, `/agents/[id]`, `/debate`, `/live`) |
| **CHECKPOINT 24/05** | All frontend complete; just PKG-S + report polish |

After PKG-16 merge: **17/18 packages** shipped. PKG-S = final
integration (registry merge, offline toggle, Loom recording, rehearsal).

---

## Confidence Score

**8/10** for one-pass implementation.

Subtract:
- −1.0 EventSource error handling subtlety (D5 — distinguishing app vs
  network) is a single point where misimplementation causes silent UX
  bugs
- −0.5 Real-LLM smoke can timeout (60s vs realistic 30-50s) — adds
  variance to acceptance check
- −0.5 D8 flat-list UX may look noisy (8 skeleton cards + 8 filled cards
  + 1 decision = 17 cards scrolling)

Add back:
- +1.0 Backend GET flex is trivial + PKG-12 patterns proven
- +0.5 PKG-15 components fully reusable (RoleBadge, DecisionPanel)
- +0.5 PKG-15 page pattern directly applicable

PKG-16 is **the demo finale**. Path:
- Best case (~2h): backend GET + components copy, smoke passes
- Realistic (~3h): debug EventSource error handler edge case
- Worst case (~½ day): smoke fires 60s timeout repeatedly; document
  as "60s budget" and ship anyway (still demonstrates live mode)
