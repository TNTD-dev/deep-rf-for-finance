# Feature: PKG-15 — Debate replay UI (US-3)

> Single page `/debate` cho phép pick một ngày → fetch
> `GET /debate/multi_agent/{date}` → render 10 entries multi-agent
> transcript với role-specific styling. Demo "multi-agent debate" để thầy
> hiểu agentic system suy nghĩ ra sao.
>
> Backend đã sẵn sàng (PKG-11 `/debate` route + PKG-8 transcript writer).
> Hiện chỉ có 1 date cached (`2025-05-05.json` từ smoke). PKG-15 ship
> interface ready; nhiều dates sẽ accumulate khi PKG-S full-test rerun.

## Feature Description

1 page + 4 components + 2 lib additions:

- **`app/debate/page.tsx`** — single page (no dynamic route per TASKS.md
  scope). Date picker (dropdown of available dates) drives `useEffect`
  fetch of `getDebate("multi_agent", date)`. Renders `DebateStream`.
- **`components/DebateStream.tsx`** — main renderer; iterates 10 entries,
  groups debate exchanges by round, surfaces special UI for
  portfolio_manager entry's decision dict.
- **`components/DebateEntry.tsx`** — single entry card: RoleBadge + ts +
  model + content (whitespace-pre-wrap Vietnamese markdown).
- **`components/RoleBadge.tsx`** — pill per role; 8 distinct colors via
  `lib/colors.ts:roleColor(role)`.
- **`components/DecisionPanel.tsx`** — when entry has `decision: {VCB: 0.18, ...}`,
  show as horizontal bar chart (simple Tailwind divs) + raw JSON below.
- **`components/DatePicker.tsx`** — `<select>` dropdown of hardcoded
  available dates (`AVAILABLE_DEBATE_DATES = ["2025-05-05"]` for MVP).
- **`lib/api.ts`** — add `getDebate(agent, date)`.
- **`lib/types.ts`** — add `DebateEntry`, `DebateTranscript`.
- **`lib/colors.ts`** — add `ROLE_COLORS` map + `roleColor(role)`.
- **`app/layout.tsx`** (PKG-13 flex) — add `<nav>` with Home / Debate links.

Acceptance criteria (Issue #16):
- Chọn date → fetch `/debate/multi_agent/{date}` → render 6 role + decision
  *(actual: 10 entries because debate runs 4 turns; spec says "6 role" but
  data ships 10 — surface all)*
- Role có màu/icon riêng

## User Story

As a **thầy hướng dẫn xem demo**
I want **chọn một ngày → thấy 10 turn của multi-agent trao đổi (3
analysts → 4 debate turns → trader → risk → portfolio_manager) với màu
sắc rõ ràng theo role**
So that **hiểu được "multi-agent" không phải tên gọi marketing — thực sự
có 6 vai trò khác nhau cãi nhau ra quyết định**.

As a **report writer (Người 1)**
I want **screenshot transcript một ngày cụ thể**
So that **báo cáo có hình minh hoạ "agentic debate trông thế nào"**.

## Problem Statement

5 challenges:

1. **Only 1 cached transcript** (`2025-05-05.json` từ PKG-8 smoke). Demo
   sẽ chỉ có 1 entry trong date picker. **Solution:** Hardcode
   `AVAILABLE_DEBATE_DATES = ["2025-05-05"]` as MVP; document as
   "interface ready, dates will accumulate when full test run lands in
   PKG-S". DO NOT build a backend `GET /debate/multi_agent` list endpoint
   (out of ½-day scope).
2. **Vietnamese markdown content** (`## heading`, `**bold**`, code fences).
   Adding `react-markdown` = ~50KB + setup. **Solution (D3):** Render
   `whitespace-pre-wrap font-mono-ish` — preserves line breaks; markdown
   syntax shows raw but readable. Demo OK, optimization later.
3. **Debate has 2 rounds → 4 entries** (bull/bear/bull/bear). Naive
   render shows 4 similar cards; viewer loses round structure.
   **Solution:** Detect debate sequence in `DebateStream`; show "Round N"
   sub-headers between pairs (or just round-N badge inside RoleBadge).
4. **Last entry (portfolio_manager) has `content: ""` but `decision:
   {...}` populated.** Naive render shows empty card. **Solution:**
   `DebateEntry` checks `decision` presence; if `content` empty + decision
   exists, render DecisionPanel inline instead of "(empty)".
5. **Long entries (~1300 chars markdown).** 10 entries × 1300 chars =
   13K chars vertical scroll. **Solution:** Keep entries fully expanded
   (scroll-y on container); add "back to top" button. NO collapse/expand
   complexity for MVP.

## Solution Statement

10 design decisions LOCK before code:

- **D1.** **Single `/debate` page** with internal date picker (per TASKS.md
  PKG-15 scope). NO dynamic route `[date]`. Simpler URL = `/debate`;
  state drives fetch.
- **D2.** **Hardcoded available dates list** (`AVAILABLE_DEBATE_DATES`
  array). MVP has 1 entry. Document as known limitation; PKG-S can add
  backend list endpoint later.
- **D3.** **No markdown lib.** Content rendered via `whitespace-pre-wrap`
  + slightly muted text color. Vietnamese reads cleanly even with raw
  `## VCB` markers. Avoid 50KB dep for thesis demo.
- **D4.** **Role colors in `lib/colors.ts:ROLE_COLORS`** — 8 distinct hex
  values. Analysts cool (sky/cyan/teal), bull green / bear red,
  trader→risk→PM warm (amber/orange/violet).
- **D5.** **DebateStream detects debate sequence** — when 2+ consecutive
  entries are bull/bear pairs, add round-N badge inline (no separator).
  Keeps DOM flat.
- **D6.** **DecisionPanel = horizontal Tailwind bar chart.** Each ticker
  row: name + width-% bar in agent color + value. Simple divs, no Recharts.
- **D7.** **DatePicker = native `<select>`.** No date-grid picker — we
  only have 1 date. Future: swap for grid when dates accumulate.
- **D8.** **Nav lives in `app/layout.tsx`** (PKG-13 ownership flex).
  Single `<nav>` with `<Link>` Home/Debate. Touches 1 file, 5 lines.
- **D9.** **ZERO JS-side tests** — continuing PKG-13/14 convention. Manual
  smoke + screenshot.
- **D10.** **Empty-content entry shows DecisionPanel inline.** portfolio_manager
  has `content: ""` + `decision: {...}` → render DecisionPanel as the
  card body instead of "(empty)" text.

## Feature Metadata

- **Feature Type:** New Capability (US-3; thirds full frontend route)
- **Estimated Complexity:** **Low-Medium** — ½ day; PKG-13/14 shell makes
  scaffolding mechanical
- **Primary Systems Affected:**
  - New: `frontend/app/debate/page.tsx`
  - New: `frontend/components/{DebateStream, DebateEntry, RoleBadge, DecisionPanel, DatePicker}.tsx`
  - Update: `frontend/lib/{api, types, colors}.ts`
  - Update: `frontend/app/layout.tsx` (D8 — nav bar)
- **Dependencies:** No new npm packages — pure additive frontend work.

---

## CONTEXT REFERENCES

### Relevant Codebase Files — ĐỌC TRƯỚC KHI IMPLEMENT

**Backend contract (PKG-8 + PKG-11):**

- `backend/routes/debate.py:46-78` — `GET /debate/{agent}/{date}` returns
  `{date, transcript: [{role, content, model?, ts?, decision?}]}`. Already
  maps PKG-8 `output` → `content` + injects `decision` on
  portfolio_manager entry.
- `backend/models.py:57-70` — `DebateEntry` + `DebateTranscript` Pydantic
  schemas. Mirror to `lib/types.ts`.
- `backend/sse.py:21-39` — `extract_decision()` shared regex; PKG-15
  doesn't call it (backend already inlines decision).
- `src/llm/multi_agent/state.py:23-32` — `ROLE_NAMES` (8 canonical roles):
  technical_analyst, news_sentiment_analyst, fundamental_analyst,
  bullish_researcher, bearish_researcher, trader, risk_manager, portfolio_manager.

**Transcript shape evidence (Spike A verified via curl):**

```
GET /debate/multi_agent/2025-05-05 →
{
  "date": "2025-05-05",
  "transcript": [
    {role: technical_analyst,     content: "## VCB\nSetup: ...",  model: "gpt-4o-mini", ts: "..."},
    {role: news_sentiment_analyst, content: "## VCB\nNo news...", model: "gpt-4o-mini", ts: "..."},
    {role: fundamental_analyst,    content: "```markdown\n...",   model: "gpt-4o-mini", ts: "..."},
    {role: bullish_researcher,     content: "Thesis: ...",        model: null, ts: "..."},  // round 1
    {role: bearish_researcher,     content: "Bullish đề xuất...", model: null, ts: "..."},
    {role: bullish_researcher,     content: "Bearish đã nêu...",  model: null, ts: "..."},  // round 2
    {role: bearish_researcher,     content: "...",                 model: null, ts: "..."},
    {role: trader,                 content: "...",                 model: "gpt-4o", ts: "..."},
    {role: risk_manager,           content: "...",                 model: "gpt-4o", ts: "..."},
    {role: portfolio_manager,      content: "",                    model: "gpt-4o", ts: "...",
                                   decision: {VCB: 0.18, FPT: 0.18, HPG: 0.18, VIC: 0.18, VNM: 0.18}}
  ]
}
```

10 entries. content lengths 400-1300 chars per analyst/researcher.
Researchers have `model: null` (set by their LLM client wrapper differently).
portfolio_manager has empty content + decision dict.

**Available cached transcripts (verified via shell):**

```
results/multi_agent/transcripts/
└── 2025-05-05.json     (5KB, PKG-8 smoke run)
```

**Frontend shell + patterns to inherit (PKG-13/14):**

- `frontend/app/agents/[id]/page.tsx` — pattern for client-side fetch +
  loading/error/empty states. Mirror for `app/debate/page.tsx` (similar
  structure but with date as state, not param).
- `frontend/lib/api.ts:14-17` — `getBacktest(agent)` pattern. Add
  `getDebate(agent, date)` following same shape.
- `frontend/lib/types.ts:48-50` — `BacktestPayload` mirror pattern;
  follow for `DebateTranscript`.
- `frontend/lib/colors.ts:33-46` — `agentCategory()` helper pattern. Add
  `roleColor(role)` similarly.
- `frontend/components/AgentBadge.tsx` — pill component pattern. Mirror
  for `RoleBadge.tsx`.
- `frontend/app/layout.tsx` — root layout; add `<nav>` (D8 flex).

**Repo conventions (CLAUDE.md):**

- Vietnamese communication
- KHÔNG `Co-Authored-By: Claude` in commits or PR body
- Surgical changes — touch only what we must

**Don't touch (file ownership):**

- `backend/` — read-only consume
- `src/` — research layer
- `frontend/app/agents/[id]/`, `frontend/app/page.tsx` — PKG-13/14
- `frontend/components/{PortfolioChart, MetricsTable, AgentToggle, AgentBadge, DrawdownChart, HoldingsHeatmap, AgentMetricsDetail}.tsx` — PKG-13/14
- `frontend/app/live/` — PKG-16

**Flexed (documented deviation):**

- `frontend/app/layout.tsx` — add `<nav>` for cross-page navigation
  (Home, Debate). Single source of nav. D8 acceptance.

### New Files to Create

```
frontend/
├── app/
│   └── debate/
│       └── page.tsx                   # /debate single page + date picker + DebateStream
└── components/
    ├── DebateStream.tsx               # iterates 10 entries with round-N badge for debate
    ├── DebateEntry.tsx                # single card; renders content OR DecisionPanel
    ├── RoleBadge.tsx                  # role pill (8 colors)
    ├── DecisionPanel.tsx              # horizontal Tailwind bar chart for weights
    └── DatePicker.tsx                 # <select> dropdown of AVAILABLE_DEBATE_DATES

Modify:
└── lib/api.ts                         # add getDebate(agent, date)
└── lib/types.ts                       # add DebateEntry, DebateTranscript
└── lib/colors.ts                      # add ROLE_COLORS map + roleColor()
└── app/layout.tsx                     # add <nav> with Home / Debate links (D8 flex)
```

### Relevant Documentation — ĐỌC TRƯỚC KHI IMPLEMENT

- **Next 16 `<Link>`**: https://nextjs.org/docs/app/api-reference/components/link
  - Pattern: `<Link href="/debate">Debate</Link>` (no `passHref`/`legacyBehavior`)
- **CSS `whitespace-pre-wrap`** (Tailwind utility): preserves whitespace +
  wraps long lines. Right behavior for Vietnamese markdown without lib.
- **React conditional rendering for empty content**: standard
  `entry.content ? <pre>...</pre> : <DecisionPanel decision={entry.decision} />`

### Pre-implementation spikes

**Spike A — Backend route shape (ALREADY VERIFIED via curl):**

```bash
curl -s http://localhost:8000/debate/multi_agent/2025-05-05 | python -c "
import sys, json
d = json.load(sys.stdin)
print('date:', d['date'])
print('len:', len(d['transcript']))
for e in d['transcript']:
    print(f\"  {e['role']:25} content={len(e['content'])} dec={'decision' in e}\")
"
```

Expected (verified): 10 entries; portfolio_manager has empty content +
decision dict.

**Spike B — Verify Vietnamese markdown renders cleanly with `whitespace-pre-wrap`:**

```bash
cd /home/duckk/personal/deep-rf-for-finance/frontend
mkdir -p app/spike-md
cat > app/spike-md/page.tsx <<'TSX'
"use client";
const text = `## VCB
Setup: sideways. Nhận định: **neutral, chờ catalyst**.

## FPT
Setup: downtrend nhẹ.`;
export default function Spike() {
  return (
    <div className="p-8 max-w-2xl">
      <h1>Markdown raw</h1>
      <pre className="whitespace-pre-wrap text-sm bg-gray-100 p-4 rounded">
        {text}
      </pre>
    </div>
  );
}
TSX
npm run build 2>&1 | tail -5
rm -rf app/spike-md
```

Expected: builds clean; visual check in browser shows readable Vietnamese
with line breaks preserved.

**Spike C — Cross-browser Vietnamese rendering (skip — Spike B covers):**

Trivial — Vietnamese works in all browsers with utf-8 charset (already
set by Next defaults).

### Patterns to Follow

**Type additions (`lib/types.ts`):**

```typescript
// Append at end of file. Mirror of backend/models.py DebateEntry +
// DebateTranscript.

export interface DebateEntry {
  role: string;        // one of ROLE_NAMES
  content: string;     // markdown-ish text; may be empty (portfolio_manager)
  model?: string | null;
  ts?: string;
  decision?: Record<string, number>;  // present only on portfolio_manager
  [key: string]: unknown;             // tolerate future extras
}

export interface DebateTranscript {
  date: string;
  transcript: DebateEntry[];
}
```

**API addition (`lib/api.ts`):**

```typescript
// Append at end. Mirror getBacktest pattern.

import type { AgentList, BacktestPayload, DebateTranscript } from "@/lib/types";

// ... existing exports stay ...

export async function getDebate(
  agent: string,
  date: string,
): Promise<DebateTranscript> {
  const r = await fetch(`${BACKEND_URL}/debate/${agent}/${date}`);
  if (!r.ok) throw new Error(`GET /debate/${agent}/${date} failed: ${r.status}`);
  return r.json();
}
```

**Role color additions (`lib/colors.ts`):**

```typescript
// Append at end of file.

export const ROLE_COLORS: Record<string, string> = {
  technical_analyst:      "#0ea5e9",  // sky-500
  news_sentiment_analyst: "#06b6d4",  // cyan-500
  fundamental_analyst:    "#14b8a6",  // teal-500
  bullish_researcher:     "#10b981",  // emerald-500 (bull = green)
  bearish_researcher:     "#ef4444",  // red-500     (bear = red)
  trader:                 "#f59e0b",  // amber-500
  risk_manager:           "#ea580c",  // orange-600
  portfolio_manager:      "#7c3aed",  // violet-600  (final decision)
};

export const roleColor = (role: string): string =>
  ROLE_COLORS[role] ?? "#94a3b8";
```

**Available dates constant (define in `app/debate/page.tsx` for now):**

```typescript
// MVP: hardcoded. PKG-S can add `GET /debate/multi_agent` list endpoint
// to fetch this dynamically when more dates are cached.
const AVAILABLE_DEBATE_DATES = ["2025-05-05"];
```

**RoleBadge (`components/RoleBadge.tsx`):**

```tsx
"use client";

import { roleColor } from "@/lib/colors";

interface Props {
  role: string;
  round?: number;  // 1-based; only set for bull/bear in a debate sequence
}

export function RoleBadge({ role, round }: Props) {
  const color = roleColor(role);
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium"
      style={{ backgroundColor: `${color}20`, color }}
    >
      <span
        className="inline-block h-1.5 w-1.5 rounded-full"
        style={{ backgroundColor: color }}
      />
      {role}
      {round !== undefined && (
        <span className="rounded bg-white/60 px-1 text-[10px] font-semibold">
          R{round}
        </span>
      )}
    </span>
  );
}
```

**DecisionPanel (`components/DecisionPanel.tsx`):**

```tsx
"use client";

import { colorFor } from "@/lib/colors";

interface Props {
  decision: Record<string, number>;
}

export function DecisionPanel({ decision }: Props) {
  const entries = Object.entries(decision);
  const maxWeight = Math.max(...entries.map(([, v]) => Math.abs(v)), 0.0001);
  return (
    <div className="space-y-2">
      <p className="text-xs font-semibold text-gray-700">
        Portfolio weights (target allocation)
      </p>
      <div className="space-y-1.5">
        {entries.map(([ticker, weight]) => (
          <div key={ticker} className="flex items-center gap-3 text-sm">
            <span className="w-12 font-mono text-gray-700">{ticker}</span>
            <div className="flex-1 h-5 bg-gray-100 rounded overflow-hidden">
              <div
                className="h-full transition-all"
                style={{
                  width: `${(Math.abs(weight) / maxWeight) * 100}%`,
                  backgroundColor: weight >= 0 ? "#10b981" : "#ef4444",
                }}
              />
            </div>
            <span className="w-16 text-right font-mono tabular-nums">
              {(weight * 100).toFixed(1)}%
            </span>
          </div>
        ))}
      </div>
      <details className="mt-2 text-xs text-gray-500">
        <summary className="cursor-pointer">Raw JSON</summary>
        <pre className="mt-1 rounded bg-gray-50 p-2 font-mono">
          {JSON.stringify(decision, null, 2)}
        </pre>
      </details>
    </div>
  );
}
```

**DebateEntry (`components/DebateEntry.tsx`):**

```tsx
"use client";

import { DecisionPanel } from "@/components/DecisionPanel";
import { RoleBadge } from "@/components/RoleBadge";
import type { DebateEntry as Entry } from "@/lib/types";

interface Props {
  entry: Entry;
  round?: number;
}

function fmtTime(iso: string | undefined): string {
  if (!iso) return "";
  return iso.slice(11, 19); // HH:MM:SS
}

export function DebateEntry({ entry, round }: Props) {
  const hasDecision = entry.decision !== undefined;
  const hasContent = entry.content && entry.content.trim().length > 0;

  return (
    <article className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <header className="flex flex-wrap items-center gap-3">
        <RoleBadge role={entry.role} round={round} />
        {entry.model && (
          <span className="text-xs text-gray-500">
            {String(entry.model)}
          </span>
        )}
        <span className="text-xs text-gray-400">{fmtTime(entry.ts)}</span>
      </header>
      <div className="mt-3">
        {hasDecision && !hasContent ? (
          <DecisionPanel decision={entry.decision!} />
        ) : (
          <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-gray-800">
            {entry.content}
          </pre>
        )}
        {hasDecision && hasContent && (
          <div className="mt-4 border-t pt-3">
            <DecisionPanel decision={entry.decision!} />
          </div>
        )}
      </div>
    </article>
  );
}
```

**DebateStream (`components/DebateStream.tsx`):**

```tsx
"use client";

import { DebateEntry } from "@/components/DebateEntry";
import type { DebateTranscript } from "@/lib/types";

interface Props {
  transcript: DebateTranscript;
}

// Walk the transcript; for each consecutive bull/bear pair, assign a
// 1-based round number. Other roles → undefined.
function assignDebateRounds(
  entries: DebateTranscript["transcript"],
): (number | undefined)[] {
  const out: (number | undefined)[] = new Array(entries.length).fill(undefined);
  let round = 0;
  for (let i = 0; i < entries.length; i++) {
    const r = entries[i].role;
    if (r === "bullish_researcher") {
      round += 1;
      out[i] = round;
    } else if (r === "bearish_researcher") {
      out[i] = round; // same round as the preceding bull
    }
  }
  return out;
}

export function DebateStream({ transcript }: Props) {
  const rounds = assignDebateRounds(transcript.transcript);
  return (
    <div className="space-y-3">
      {transcript.transcript.map((entry, i) => (
        <DebateEntry key={i} entry={entry} round={rounds[i]} />
      ))}
    </div>
  );
}
```

**DatePicker (`components/DatePicker.tsx`):**

```tsx
"use client";

interface Props {
  dates: string[];
  value: string;
  onChange: (date: string) => void;
}

export function DatePicker({ dates, value, onChange }: Props) {
  return (
    <label className="inline-flex items-center gap-2 text-sm">
      <span className="text-gray-700">Decision date:</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded border border-gray-300 bg-white px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
      >
        {dates.map((d) => (
          <option key={d} value={d}>
            {d}
          </option>
        ))}
      </select>
    </label>
  );
}
```

**`/debate` page (`app/debate/page.tsx`):**

```tsx
"use client";

import { useEffect, useState } from "react";

import { DatePicker } from "@/components/DatePicker";
import { DebateStream } from "@/components/DebateStream";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { BACKEND_URL, getDebate } from "@/lib/api";
import type { DebateTranscript } from "@/lib/types";

// MVP — only 1 transcript cached from PKG-8 smoke. PKG-S can fetch this
// list from a backend endpoint when more decisions accumulate.
const AVAILABLE_DEBATE_DATES = ["2025-05-05"];
const DEFAULT_AGENT = "multi_agent";

export default function DebatePage() {
  const [date, setDate] = useState<string>(AVAILABLE_DEBATE_DATES[0] ?? "");

  return (
    <main className="container mx-auto max-w-5xl space-y-6 px-4 py-6">
      <header className="border-b border-gray-200 pb-4">
        <h1 className="text-2xl font-bold tracking-tight">Multi-Agent Debate Replay</h1>
        <p className="mt-1 text-sm text-gray-600">
          One decision = 10 turns across 8 roles (3 analysts → 2 debate
          rounds → trader → risk manager → portfolio manager). Demo uses
          PKG-8 smoke transcript; more dates will accumulate after PKG-S
          full backtest run.
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold text-gray-700">
            Select date
          </CardTitle>
        </CardHeader>
        <CardContent>
          <DatePicker
            dates={AVAILABLE_DEBATE_DATES}
            value={date}
            onChange={setDate}
          />
        </CardContent>
      </Card>

      <DebateLoader date={date} />
    </main>
  );
}

function DebateLoader({ date }: { date: string }) {
  // key={date} on this component (via parent map) is overkill — instead
  // useEffect with [date] dep handles refetch and we set state through
  // the async callback, not synchronously inside the effect.
  return <DebateInner key={date} date={date} />;
}

function DebateInner({ date }: { date: string }) {
  const [transcript, setTranscript] = useState<DebateTranscript | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        setTranscript(await getDebate(DEFAULT_AGENT, date));
      } catch (e) {
        setError(String(e));
      } finally {
        setLoading(false);
      }
    })();
  }, [date]);

  if (loading) {
    return <p className="p-4 text-gray-600">Loading {date}…</p>;
  }
  if (error) {
    return (
      <div className="rounded border border-red-200 bg-red-50 p-4">
        <p className="text-red-700 font-semibold">Error: {error}</p>
        <p className="mt-2 text-sm text-gray-600">
          Is the backend running at <code>{BACKEND_URL}</code>? Try{" "}
          <code>.venv/bin/uvicorn backend.main:app --port 8000</code>.
        </p>
      </div>
    );
  }
  if (!transcript) {
    return <p className="p-4">No transcript for {date}.</p>;
  }
  return <DebateStream transcript={transcript} />;
}
```

**Layout nav patch (`app/layout.tsx` — D8 flex):**

Replace the body wrapper:

```tsx
// BEFORE
<body className="bg-gray-50 text-gray-900 min-h-full flex flex-col">
  {children}
</body>

// AFTER
<body className="bg-gray-50 text-gray-900 min-h-full flex flex-col">
  <nav className="border-b border-gray-200 bg-white">
    <div className="container mx-auto flex max-w-7xl items-center gap-6 px-4 py-3 text-sm">
      <Link href="/" className="font-semibold hover:underline">Dashboard</Link>
      <Link href="/debate" className="hover:underline">Debate</Link>
    </div>
  </nav>
  {children}
</body>
```

Add `import Link from "next/link";` at top of layout.tsx.

**Error handling (CLAUDE.md alignment):**

- Backend down → red error card + backend URL hint
- Date with no cached transcript → 404 from backend → red error
- Empty transcript array → DebateStream renders nothing; safe (defensive)
- Missing `decision` on portfolio_manager → DebateEntry falls through to
  empty-content branch (acceptable)
- New role not in ROLE_COLORS → `roleColor()` returns slate fallback

---

## DESIGN DECISIONS — LOCK BEFORE IMPLEMENT

### D1. Single `/debate` page (not `/debate/[date]`)

TASKS.md scope says "DatePicker.tsx" → dropdown drives state, not URL.
Simpler routing. URL = `/debate` regardless of selected date.

### D2. Hardcoded available dates (MVP)

`AVAILABLE_DEBATE_DATES = ["2025-05-05"]`. Document limitation; PKG-S
can ship `GET /debate/multi_agent` list endpoint later if needed.

### D3. No markdown library

`whitespace-pre-wrap` + `font-sans` preserves Vietnamese line breaks +
shows `## VCB` and `**bold**` markers raw. Demo OK; saves 50KB + setup.

### D4. Role colors in lib/colors.ts

8 distinct hex values: analysts cool (sky/cyan/teal), bull green / bear
red, trader→risk→PM warm (amber/orange/violet). Single source so
DebateStream + RoleBadge + future viz all agree.

### D5. Round-N badge inline

`DebateStream:assignDebateRounds()` returns parallel array of round
numbers (undefined for non-debate roles). RoleBadge optionally renders
`R1`/`R2` chip. No separator → DOM stays flat.

### D6. DecisionPanel = Tailwind bar chart

Each ticker → row with name + scaled bar + value%. No Recharts (overkill
for 5 values). Negative weights → red, positive → green. Raw JSON in
`<details>` for power users.

### D7. DatePicker = native select

`<select><option>` styled with Tailwind. Future: swap for a date-grid
when dates accumulate. Native = zero deps, screen-reader friendly.

### D8. Nav in app/layout.tsx (PKG-13 flex)

Single source of cross-page nav. 5-line `<nav>` addition. Documented
flex in PR.

### D9. ZERO JS tests

Continuing PKG-13/14 convention. Manual smoke + screenshot.

### D10. Empty content + decision → DecisionPanel as body

portfolio_manager entry: `content: ""` + `decision: {...}`.
`DebateEntry` checks both; if content empty + decision present, render
DecisionPanel as the card body. If both present, render content then
DecisionPanel after divider. If only content, just content.

---

## IMPLEMENTATION PLAN

### Phase 1: Lib additions (~10 min)

- `lib/types.ts` — append `DebateEntry`, `DebateTranscript`
- `lib/api.ts` — append `getDebate(agent, date)`
- `lib/colors.ts` — append `ROLE_COLORS` + `roleColor()`

### Phase 2: Components (~60 min)

- `components/RoleBadge.tsx` — simplest first
- `components/DecisionPanel.tsx` — Tailwind bars
- `components/DebateEntry.tsx` — card with branching content/decision
- `components/DebateStream.tsx` — loop + round assignment
- `components/DatePicker.tsx` — native select

### Phase 3: Page + nav (~25 min)

- `app/debate/page.tsx` — main page with DateInner pattern (key={date})
- `app/layout.tsx` — add `<nav>` (D8 flex)

### Phase 4: Build + smoke (~15 min)

- `npm run lint` + `npm run build` clean
- Start backend + dev server, navigate / → click Debate → verify

**Budget total: ~2 hours hands-on. ½ day with debugging buffer.**

---

## STEP-BY-STEP TASKS

### 1. RUN Spike A (ALREADY VERIFIED during planning)

curl + python check confirmed 10-entry shape + empty-content + decision
on portfolio_manager.

### 2. RUN Spike B — Vietnamese markdown with whitespace-pre-wrap

```bash
cd /home/duckk/personal/deep-rf-for-finance/frontend
mkdir -p app/spike-md
cat > app/spike-md/page.tsx <<'TSX'
"use client";
const text = `## VCB
Setup: sideways. Nhận định: **neutral, chờ catalyst**.

## FPT
Setup: downtrend nhẹ.`;
export default function Spike() {
  return (
    <div className="p-8 max-w-2xl">
      <pre className="whitespace-pre-wrap text-sm bg-gray-100 p-4 rounded">{text}</pre>
    </div>
  );
}
TSX
npm run build 2>&1 | tail -5
rm -rf app/spike-md
```

- **VALIDATE:** Build clean.

### 3. UPDATE `frontend/lib/types.ts` — add DebateEntry + DebateTranscript

Append at end of file. Pattern shown above. Use `[key: string]: unknown`
for extras tolerance (decision shape varies).

- **VALIDATE:** `npm run lint` clean.

### 4. UPDATE `frontend/lib/api.ts` — add getDebate()

Append at end. Import `DebateTranscript` from types.

- **VALIDATE:** `npm run lint` clean.

### 5. UPDATE `frontend/lib/colors.ts` — add ROLE_COLORS + roleColor()

Append at end. Use `Record<string, string>` map type matching existing
`AGENT_COLORS` pattern.

- **VALIDATE:** `npm run lint` clean.

### 6. CREATE `frontend/components/RoleBadge.tsx`

Per pattern. `"use client"` directive required.

- **GOTCHA:** `style={{ backgroundColor: `${color}20` }}` appends `20`
  (12% alpha in hex). Verify color stays readable on white card bg.

### 7. CREATE `frontend/components/DecisionPanel.tsx`

Per pattern. Bar widths via `Math.abs(w) / maxAbsW * 100%`.

- **GOTCHA:** `maxAbsW` falls back to `0.0001` to avoid div-by-zero on
  all-zero decision (defensive).

### 8. CREATE `frontend/components/DebateEntry.tsx`

Per pattern. Branch logic: empty content + decision → DecisionPanel;
content + decision → both with divider; else just content.

- **GOTCHA:** `entry.decision!` non-null assertion safe because
  `hasDecision` checks `!== undefined` first.

### 9. CREATE `frontend/components/DebateStream.tsx`

Per pattern. `assignDebateRounds()` is pure — increments only on bull
role, mirrors round to next bear.

- **VALIDATE:** With 4 debate entries (B/B/B/B), expect rounds = [1,1,2,2].

### 10. CREATE `frontend/components/DatePicker.tsx`

Per pattern. Controlled `<select>`.

### 11. CREATE `frontend/app/debate/page.tsx`

Per pattern. Use `key={date}` on DebateInner subcomponent (same trick
as PKG-14 to avoid synchronous setState-in-effect lint error).

- **GOTCHA:** Outer `DebatePage` owns date state; `DebateLoader` is just
  a passthrough for the `key={date}` remount; `DebateInner` does the
  actual fetch. Three-component nesting keeps the lint rule happy.

### 12. UPDATE `frontend/app/layout.tsx` — add nav (D8 flex)

- Add `import Link from "next/link";` at top.
- Wrap children with `<nav>` per pattern. Body retains existing flex.

- **VALIDATE:** `npm run build` clean. All 3 routes (`/`, `/agents/[id]`,
  `/debate`) accessible.

### 13. BUILD + LINT

```bash
cd frontend && npm run lint && npm run build
```

- **VALIDATE:** Both clean. Routes table shows `○ /debate` (static
  prerender of the shell; fetch happens client-side).

### 14. LIVE SMOKE

```bash
# Terminal A
.venv/bin/uvicorn backend.main:app --port 8000 --log-level warning

# Terminal B
cd frontend && npm run dev

# Browser: http://localhost:3000
# 1. Click "Debate" in nav → /debate loads
# 2. Date picker shows "2025-05-05" (only option)
# 3. Transcript renders 10 cards
# 4. Bull/bear entries show R1/R2 round badge
# 5. portfolio_manager (last) shows DecisionPanel bars (each ticker 18%)
# 6. Click "Dashboard" → / loads (regression check on PKG-13)
# 7. Click "multi_agent" in MetricsTable → /agents/multi_agent loads
```

- **VALIDATE:** Screenshot for PR.

### 15. COMMIT + PR

```bash
git add .agent/plans/pkg-15-debate-replay-ui.md frontend/
git status
git commit -m "PKG-15: Debate replay UI ..."
git push -u origin duc/PKG-15-frontend-debate
gh pr create --title "PKG-15: Debate replay UI" --body "... (include D8 flex callout)"
```

---

## TESTING STRATEGY

### Unit tests: NONE (continuing D9 zero-test convention)

Manual smoke + screenshot. `npm run build` catches type errors.

### Integration smoke (mandatory, in PR description)

Step 14 manual browser checklist. Capture screenshot of `/debate`.

### Edge Cases Explicitly Covered

| # | Case | Coverage |
|---|------|----------|
| 1 | portfolio_manager empty content + decision | DebateEntry renders DecisionPanel as body |
| 2 | Vietnamese markdown with `##` headings | whitespace-pre-wrap preserves layout |
| 3 | Backend down | Red error card + backend URL hint |
| 4 | Date with no cached transcript | 404 from backend → red error |
| 5 | Multiple debate rounds (bull/bear/bull/bear) | assignDebateRounds → [1,1,2,2] |
| 6 | Unknown role | roleColor fallback slate |
| 7 | All-zero decision | DecisionPanel guards maxWeight `||` 0.0001 |
| 8 | Negative weight | DecisionPanel renders red bar |

---

## VALIDATION COMMANDS

### Level 1: Lint + type check

```bash
cd frontend && npm run lint && npm run build
```

### Level 2: Smoke

Step 14 manual.

### Level 3: Backend regression unchanged

```bash
.venv/bin/pytest tests/ 2>&1 | tail -3
# Expect: 255 passed
```

### Level 4: Visual confirmation

Browser `/debate` — 10 cards visible, R1/R2 badges on debate, DecisionPanel
on last card.

---

## ACCEPTANCE CRITERIA

Issue #16:
- [ ] Chọn date → fetch `/debate/multi_agent/{date}` → render 10 entries
      (issue says "6 role + decision"; actual = 10 because debate has 4
      rounds — document in PR)
- [ ] Role có màu/icon riêng (8 ROLE_COLORS in lib/colors.ts)
- [ ] `npm run lint && npm run build` clean
- [ ] Backend regression: 255 pytest still pass

Extra (this plan):
- [ ] Nav bar in layout.tsx (D8 flex documented)
- [ ] R1/R2 round badge on debate entries
- [ ] DecisionPanel surfaces portfolio_manager weights as bars
- [ ] Empty-content portfolio_manager renders DecisionPanel inline

---

## COMPLETION CHECKLIST

- [ ] Spike B markdown render verified
- [ ] 3 lib updates (types, api, colors)
- [ ] 5 new components (RoleBadge, DecisionPanel, DebateEntry, DebateStream, DatePicker)
- [ ] `app/debate/page.tsx` shipped
- [ ] `app/layout.tsx` nav patch (D8 flex documented in PR)
- [ ] `npm run build` clean
- [ ] Manual smoke 7 steps pass
- [ ] PR opened, body `Closes #16`
- [ ] No Claude attribution per CLAUDE.md
- [ ] PKG-16 unblocked (last frontend route)

---

## NOTES

### Design decisions worth flagging in PR

1. **Single page (D1)** — TASKS.md scope said no dynamic route; state
   drives fetch. URL stays `/debate`.
2. **Hardcoded available dates (D2)** — MVP limitation; PKG-S adds list
   endpoint when more transcripts accumulate.
3. **No react-markdown (D3)** — `whitespace-pre-wrap` enough for Vietnamese
   prose; saves 50KB dep + setup time.
4. **Round-N badge inline (D5)** — keeps DOM flat; better than separator
   rows for narrow viewport.
5. **Tailwind bar chart for DecisionPanel (D6)** — Recharts overkill for
   5 values; simple divs faster.
6. **Nav in layout.tsx (D8 flex)** — touches PKG-13 owned file but
   minimal (5 lines); document in PR.
7. **Issue #16 says "6 role" but data has 10 entries** — debate has 4
   rounds (2 bull + 2 bear). Display all 10; document discrepancy.

### Risks specific to PKG-15

| # | Risk | Mitigation |
|---|------|-----------|
| 1 | Only 1 cached date — sparse demo | Document as MVP limitation; PKG-S full-test run accumulates more |
| 2 | Long content scrolls forever | Each entry full-expanded; accept scroll; add "back to top" later if needed |
| 3 | Vietnamese markdown looks raw | Acceptable for demo; future enhancement = lazy add react-markdown |
| 4 | Role color clashes with PKG-13 agent colors | Separate palette (ROLE_COLORS) — analysts cool, debate contrast, decision purple |
| 5 | D8 layout.tsx touch could surprise reviewer | PR body has explicit flex callout |
| 6 | DecisionPanel bar widths weird if weights all near 0 | `maxAbsW || 0.0001` guard |

### Khi gặp blocker

- Build fails on layout.tsx Link import → ensure `import Link from "next/link"` is at top
- /debate 404 → check `app/debate/page.tsx` exists; restart dev server
- Vietnamese chars garbled → check charset utf-8 in layout `<html lang="vi">` (already there from PKG-13)
- DecisionPanel bars empty → console.log entry.decision; ensure it's a dict not stringified JSON
- Round badge missing → check assignDebateRounds output; verify role spelling matches "bullish_researcher" exactly

### Phase 3 status after PKG-15

| PKG | Status |
|-----|--------|
| PKG-10..14 | ✅ merged |
| **PKG-15 debate replay (this PR)** | 🟡 ready after impl |
| PKG-16 Live mode UI | unblocked (consumes PKG-12 SSE; uses nav from D8) |
| **CHECKPOINT 24/05** | All frontend pages shipping cleanly; live mode is the last gate |

---

## Confidence Score

**8.5/10** for one-pass implementation.

Subtract:
- −0.5 D8 layout.tsx touch — minor file ownership flex
- −0.5 Round badge logic could miss edge cases (single bull entry without bear?)
- −0.5 Vietnamese markdown unpolished — risks "looks unfinished" critique
       at demo

Add back:
- +1.0 Backend contract verified end-to-end (Spike A curl + Python check)
- +0.5 PKG-13/14 patterns directly applicable; copy-paste blueprint
- +0.5 No new deps, no new endpoints — pure additive frontend

PKG-15 is the **most polished** frontend page so far (debate has dramatic
narrative). Path:
- Best case (~2h): spikes pass, copy patterns, ship
- Realistic (~3h): tweak DecisionPanel bar styling
- Worst case (~½ day): adjust round-badge logic + retry markdown rendering
