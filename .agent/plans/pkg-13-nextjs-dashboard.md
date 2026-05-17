# Feature: PKG-13 — Next.js shell + comparison dashboard (US-1)

> First frontend package. Đây là cái thầy mở đầu tiên — phải truyền tải "agent
> nào thắng" trong < 30s (PRD §11). PKG-13 ship `localhost:3000` Next.js
> dashboard consume `backend/` (PKG-11) qua client-side `fetch`. Chart overlay
> 8 agents + bảng metrics sortable. KHÔNG SSE (PKG-16), KHÔNG agent detail
> page (PKG-14), KHÔNG debate replay (PKG-15) — đây CHỈ là shell + dashboard.
>
> ⚠️ **Highest-risk package của thesis.** Solo dev không phải frontend pro;
> Next.js + Tailwind + Recharts + shadcn/ui learning curve có thể nuốt
> > 1 day. Plan có **explicit fallback gate ở CHECKPOINT 24/05**: nếu
> Next.js stuck > 1 day, switch sang Streamlit (1-file Python dashboard,
> dùng same backend endpoints). Streamlit pseudo-code đính kèm trong NOTES
> section dưới cùng.

## Feature Description

Single comparison dashboard page + supporting shell:

- **`app/page.tsx`** — homepage: header + portfolio overlay chart (8 agents) + metrics table (sortable, default by cum_return desc) + per-agent visibility toggles
- **`app/layout.tsx`** — root layout (light mode only, Tailwind base, font, simple header)
- **`components/PortfolioChart.tsx`** — Recharts `LineChart` with 8 lines (baselines dashed, agents solid), tooltip on hover, ResponsiveContainer
- **`components/MetricsTable.tsx`** — shadcn `Table` with sortable columns (cum return, Sharpe, MDD, total cost, n_steps)
- **`components/AgentToggle.tsx`** — chip/checkbox grid to show/hide series in chart + table
- **`lib/api.ts`** — typed `fetch` wrappers: `getAgents()`, `getBacktest(agent)`
- **`lib/types.ts`** — TypeScript mirrors of `backend/models.py` Pydantic schemas
- **`lib/format.ts`** — number formatters (percent, VND, USD, decimals)
- **`lib/colors.ts`** — deterministic name→color map for 8 agents

Acceptance criteria (Issue #14):
- `npm run dev` → `localhost:3000` shows chart + table
- Hover line → tooltip with date + value
- Responsive ≥ 1280px (demo trên laptop)

## User Story

As a **thầy hướng dẫn** (advisor mở demo)
I want **mở `localhost:3000` thấy ngay biểu đồ portfolio overlay 8 chiến lược
+ bảng metrics sorted by return**
So that **trong < 30s biết "BuyAndHold +103% > PPO +40% > Equal +53% > ..."
mà không cần đọc CSV hay chạy Python**.

As a **PKG-14 implementor (next package)**
I want **shell (layout.tsx + lib/api.ts + lib/types.ts) đã setup + working**
So that **PKG-14 chỉ tạo `app/agents/[id]/page.tsx` mà không scaffold lại
toolchain**.

As a **demo presenter (Duc trong buổi bảo vệ)**
I want **toggle on/off agents trên chart**
So that **kể câu chuyện theo từng layer: "đây là baselines, đây là RL, đây
là LLM agents" — không bị 8 đường rối**.

## Problem Statement

5 challenges:

1. **Solo dev learning curve.** Duc nhận xét trong checkpoint không phải
   frontend specialist. Next.js 15 + App Router + Tailwind + Recharts +
   shadcn/ui là 5 tech surfaces. **Solution:** Scope ruthlessly — không
   dark mode, không i18n, không state mgmt lib, không E2E tests. Plan
   include EXACT npm commands (versions pinned). Streamlit fallback
   documented for go/no-go gate.
2. **Backend = localhost FastAPI; no production deployment.** Hardcoding
   `http://localhost:8000` is correct (KHÔNG env var = demo simplicity).
   **Solution:** `lib/api.ts` exports `BACKEND_URL` constant; ONE place
   to change for moving demos.
3. **Chart with 8 overlapping lines = visual clutter.** PRD §11 "<30s
   biết agent nào thắng" requires hierarchy. **Solution:** baselines
   dashed (background context), agents solid (foreground); toggle UI lets
   presenter selectively hide; default color palette uses semantically
   distinct hues (warm = LLM, cool = RL, gray = baselines).
4. **Pydantic ↔ TypeScript type drift.** Backend `Metrics` has
   `extra="allow"` (LLM agents add `llm_cost_usd` etc.). TS must mirror
   loosely. **Solution:** `Metrics` type = required fields explicit +
   `[key: string]: number | undefined` index signature for extras.
5. **shadcn/ui v4 + Tailwind v4 release churn.** Cutoff Jan 2026 + libs
   move fast. **Solution:** Pin Tailwind v3 (stable), shadcn use the
   `@latest` CLI which generates code into the repo (not a runtime dep).
   Components live in `components/ui/` — owned by us, immune to upstream
   breakage.

## Solution Statement

10 design decisions LOCK before code:

- **D1.** **Next.js 15 App Router + TypeScript strict.** App Router for forward
  compat; TypeScript strict so type errors caught at build, not at demo.
- **D2.** **Tailwind v3 (stable, not v4).** v4 just released; demo deadline
  31/05 — không thời gian debug regressions. Pin `tailwindcss@^3.4`.
- **D3.** **shadcn/ui for `Table` + `Card`; Recharts for chart.** shadcn
  generates code into `components/ui/` (owned by us). Recharts handles the
  LineChart directly — KHÔNG dùng shadcn `Chart` wrapper (adds abstraction +
  pin to a specific Recharts version).
- **D4.** **All data fetched client-side via `useEffect` + `fetch`.** No
  SSR/RSC server-side fetching (backend là localhost only — server-side
  fetch would fail in production builds). Components are `"use client"`.
- **D5.** **`useState` only for UI state.** No Zustand/Redux/Jotai. UI state =
  visible agent set (Set<string>) + selected sort column. Both fit `useState`.
- **D6.** **Color palette: 8 deterministic colors via name→hex map.**
  Baselines (3): grays/desaturated. Agents (5): distinct hues per family
  (RL: blues, LLM: warm). Map in `lib/colors.ts` so chart + table + toggle
  all agree.
- **D7.** **Number formatting helpers in `lib/format.ts`.**
  `formatPercent(0.103) = "+10.3%"`, `formatVND(1_426_553) = "1.43M ₫"`,
  `formatUSD(0.0547) = "$0.05"`, `formatSharpe(2.75) = "2.75"`. Single
  source ensures chart tooltip + table cells agree.
- **D8.** **`AgentToggle` is a controlled component.** Parent (`page.tsx`)
  owns the `Set<string>` of visible agents; toggle emits onChange. Chart
  + table both read from the same set — visibility is hierarchical.
- **D9.** **ZERO JS-side tests (no Vitest/Jest).** Save time budget. Smoke =
  manual: `npm run dev` + screenshot in PR + curl-test API client via
  `npm run lint && npm run build` (catches type errors). Tests reintroduce
  if scope grows post-MVP.
- **D10.** **Hardcoded `http://localhost:8000` in `lib/api.ts`.** No env
  var, no `.env.local`. Demo is localhost. Document for moving demos:
  "edit lib/api.ts line N to change BACKEND_URL".

## Feature Metadata

- **Feature Type:** New Capability (first frontend; unblocks PKG-14/15/16
  which inherit the shell + types + lib)
- **Estimated Complexity:** **Medium-High** — multiple new tech surfaces;
  mitigated by ruthless scope (no tests, no state lib, no dark mode)
- **Primary Systems Affected:**
  - New: `frontend/` package (entire Next.js tree)
  - New: `frontend/{app,components,lib}/`
  - Update: `README.md` (frontend setup section + node version note)
  - Update: `.gitignore` (`frontend/node_modules`, `frontend/.next/`)
- **Dependencies:** Node 18.18+ (we have v24.14.1 ✓). NPM packages:
  - `next@15`, `react@19`, `react-dom@19`, `typescript@5`
  - `tailwindcss@^3.4`, `postcss`, `autoprefixer`
  - `recharts@^2.13` (Recharts 3 alpha — too new)
  - `class-variance-authority`, `clsx`, `tailwind-merge`, `lucide-react` (shadcn deps)
  - `@radix-ui/react-slot` (transitive shadcn)
  - `eslint`, `eslint-config-next`

---

## CONTEXT REFERENCES

### Relevant Codebase Files — ĐỌC TRƯỚC KHI IMPLEMENT

**The API PKG-13 consumes (PKG-11):**

- `backend/routes/agents.py` — `GET /agents → {agents: string[], baselines: string[]}`. Hardcoded `BASELINE_AGENTS = {"buy_and_hold", "equal_weight", "random"}`.
- `backend/routes/backtest.py` — `GET /backtest/{agent} → BacktestPayload`. 5-line route, pure file read.
- `backend/models.py:14-79` — Pydantic schemas; THE source TS types mirror:
  - `Provenance`, `PortfolioPoint`, `Metrics` (extra="allow"!), `BacktestPayload`, `AgentList`
- `backend/main.py:39-62` — CORS allows `http://localhost:3000`; `allow_methods=["GET", "POST", "OPTIONS"]`. Already correct for PKG-13.

**Existing artifacts to verify shape against:**

- `results/metrics_table.csv` — cross-agent CSV; row count = 8; columns include `cumulative_return, sharpe, sortino, max_drawdown, turnover, total_cost, n_steps` + LLM extras
- `results/buy_and_hold/metrics.json` — 50KB sample; 248 portfolio_curve points + 248 holdings rows
- `results/multi_agent/metrics.json` — 2KB sample with extras like `llm_cost_usd, n_decisions, avg_latency_s, avg_debate_rounds`
- `results/zero_shot/metrics.json` — 3KB sample with 11 points (smoke run)

**Pre-PKG-13 baseline metrics (from `results/metrics_table.csv` — what dashboard should display):**

| agent          | cum_return | sharpe | mdd    | n_steps |
|----------------|-----------:|-------:|-------:|--------:|
| buy_and_hold   | +103.18%   | 2.75   | 19.71% | 247     |
| equal_weight   | +53.07%    | 2.14   | 18.18% | 247     |
| ppo            | +40.29%    | 1.26   | 17.59% | 247     |
| zero_shot      | +8.69%     | 10.52  | 1.39%  | 10      |
| single_agentic | +6.47%     | 8.93   | 1.50%  | 10      |
| multi_agent    | +2.79%     | 10.86  | 0.29%  | 4       |
| ddpg           | +1.07%     | 0.05   | 23.18% | 247     |
| random         | -10.32%    | -0.45  | 26.74% | 247     |

LLM agent rows have small n_steps (smoke runs only); chart should still render their truncated line.

**Repo conventions to honor:**

- `CLAUDE.md` §"Out of scope" — public deployment, real-money trading, intraday — không. PKG-13 ship localhost only.
- `CLAUDE.md` §"Commit & PR attribution" — KHÔNG `Co-Authored-By: Claude` trong commits hay PR body.

**Don't touch (file ownership):**

- `backend/` — owned by PKG-11/12 (read-only consume)
- `src/` — research layer
- `frontend/app/agents/[id]/` — PKG-14
- `frontend/app/debate/` — PKG-15
- `frontend/app/live/` — PKG-16
- `frontend/components/{HoldingsHeatmap,DrawdownChart,DebateStream,SSEStream}.tsx` — future packages

### New Files to Create

```
frontend/
├── .gitignore                       # next, node_modules, .next, build artifacts
├── package.json                     # pinned deps
├── package-lock.json                # generated
├── tsconfig.json                    # strict TS
├── next.config.ts                   # minimal
├── tailwind.config.ts               # content paths + base theme
├── postcss.config.js                # tailwind + autoprefixer
├── components.json                  # shadcn config (generated by `npx shadcn init`)
├── eslint.config.mjs                # generated by create-next-app
├── app/
│   ├── layout.tsx                   # root layout + globals.css import + simple header
│   ├── page.tsx                     # comparison dashboard (the homepage)
│   └── globals.css                  # Tailwind directives + custom CSS vars
├── components/
│   ├── PortfolioChart.tsx           # Recharts LineChart, 8 agents
│   ├── MetricsTable.tsx             # shadcn Table + sort
│   ├── AgentToggle.tsx              # chip grid show/hide
│   └── ui/                          # shadcn-generated (table.tsx, card.tsx, button.tsx)
└── lib/
    ├── api.ts                       # getAgents, getBacktest typed wrappers
    ├── types.ts                     # TS mirror of backend/models.py
    ├── format.ts                    # number/currency formatters
    ├── colors.ts                    # agent → hex map
    └── utils.ts                     # generated by shadcn (cn helper)

Update at repo root:
├── .gitignore                       # add frontend/node_modules + frontend/.next
└── README.md                        # add "Frontend setup" section
```

### Relevant Documentation — ĐỌC TRƯỚC KHI IMPLEMENT

- **Next.js 15 App Router**: https://nextjs.org/docs/app
  - Sections: Getting Started, Layouts, Client Components
  - Why: PKG-13's pages are `"use client"` (fetch in useEffect)
- **shadcn/ui Installation**: https://ui.shadcn.com/docs/installation/next
  - Sections: init, add components
  - Why: Component generation pattern (code lives in repo)
- **Recharts LineChart**: https://recharts.org/en-US/api/LineChart
  - Sections: Line, Tooltip, Legend, XAxis, YAxis, ResponsiveContainer
  - Why: Core chart primitive
- **Tailwind v3 Installation**: https://v3.tailwindcss.com/docs/guides/nextjs
  - Why: Pin v3 (skip v4 churn until post-deadline)
- **React 19 useEffect data fetching**: https://react.dev/reference/react/useEffect#fetching-data-with-effects
  - Why: Pattern for client-side fetch + loading/error states

### Pre-implementation spikes

**Spike A — Scaffold + measure init time:**

```bash
cd /home/duckk/personal/deep-rf-for-finance
# Note: --src-dir=false so files live at frontend/app/ not frontend/src/app/
# Use --no-git because we want a single repo
npx create-next-app@latest frontend \
    --typescript --tailwind --app \
    --no-src-dir --no-git --no-import-alias \
    --use-npm
ls frontend/
# Verify: app/, package.json, tsconfig.json, tailwind.config.ts, next.config.ts
```

Expected: scaffold completes < 60s; `frontend/app/{page.tsx, layout.tsx, globals.css}` exist; `package.json` lists `next@^15`, `react@^19`, `tailwindcss@^3`.

**Spike B — shadcn init + add table component:**

```bash
cd frontend
npx shadcn@latest init --yes --base-color slate
# Accept defaults; this writes components.json + lib/utils.ts + CSS variables
npx shadcn@latest add table card button --yes
ls components/ui/
# Expected: table.tsx, card.tsx, button.tsx, plus utils
```

Expected: 3 components in `components/ui/`. NO runtime deps added (shadcn generates inline code).

**Spike C — Cross-origin fetch from Next.js to FastAPI:**

```bash
# Terminal 1: backend
.venv/bin/uvicorn backend.main:app --port 8000 --log-level info &

# Terminal 2: smoke fetch with curl + Origin header (simulates Next.js request)
curl -s -H "Origin: http://localhost:3000" \
     http://localhost:8000/agents \
  | python -m json.tool

# Verify CORS headers
curl -s -i -H "Origin: http://localhost:3000" \
     http://localhost:8000/agents | grep -i "access-control"

# Cleanup
pkill -f "uvicorn backend.main:app --port 8000"
```

Expected: 200 JSON `{agents: [...], baselines: [...]}` AND
`access-control-allow-origin: http://localhost:3000` response header.
Confirms PKG-11 CORS already covers PKG-13's Origin.

### Patterns to Follow

**TypeScript type mirror (`lib/types.ts`):**

```typescript
// Mirror of backend/models.py — keep in sync when Pydantic changes.

export interface Provenance {
  ts: string;
  seed: number;
  test_window: string[] | null;
  n_steps: number;
}

export interface PortfolioPoint {
  date: string;  // "YYYY-MM-DD"
  value: number;  // int VND
}

// HoldingsPoint = {date: string, [ticker: string]: number | string}
// — date first key, the rest are tickers (VCB, FPT, ...) mapping to int counts.
export type HoldingsPoint = { date: string } & { [ticker: string]: number | string };

export interface Metrics {
  // Required (always present)
  cumulative_return: number;
  sharpe: number;
  sortino: number;
  max_drawdown: number;
  turnover: number;
  total_cost: number;
  n_steps: number;
  // Extras — present on LLM / multi_agent rows only
  llm_cost_usd?: number;
  avg_latency_s?: number;
  max_latency_s?: number;
  timeout_rate?: number;
  node_errors_total?: number;
  avg_debate_rounds?: number;
  parse_failure_rate?: number;
  n_decisions?: number;
  avg_iterations_per_decision?: number;
  hallucination_rate?: number;
  cap_hit_rate?: number;
  cached_tokens?: number;
  llm_calls?: number;
  [key: string]: number | undefined;
}

export interface BacktestPayload {
  agent: string;
  portfolio_curve: PortfolioPoint[];
  holdings: HoldingsPoint[];
  metrics: Metrics;
  provenance: Provenance;
}

export interface AgentList {
  agents: string[];
  baselines: string[];
}
```

**API client (`lib/api.ts`):**

```typescript
import type { AgentList, BacktestPayload } from "@/lib/types";

// Hardcoded for localhost demo. To change for a moving demo, edit this line.
export const BACKEND_URL = "http://localhost:8000";

export async function getAgents(): Promise<AgentList> {
  const r = await fetch(`${BACKEND_URL}/agents`);
  if (!r.ok) throw new Error(`GET /agents failed: ${r.status}`);
  return r.json();
}

export async function getBacktest(agent: string): Promise<BacktestPayload> {
  const r = await fetch(`${BACKEND_URL}/backtest/${agent}`);
  if (!r.ok) throw new Error(`GET /backtest/${agent} failed: ${r.status}`);
  return r.json();
}
```

**Color palette (`lib/colors.ts`):**

```typescript
// Deterministic name → color. Baselines gray-ish (background context);
// agents distinct hues (foreground signal). PortfolioChart uses these +
// AgentToggle chip swatches; both must agree.

export const AGENT_COLORS: Record<string, string> = {
  // Baselines — desaturated, dashed in chart
  buy_and_hold:    "#9ca3af",  // slate-400
  equal_weight:    "#6b7280",  // gray-500
  random:          "#d1d5db",  // gray-300

  // RL agents — cool blues
  ddpg:            "#3b82f6",  // blue-500
  ppo:             "#0ea5e9",  // sky-500

  // LLM agents — warm reds/oranges
  zero_shot:       "#f59e0b",  // amber-500
  single_agentic:  "#ef4444",  // red-500
  multi_agent:     "#dc2626",  // red-600 (the headline agent)
};

export const BASELINE_NAMES = new Set([
  "buy_and_hold", "equal_weight", "random",
]);

export const isBaseline = (name: string) => BASELINE_NAMES.has(name);

export const colorFor = (name: string) => AGENT_COLORS[name] ?? "#94a3b8";
```

**Number formatters (`lib/format.ts`):**

```typescript
export const formatPercent = (v: number, decimals = 1) =>
  `${v >= 0 ? "+" : ""}${(v * 100).toFixed(decimals)}%`;

export const formatVND = (v: number) => {
  // Compact form: 1_426_553 → "1.43M ₫"
  if (Math.abs(v) >= 1e9) return `${(v / 1e9).toFixed(2)}B ₫`;
  if (Math.abs(v) >= 1e6) return `${(v / 1e6).toFixed(2)}M ₫`;
  if (Math.abs(v) >= 1e3) return `${(v / 1e3).toFixed(0)}K ₫`;
  return `${v.toFixed(0)} ₫`;
};

export const formatUSD = (v: number) => `$${v.toFixed(2)}`;

export const formatDecimal = (v: number, decimals = 2) => v.toFixed(decimals);
```

**PortfolioChart pattern (`components/PortfolioChart.tsx`):**

```tsx
"use client";
import {
  CartesianGrid, Legend, Line, LineChart, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts";
import type { BacktestPayload } from "@/lib/types";
import { colorFor, isBaseline } from "@/lib/colors";
import { formatVND } from "@/lib/format";

interface Props {
  payloads: Record<string, BacktestPayload>;  // name → payload
  visible: Set<string>;
}

export function PortfolioChart({ payloads, visible }: Props) {
  // Merge per-agent curves into ONE wide dataset for Recharts:
  // [{date: "2025-05-05", buy_and_hold: 1e9, ppo: 1e9, ...}, ...]
  const dateSet = new Set<string>();
  Object.values(payloads).forEach((p) =>
    p.portfolio_curve.forEach((pt) => dateSet.add(pt.date))
  );
  const dates = Array.from(dateSet).sort();

  const merged = dates.map((date) => {
    const row: Record<string, number | string> = { date };
    for (const [name, p] of Object.entries(payloads)) {
      const pt = p.portfolio_curve.find((x) => x.date === date);
      if (pt) row[name] = pt.value;
    }
    return row;
  });

  const visibleAgents = Object.keys(payloads).filter((n) => visible.has(n));

  return (
    <ResponsiveContainer width="100%" height={400}>
      <LineChart data={merged} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
        <XAxis dataKey="date" tick={{ fontSize: 12 }} />
        <YAxis
          tickFormatter={(v) => formatVND(v)}
          tick={{ fontSize: 12 }}
          domain={["auto", "auto"]}
        />
        <Tooltip
          formatter={(value: number) => formatVND(value)}
          labelFormatter={(label) => `Date: ${label}`}
        />
        <Legend />
        {visibleAgents.map((name) => (
          <Line
            key={name}
            type="monotone"
            dataKey={name}
            stroke={colorFor(name)}
            strokeWidth={2}
            strokeDasharray={isBaseline(name) ? "5 5" : undefined}
            dot={false}
            connectNulls
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
```

**MetricsTable pattern (`components/MetricsTable.tsx`):**

```tsx
"use client";
import { useState } from "react";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import type { BacktestPayload } from "@/lib/types";
import { colorFor } from "@/lib/colors";
import { formatPercent, formatVND, formatDecimal } from "@/lib/format";

type Col = "cumulative_return" | "sharpe" | "sortino" | "max_drawdown" | "total_cost";

interface Props {
  payloads: Record<string, BacktestPayload>;
  visible: Set<string>;
}

export function MetricsTable({ payloads, visible }: Props) {
  const [sortKey, setSortKey] = useState<Col>("cumulative_return");
  const [sortDesc, setSortDesc] = useState(true);

  const rows = Object.values(payloads)
    .filter((p) => visible.has(p.agent))
    .map((p) => ({ name: p.agent, m: p.metrics }));

  rows.sort((a, b) => {
    const av = a.m[sortKey] ?? 0;
    const bv = b.m[sortKey] ?? 0;
    return sortDesc ? bv - av : av - bv;
  });

  const headerCell = (label: string, key: Col) => (
    <TableHead
      role="button"
      onClick={() => {
        if (sortKey === key) setSortDesc(!sortDesc);
        else { setSortKey(key); setSortDesc(true); }
      }}
      className="cursor-pointer select-none"
    >
      {label} {sortKey === key ? (sortDesc ? "↓" : "↑") : ""}
    </TableHead>
  );

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Agent</TableHead>
          {headerCell("Cum Return", "cumulative_return")}
          {headerCell("Sharpe", "sharpe")}
          {headerCell("Sortino", "sortino")}
          {headerCell("Max DD", "max_drawdown")}
          {headerCell("Total Cost", "total_cost")}
          <TableHead className="text-right">LLM Cost</TableHead>
          <TableHead className="text-right">Steps</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map(({ name, m }) => (
          <TableRow key={name}>
            <TableCell className="font-medium">
              <span
                className="inline-block w-3 h-3 mr-2 rounded-sm align-middle"
                style={{ backgroundColor: colorFor(name) }}
              />
              {name}
            </TableCell>
            <TableCell>{formatPercent(m.cumulative_return)}</TableCell>
            <TableCell>{formatDecimal(m.sharpe)}</TableCell>
            <TableCell>{formatDecimal(m.sortino)}</TableCell>
            <TableCell>{formatPercent(m.max_drawdown)}</TableCell>
            <TableCell>{formatVND(m.total_cost)}</TableCell>
            <TableCell className="text-right">
              {m.llm_cost_usd !== undefined ? `$${m.llm_cost_usd.toFixed(2)}` : "—"}
            </TableCell>
            <TableCell className="text-right">{m.n_steps}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
```

**AgentToggle pattern (`components/AgentToggle.tsx`):**

```tsx
"use client";
import { colorFor } from "@/lib/colors";

interface Props {
  agents: string[];        // all known
  visible: Set<string>;
  onChange: (next: Set<string>) => void;
}

export function AgentToggle({ agents, visible, onChange }: Props) {
  return (
    <div className="flex flex-wrap gap-2">
      {agents.map((name) => {
        const on = visible.has(name);
        return (
          <button
            key={name}
            type="button"
            onClick={() => {
              const next = new Set(visible);
              if (on) next.delete(name); else next.add(name);
              onChange(next);
            }}
            className={`px-3 py-1 rounded-full text-sm border transition ${
              on ? "bg-white" : "bg-gray-100 opacity-50"
            }`}
            style={{ borderColor: colorFor(name) }}
          >
            <span
              className="inline-block w-2 h-2 mr-2 rounded-full"
              style={{ backgroundColor: colorFor(name) }}
            />
            {name}
          </button>
        );
      })}
    </div>
  );
}
```

**Homepage pattern (`app/page.tsx`):**

```tsx
"use client";
import { useEffect, useState } from "react";
import {
  Card, CardContent, CardHeader, CardTitle,
} from "@/components/ui/card";
import { AgentToggle } from "@/components/AgentToggle";
import { MetricsTable } from "@/components/MetricsTable";
import { PortfolioChart } from "@/components/PortfolioChart";
import { getAgents, getBacktest } from "@/lib/api";
import type { BacktestPayload } from "@/lib/types";

export default function HomePage() {
  const [payloads, setPayloads] = useState<Record<string, BacktestPayload>>({});
  const [visible, setVisible] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const list = await getAgents();
        const all = [...list.baselines, ...list.agents];
        const results = await Promise.allSettled(all.map(getBacktest));
        const ok: Record<string, BacktestPayload> = {};
        results.forEach((r, i) => {
          if (r.status === "fulfilled") ok[all[i]] = r.value;
        });
        setPayloads(ok);
        setVisible(new Set(Object.keys(ok)));
      } catch (e) {
        setError(String(e));
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) return <p className="p-8">Loading…</p>;
  if (error) return <p className="p-8 text-red-600">Error: {error}</p>;
  if (!Object.keys(payloads).length)
    return <p className="p-8">No agents have backtest data yet.</p>;

  return (
    <main className="container mx-auto py-6 space-y-6 max-w-7xl">
      <header>
        <h1 className="text-2xl font-bold">DRL vs LLM/Agentic Trading — VN30</h1>
        <p className="text-sm text-gray-600">
          Test period 2025-05-05 → 2026-04-29 · 248 sessions ·
          {" "}{Object.keys(payloads).length} agents
        </p>
      </header>

      <Card>
        <CardHeader><CardTitle>Show / Hide Agents</CardTitle></CardHeader>
        <CardContent>
          <AgentToggle
            agents={Object.keys(payloads)}
            visible={visible}
            onChange={setVisible}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Portfolio Curve Overlay</CardTitle></CardHeader>
        <CardContent>
          <PortfolioChart payloads={payloads} visible={visible} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Metrics</CardTitle></CardHeader>
        <CardContent>
          <MetricsTable payloads={payloads} visible={visible} />
        </CardContent>
      </Card>
    </main>
  );
}
```

**Layout pattern (`app/layout.tsx`):**

```tsx
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "DRL vs LLM/Agentic Trading",
  description: "VN30 comparison dashboard",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi">
      <body className="bg-gray-50 text-gray-900 antialiased">{children}</body>
    </html>
  );
}
```

**Error handling (CLAUDE.md alignment):**

- Backend down → page shows red "Error: GET /agents failed: ..." (no fancy retry; user restarts uvicorn)
- One agent's `metrics.json` missing → `Promise.allSettled` filters, show the rest
- Cold network → loading spinner (just "Loading…" text — keep simple)
- Type drift detected → TypeScript catches at `npm run build`

---

## DESIGN DECISIONS — LOCK BEFORE IMPLEMENT

### D1. Next.js 15 App Router + strict TS

`tsconfig.json` strict + noUncheckedIndexedAccess. Build-time type checks
catch Pydantic drift.

### D2. Tailwind v3 (not v4)

`tailwindcss@^3.4` pinned. v4 broke a lot in spring 2026 betas; not worth
the risk under demo deadline.

### D3. shadcn/ui Table + Card; Recharts direct (no shadcn Chart wrapper)

shadcn writes code into `components/ui/` — owned by us. Recharts unwrapped
because the shadcn Chart wrapper adds CSS-var theming we don't need.

### D4. ALL data client-side via useEffect + fetch

Backend is localhost — server-side fetch from Next.js would fail in any
non-dev build. All page-level components are `"use client"`.

### D5. useState only (no state lib)

UI state = `Set<string>` of visible agents + `Col` sort key. Both fit
useState. Premature global state = wasted budget.

### D6. Hardcoded 8-color palette

Baselines desaturated (gray family) + dashed in chart. RL = blue family.
LLM = warm reds/orange. One single source `lib/colors.ts`.

### D7. Format helpers in lib/format.ts

`formatPercent(v, decimals=1)` always prefixes `+`. `formatVND` auto-compact
(1.43M ₫). `formatUSD` 2-decimal. Chart tooltip + table use same helpers.

### D8. AgentToggle = controlled component

Parent owns `Set<string>`. Toggle emits onChange(newSet). Single source.

### D9. ZERO JS-side tests

Manual smoke + screenshot. `npm run build` catches type errors. Save the
day budget. Add Vitest later if scope grows.

### D10. Hardcoded BACKEND_URL = "http://localhost:8000"

No env var. ONE line to edit if demo moves. Document in README.

---

## IMPLEMENTATION PLAN

### Phase 1: Scaffold + spikes (~30 min)

- Run Spike A (create-next-app)
- Run Spike B (shadcn init + add components)
- Run Spike C (CORS sanity)

### Phase 2: Foundation libs (~30 min)

- `lib/types.ts` — TS mirror
- `lib/api.ts` — typed fetch wrappers
- `lib/colors.ts` — 8-color map
- `lib/format.ts` — number formatters

### Phase 3: Components (~90 min)

- `components/PortfolioChart.tsx`
- `components/MetricsTable.tsx`
- `components/AgentToggle.tsx`

### Phase 4: Page + layout (~30 min)

- `app/layout.tsx` (replace scaffold's)
- `app/page.tsx` (replace scaffold's homepage)

### Phase 5: Smoke + screenshot (~30 min)

- Start uvicorn (PKG-11)
- Start `npm run dev`
- Open `localhost:3000` — verify chart renders, table sortable, toggle works, tooltip on hover
- `npm run build` — type-check clean
- Screenshot for PR

### Phase 6: Repo integration (~15 min)

- Update root `.gitignore` (frontend/node_modules, frontend/.next)
- Update `README.md` with frontend setup section
- Commit, PR

**Budget total: ~4 hours. With debugging buffer: 6 hours = ¾ day.**

---

## STEP-BY-STEP TASKS

### 1. RUN Spike A — scaffold

```bash
cd /home/duckk/personal/deep-rf-for-finance
npx create-next-app@latest frontend \
    --typescript --tailwind --app \
    --no-src-dir --no-git --no-import-alias --use-npm
```

- **VALIDATE:** `ls frontend/` includes `app/`, `package.json`, `tailwind.config.ts`, `tsconfig.json`.
- **GOTCHA:** If `create-next-app` prompts for additional flags, accept defaults
  (Turbopack OK, Eslint YES). Pin React/Next versions in package.json AFTER scaffold completes
  if you see `react@19.x.x` already, leave as-is.

### 2. RUN Spike B — shadcn init + components

```bash
cd /home/duckk/personal/deep-rf-for-finance/frontend
npx shadcn@latest init --yes --base-color slate
npx shadcn@latest add table card button --yes
```

- **VALIDATE:** `ls components/ui/` shows `table.tsx`, `card.tsx`, `button.tsx`.
- **GOTCHA:** shadcn writes a `components.json` + may modify `tailwind.config.ts`
  to add the slate base CSS vars. Accept; don't revert.

### 3. RUN Spike C — backend CORS sanity

```bash
cd /home/duckk/personal/deep-rf-for-finance
.venv/bin/uvicorn backend.main:app --port 8000 --log-level warning &
UV=$!
sleep 1
curl -s -H "Origin: http://localhost:3000" http://localhost:8000/agents | python -m json.tool
curl -s -i -H "Origin: http://localhost:3000" http://localhost:8000/agents 2>&1 | grep -i "access-control"
kill $UV
```

- **VALIDATE:** First curl prints `{agents: [...], baselines: [...]}`. Second
  curl shows `access-control-allow-origin: http://localhost:3000` header.

### 4. INSTALL Recharts

```bash
cd /home/duckk/personal/deep-rf-for-finance/frontend
npm install recharts@^2.13
```

- **VALIDATE:** `npm ls recharts` shows installed.
- **GOTCHA:** Recharts 3.x alpha has breaking changes; pin ^2.13 explicitly.

### 5. CREATE `frontend/lib/types.ts`

- **IMPLEMENT:** Mirror `backend/models.py` as shown in Patterns.
- **GOTCHA:** `Metrics` index signature `[key: string]: number | undefined`
  is what lets LLM extras pass through TypeScript without per-agent subtypes.

### 6. CREATE `frontend/lib/api.ts`

- **IMPLEMENT:** Two functions `getAgents()`, `getBacktest(agent)`, both throwing on non-2xx.
- **VALIDATE:** `npm run lint` clean.

### 7. CREATE `frontend/lib/colors.ts`

- **IMPLEMENT:** 8-name → hex map; `isBaseline()` helper; `colorFor()` with fallback.
- **GOTCHA:** Keep alphabetical inside groups to minimize merge friction
  if PKG-S adds agents later.

### 8. CREATE `frontend/lib/format.ts`

- **IMPLEMENT:** 4 formatters as shown.
- **GOTCHA:** `formatPercent` ALWAYS prefixes `+`/`-` — improves chart tooltip
  hierarchy ("losses are red, gains are green").

### 9. CREATE `frontend/components/AgentToggle.tsx`

- **IMPLEMENT:** Controlled component as shown.
- **GOTCHA:** `"use client"` directive REQUIRED — uses event handlers.

### 10. CREATE `frontend/components/PortfolioChart.tsx`

- **IMPLEMENT:** As shown — wide-format merge inside the component.
- **GOTCHA:** Recharts requires ResponsiveContainer wrapping; height MUST be a number
  (px) or string ("400px") — `"100%"` only works on width, NOT height (height needs explicit).
- **GOTCHA:** `connectNulls` is critical because LLM agents have only 10-11 portfolio_curve points
  vs baselines' 248 — without `connectNulls` the LLM lines render as 10 disconnected dots.

### 11. CREATE `frontend/components/MetricsTable.tsx`

- **IMPLEMENT:** Sortable shadcn Table as shown.
- **GOTCHA:** `m.llm_cost_usd !== undefined` distinguishes "missing for baselines"
  from `0.0` (e.g. cached run). Use `—` placeholder, not `$0.00`.

### 12. REPLACE `frontend/app/page.tsx`

- **IMPLEMENT:** As shown — Promise.allSettled tolerant of missing agent metrics.
- **GOTCHA:** Default visible set = all loaded agents. User toggles off via
  AgentToggle. Empty set = empty chart (acceptable UX).

### 13. REPLACE `frontend/app/layout.tsx`

- **IMPLEMENT:** Simple layout as shown; remove the scaffold's font imports if any
  errors arise (just skip `next/font` for budget).

### 14. UPDATE root `.gitignore`

- **IMPLEMENT:** Append:
  ```
  # Frontend (PKG-13+)
  frontend/node_modules/
  frontend/.next/
  frontend/out/
  frontend/build/
  frontend/.env*.local
  ```
- **VALIDATE:** `git status --ignored frontend/` shows the dirs are excluded.

### 15. SMOKE — manual

```bash
# Terminal A: backend
.venv/bin/uvicorn backend.main:app --port 8000 --log-level info

# Terminal B: frontend
cd frontend
npm run dev
# Browser → http://localhost:3000
# Verify: chart renders with 8 lines, table sortable, tooltip on hover, toggles work
```

- **VALIDATE:** Take a screenshot for PR description.

### 16. BUILD CHECK

```bash
cd frontend
npm run build
# Expected: compile success, no type errors
```

- **VALIDATE:** "✓ Compiled successfully" + zero TS errors.
- **GOTCHA:** If `next build` complains about missing `Suspense` boundaries
  for client components fetching data, wrap the page's content in `<Suspense fallback={...}>`.
  (May or may not fire — depends on Next 15 minor version.)

### 17. UPDATE `README.md` — frontend setup section

- **IMPLEMENT:** Append a new section:
  ```markdown
  ## Frontend (PKG-13+)

  Requirements: Node ≥18.18 (tested with v24.14).

  ```bash
  # First-time install (after cloning)
  cd frontend
  npm install

  # Dev (after backend is running at localhost:8000)
  npm run dev          # opens http://localhost:3000

  # Production build (smoke type checks)
  npm run build
  ```

  Backend URL is hardcoded to `http://localhost:8000` in
  `frontend/lib/api.ts`. For moving demos, edit that constant.
  ```

### 18. COMMIT + PR

```bash
cd /home/duckk/personal/deep-rf-for-finance
git add .agent/plans/pkg-13-nextjs-dashboard.md .gitignore README.md frontend/
git status  # verify no stray dotfiles
git commit -m "PKG-13: Next.js comparison dashboard
... (see Patterns)
Closes #14"
git push -u origin duc/PKG-13-frontend-dashboard
gh pr create --title "PKG-13: Next.js shell + comparison dashboard" --body "..."
```

---

## TESTING STRATEGY

### Unit tests: NONE (per D9 scope reduction)

Manual smoke + screenshot is the test. Rationale: budget is ½–1 day total;
Vitest setup alone is 2 hours; component tests for visual stuff have low
ROI vs visual inspection.

If post-MVP scope grows, candidates:
- `lib/format.test.ts` — formatter outputs
- `lib/api.test.ts` — mocked fetch
- `components/MetricsTable.test.tsx` — sort behavior

### Integration smoke (mandatory, in PR description)

```bash
# Terminal A
.venv/bin/uvicorn backend.main:app --port 8000

# Terminal B
cd frontend && npm run dev

# Browser: open http://localhost:3000
# Screenshot included in PR
# Toggle 2-3 agents off, verify chart updates
# Sort table by Sharpe asc/desc, verify
# Hover line in chart, verify tooltip
```

### Edge Cases Explicitly Covered

| # | Case | Coverage |
|---|------|----------|
| 1 | Missing metrics.json for one agent | Promise.allSettled — show rest |
| 2 | LLM agent with truncated curve (10-11 points) | `connectNulls` in Line |
| 3 | Schema drift (Pydantic field rename) | `npm run build` TS error |
| 4 | Backend down | Red "Error: ..." page |
| 5 | All toggles off | Empty chart + empty table (acceptable) |
| 6 | Number formatting (large VND, small USD) | format.ts helpers |

---

## VALIDATION COMMANDS

### Level 1: Lint + type check

```bash
cd frontend
npm run lint
npm run build  # implicit type check
```

### Level 2: Smoke

(Step 15 + Step 16)

### Level 3: Backend regression unchanged

```bash
.venv/bin/pytest tests/ 2>&1 | tail -3
# Expect: 255 passed (no change from PKG-12)
```

### Level 4: Visual confirmation (screenshot)

Open `http://localhost:3000` after both servers running. Manual:
- Hover any line → tooltip shows date + VND value
- Click a Sharpe header → table sorts
- Click toggle chip → series disappears from chart + table

### Level 5: README accurate

```bash
# Fresh-clone simulation (rm node_modules then follow README)
cd frontend
rm -rf node_modules .next
npm install
npm run dev  # serves localhost:3000
```

---

## ACCEPTANCE CRITERIA

Issue #14:
- [ ] `npm run dev` → `localhost:3000` shows chart + table
- [ ] Hover line shows tooltip with date + value
- [ ] Responsive ≥ 1280px laptop (chart uses ResponsiveContainer)
- [ ] No backend regression (255 pytest still pass)
- [ ] `npm run build` clean (no TS errors, no lint errors)

Extra (this plan):
- [ ] All 8 agents visible by default; baselines render dashed
- [ ] AgentToggle hides series from both chart + table
- [ ] MetricsTable sortable by 5 columns; default sort = cum_return desc
- [ ] README has "Frontend setup" section
- [ ] PR includes screenshot

---

## COMPLETION CHECKLIST

- [ ] Spike A/B/C results captured in PR description
- [ ] `frontend/` package scaffolded + dependencies installed
- [ ] 4 lib files (types, api, colors, format)
- [ ] 3 components (PortfolioChart, MetricsTable, AgentToggle)
- [ ] `app/layout.tsx` + `app/page.tsx` replacing scaffolded versions
- [ ] `.gitignore` updated
- [ ] `README.md` Frontend section added
- [ ] `npm run build` clean
- [ ] Smoke screenshot in PR
- [ ] PR opened, body `Closes #14`
- [ ] No Claude attribution per CLAUDE.md
- [ ] PKG-14 unblocked (shell + types + lib reusable)

---

## NOTES

### Design decisions worth flagging in PR

1. **No tests (D9)** — manual smoke + screenshot is the validation. Budget-driven, not principled. Document in PR + open follow-up issue if scope grows.
2. **Tailwind v3 (D2)** — explicit pin avoids v4 churn.
3. **Hardcoded BACKEND_URL (D10)** — demo simplicity; README documents.
4. **No state mgmt lib (D5)** — useState scales for 2 pieces of UI state.
5. **shadcn writes code (D3)** — components/ui/ owned by us; upstream-immune.
6. **connectNulls on Line (Step 10)** — LLM agents have truncated curves; without this they'd render as disconnected dots.

### Risks specific to PKG-13

| # | Risk | Mitigation |
|---|------|-----------|
| 1 | Solo dev Next.js learning curve > 1 day | Streamlit fallback documented below; CHECKPOINT 24/05 gate |
| 2 | Recharts v3 alpha released, npm picks it | Pinned `recharts@^2.13` |
| 3 | shadcn CLI prompts for non-default config | Step 2 uses `--yes` to accept defaults |
| 4 | Tailwind v4 chosen by create-next-app | Verify v3 after scaffold; downgrade if v4 |
| 5 | 8-line overlay visually cluttered | Toggle UI lets presenter narrate per layer; baselines dashed for hierarchy |
| 6 | Pydantic Metrics drift | TS strict + index signature catches at build |

### Khi gặp blocker (escalation tree)

- `npm install` fails (corporate proxy / node version) → check Node ≥18.18; clear `node_modules` + `package-lock.json`, retry
- `npx shadcn` fails — try `npx shadcn@latest` explicitly; if still fails, hand-roll a simple `<table>` (no shadcn) for MVP
- CORS error in browser → verify `backend/main.py` allow_origins includes `http://localhost:3000`; restart uvicorn
- Chart blank → check React DevTools that `payloads` state has data; verify Network tab shows 200 from `/backtest/...`
- Build TS errors on `Metrics` index signature → ensure exactly `[key: string]: number | undefined`, not `any`
- > 1 day stuck → ⚠️ **switch to Streamlit fallback** (see below)

### ⚠️ Streamlit fallback (if PKG-13 Next.js stuck > 1 day)

Single Python file `streamlit_dashboard.py` at repo root. Run with
`.venv/bin/streamlit run streamlit_dashboard.py`. Same backend endpoints,
zero JS, zero npm. Sketch:

```python
"""Emergency fallback for PKG-13 if Next.js blocked.
Run: .venv/bin/streamlit run streamlit_dashboard.py
Requires: pip install streamlit (NOT in base deps; install only if used)
"""
import json, pathlib
import pandas as pd
import streamlit as st

st.set_page_config(page_title="DRL vs LLM/Agentic Trading", layout="wide")
st.title("DRL vs LLM/Agentic Trading — VN30")
st.caption("Test period 2025-05-05 → 2026-04-29 · 248 sessions")

RESULTS = pathlib.Path("results")
payloads = {}
for p in sorted(RESULTS.glob("*/metrics.json")):
    payloads[p.parent.name] = json.loads(p.read_text())

# Toggle
visible = st.multiselect(
    "Agents", list(payloads), default=list(payloads)
)

# Chart
import altair as alt  # streamlit ships built-in alt

rows = []
for name in visible:
    for pt in payloads[name]["portfolio_curve"]:
        rows.append({"date": pt["date"], "value": pt["value"], "agent": name})
df = pd.DataFrame(rows)
df["date"] = pd.to_datetime(df["date"])

chart = (
    alt.Chart(df).mark_line().encode(
        x="date:T", y="value:Q", color="agent:N",
        tooltip=["date", "value", "agent"],
    ).properties(height=400).interactive()
)
st.altair_chart(chart, use_container_width=True)

# Table
table_rows = []
for name in visible:
    m = payloads[name]["metrics"]
    table_rows.append({
        "agent": name,
        "cum_return": m["cumulative_return"],
        "sharpe": m["sharpe"],
        "sortino": m["sortino"],
        "max_dd": m["max_drawdown"],
        "total_cost": m["total_cost"],
        "llm_cost_usd": m.get("llm_cost_usd"),
        "n_steps": m["n_steps"],
    })
table_df = pd.DataFrame(table_rows).sort_values("cum_return", ascending=False)
st.dataframe(table_df, use_container_width=True)
```

Streamlit pros: 1 file, native widgets, < 1 hour to ship.
Streamlit cons: less polish for buổi bảo vệ; PKG-14/15/16 would also need
Streamlit pages (chia thành multipage app with `pages/` dir).

**Trigger gate:** If after 1 day (~8 hours hands-on) Next.js dashboard isn't
rendering chart + table, switch. Don't sunk-cost.

### Phase 3 status after PKG-13

| PKG | Status |
|-----|--------|
| PKG-10 backtest + metrics | ✅ merged |
| PKG-11 FastAPI shell | ✅ merged |
| PKG-12 SSE live route | ✅ merged |
| **PKG-13 Next.js comparison dashboard (this PR)** | 🟡 ready after impl |
| PKG-14 Agent detail page | unblocked (shell + types + lib reusable) |
| PKG-15 Debate replay UI | unblocked (uses lib/api.ts → /debate/...) |
| PKG-16 Live mode UI | unblocked (uses /live/run from PKG-12) |
| **CHECKPOINT 24/05 (7 days out)** | **PKG-13 must ship by then OR Streamlit pivot fires** |

---

## Confidence Score

**6.5/10** for one-pass implementation.

Subtract:
- −1.0 Solo dev frontend learning curve — Next.js + Tailwind + shadcn + Recharts are 4 unfamiliar tech surfaces simultaneously
- −1.0 npm/scaffold churn — `create-next-app`, `shadcn init`, version pin drift; any one prompt mismatch = 30min debug
- −0.5 Recharts wide-merge format may surprise (`connectNulls` issue with truncated LLM curves)
- −0.5 No tests = no mechanical safety net; visual inspection only
- −0.5 shadcn CLI breaking changes between releases

Add back:
- +1.0 Backend API + types locked + already tested (255 pytest pass); contract is solid
- +0.5 Plan includes EXACT commands + EXACT versions
- +0.5 Streamlit fallback fully documented (psychological safety = better decisions under stress)

PKG-13 is the **highest-risk** package in Phase 3 by far. Path:
- Best case (~4h): spikes work first time, manual smoke pass, PR opens
- Realistic (~8h = 1 full day): spend 2h on shadcn/Tailwind quirks
- Worst case (> 1 day): switch to Streamlit fallback (~3h to ship instead)

**RECOMMEND**: Set a hard 8-hour timer. If Next.js dashboard isn't rendering
the chart by hour 8, switch to Streamlit. The thesis ships either way.
