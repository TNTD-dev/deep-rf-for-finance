# Feature: PKG-14 — Agent detail page (US-2)

> Click một agent từ dashboard → `/agents/{id}` → thấy 4 chart: portfolio
> curve, drawdown curve, holdings heatmap, metrics chi tiết. ½ day scope.
>
> PKG-14 reuses 100% backend + frontend shell shipped trong PKG-11/13.
> Không endpoint mới (`/backtest/{agent}` đã trả đủ payload), không
> setup mới, không dep mới. Chỉ thêm 1 dynamic route + 3-4 components.

## Feature Description

1 dynamic route + 4 components:

- **`app/agents/[id]/page.tsx`** — dynamic route. Client component. Read
  `id` from `params` (Next 16: `params` is a Promise, use `use(params)`).
  Fetch `getBacktest(id)`. 4 sections in Card layout:
  - **Header**: breadcrumb "← Back to dashboard", agent name, AgentBadge,
    n_steps badge
  - **Portfolio curve**: reuse `PortfolioChart` with `{[id]: payload}` +
    `new Set([id])` (no new component, see D3)
  - **Drawdown curve**: new `DrawdownChart` — Recharts Area chart, red
    fill below 0, computed client-side `dd_t = (running_max - pv_t) / running_max`
  - **Holdings heatmap**: new `HoldingsHeatmap` — SVG 5×N grid, per-ticker
    intensity normalization, hover tooltip
  - **Metrics detail**: new `AgentMetricsDetail` — 2-column key-value list
    showing ALL metrics keys (financial + LLM extras)

- **Update `components/MetricsTable.tsx`** (PKG-13 owned, minimal touch) —
  wrap agent name cell in `<Link href={\`/agents/${name}\`}>`. **File
  ownership flex documented in PR + this plan §D9.**

Acceptance criteria (Issue #15):
- Click agent từ dashboard → đến `/agents/multi_agent` thấy 4 chart
- Holdings heatmap đọc đúng 5 ticker × thời gian

## User Story

As a **thầy hướng dẫn xem demo**
I want **click agent name trên dashboard rồi thấy portfolio curve riêng +
holdings heatmap theo thời gian + drawdown chart + metrics chi tiết**
So that **hiểu được "agent này hành xử thế nào" — không chỉ Sharpe Number
mà còn timing của lệnh + risk profile**.

As a **report writer (Người 1)**
I want **screenshot per-agent detail pages cho 8 agents**
So that **báo cáo có hình minh hoạ riêng cho từng phương pháp, không
phải copy-paste từ matplotlib**.

As a **PKG-15 implementor (next package)**
I want **dynamic route convention `app/agents/[id]/` shipped và verified**
So that **PKG-15 `app/debate/[date]/` route follows same pattern, không
debug Next 16 quirks lần nữa**.

## Problem Statement

5 challenges:

1. **Next 16 dynamic route `params` is a Promise** (breaking change từ
   Next 14→15→16). In client components phải dùng `use(params)` từ React.
   **Solution:** Pattern locked in plan; spike A verifies the syntax
   compiles + renders.
2. **PKG-13 file ownership boundary vs Issue #15 acceptance ("click agent
   từ dashboard")** — Issue REQUIRES homepage→detail navigation. Strictly
   keeping PKG-13's MetricsTable untouched means user has to type URL
   manually. **Solution (D9):** Accept minimal touch on
   `components/MetricsTable.tsx` (wrap agent name in `<Link>`). Document
   deviation in PR.
3. **Holdings values are HUGE integers** (~3.3M for VCB shares). Spike B
   confirmed env stores raw share count. Global normalization would dim
   VCB next to HPG (~9M). **Solution:** Per-ticker normalization — each
   row (ticker) has its own intensity scale.
4. **Heatmap = 5 tickers × 248 sessions = 1240 cells**. Rendering as
   1240 React JSX nodes = slow virtual DOM diff on re-render. **Solution:**
   Single inline `<svg>` with 1240 `<rect>` children — Vanilla SVG, no
   React reconciliation per cell, fast. Tailwind controls outer styling
   only.
5. **Drawdown formula must MATCH PKG-10**. Spike B confirmed
   `dd_t = (running_max - pv_t) / running_max` produces 19.7093% for
   buy_and_hold (matches PKG-10 `compute_max_drawdown`). **Solution:**
   Inline computation in `DrawdownChart` from `portfolio_curve` array.

## Solution Statement

10 design decisions LOCK before code:

- **D1.** **Dynamic route via `app/agents/[id]/page.tsx`** with `"use client"`
  + `use(params)` from React. `id` = agent name (string).
- **D2.** **Client-side fetch via existing `getBacktest(id)`** from
  `lib/api.ts`. Same pattern as homepage `useEffect`. NO new endpoint.
- **D3.** **Reuse `PortfolioChart` for single-agent display.** Wrap payload
  in `{[id]: payload}` + `new Set([id])`. NO new SingleAgentChart needed.
  Existing component handles single-line case fine (legend shows 1 series).
- **D4.** **`DrawdownChart` — Recharts Area** (not Line) with `fill="#ef4444"
  fillOpacity={0.2} stroke="#dc2626"`. Inline drawdown computation from
  `portfolio_curve`. Y-axis percent.
- **D5.** **`HoldingsHeatmap` — single SVG with `<rect>` cells.**
  - Per-ticker max normalization: `opacity = value / max(row)`
  - Color: `fill="#059669"` (emerald-600) + opacity 0–1
  - Cell size: 5px wide × 28px tall (5px × 248 sessions = 1240px fits
    `max-w-7xl` container; 28px tall × 5 tickers = 140px chart height)
  - Tooltip: native SVG `<title>` element on each rect (zero JS)
  - Y-axis labels: ticker names left of grid
  - X-axis labels: month markers (every ~21st cell)
- **D6.** **`AgentMetricsDetail` — 2-column grid.** Iterate `Object.entries(metrics)`
  + format value by key heuristic (`*_return | *_drawdown | *_rate` → percent;
  `total_cost` → VND; `llm_cost_usd` → USD; everything else → decimal).
- **D7.** **`AgentBadge` — small pill component.** 3 types: `baseline` (gray),
  `rl` (blue), `llm` (red). Detect via name lookup (BASELINE_NAMES + RL set +
  LLM set in `lib/colors.ts` or new `lib/agent-category.ts`). Plan: add to
  `lib/colors.ts` since color map already lives there.
- **D8.** **Link from homepage MetricsTable agent cell** via `<Link
  href={\`/agents/${name}\`}>` — minimal PKG-13 touch (1 file, ~3 lines).
- **D9.** **File ownership deviation documented.** PR body section
  "Touched PKG-13 file: MetricsTable.tsx — wrapped agent name in Link to
  enable Issue #15 acceptance". Surface so reviewer sees clearly.
- **D10.** **Loading + error states match homepage pattern.** Same
  `"Loading…"` text + red "Error: ..." block with backend URL hint. Keep
  UX consistent across pages.

## Feature Metadata

- **Feature Type:** New Capability (first secondary route; unblocks PKG-15
  debate page convention)
- **Estimated Complexity:** **Low-Medium** — ½ day; heaviest piece is the
  heatmap SVG layout
- **Primary Systems Affected:**
  - New: `frontend/app/agents/[id]/page.tsx`
  - New: `frontend/components/{HoldingsHeatmap, DrawdownChart, AgentMetricsDetail, AgentBadge}.tsx`
  - Update: `frontend/components/MetricsTable.tsx` (D8 — wrap agent name in Link)
  - Update: `frontend/lib/colors.ts` (D7 — add `agentCategory(name)` helper)
- **Dependencies:** No new npm packages — Recharts (already installed)
  handles Area chart; SVG is vanilla.

---

## CONTEXT REFERENCES

### Relevant Codebase Files — ĐỌC TRƯỚC KHI IMPLEMENT

**Frontend shell to inherit (PKG-13):**

- `frontend/app/page.tsx:18-37` — `useEffect` + `Promise.allSettled` fetch
  pattern; loading/error/empty states. Mirror in `app/agents/[id]/page.tsx`
  (single fetch instead of N).
- `frontend/components/PortfolioChart.tsx` — reusable as-is with `{[id]: payload}`.
  Verify legend shows 1 line correctly when called with single-key payloads.
- `frontend/components/MetricsTable.tsx:62-82` — current first cell:
  `<TableCell><span className="inline-flex ..."><span color/>...{name}</span></TableCell>`.
  Wrap `{name}` text in `<Link href={\`/agents/${name}\`}>`.
- `frontend/lib/colors.ts` — `AGENT_COLORS`, `BASELINE_NAMES`, `isBaseline`,
  `colorFor`. Add `agentCategory(name): "baseline" | "rl" | "llm"`.
- `frontend/lib/format.ts` — `formatPercent`, `formatVND`, `formatUSD`,
  `formatDecimal`. AgentMetricsDetail dispatches by key heuristic.
- `frontend/lib/types.ts:31-44` — `Metrics` interface with index signature.
  AgentMetricsDetail iterates `Object.entries(metrics)`.
- `frontend/lib/api.ts:14-17` — `getBacktest(agent)` Promise<BacktestPayload>.

**Backend contract (PKG-10/11 — read-only):**

- `backend/models.py:42-49` — `BacktestPayload {agent, portfolio_curve,
  holdings, metrics, provenance}`. Already complete; PKG-14 consumes verbatim.
- `backend/routes/backtest.py` — `GET /backtest/{agent}` returns full
  payload. No changes needed.
- `src/eval/metrics.py:65-72` — `compute_max_drawdown` Python reference:
  ```python
  running_max = np.maximum.accumulate(pv)
  dd = (running_max - pv) / np.maximum(running_max, 1e-12)
  return float(dd.max())
  ```
  TypeScript port computes the same dd array (not just the max) for the chart.

**Data shape evidence (Spike B verified):**

```
buy_and_hold metrics.json:
  portfolio_curve: 248 points
  holdings: 248 rows like {"date":"2025-05-06","VCB":3349100,"FPT":2049600,...}
  PKG-10 max_drawdown = 19.7093%
  Reconstructed from JS-port formula = 19.7093% (identical)

multi_agent metrics.json:
  portfolio_curve: 5 points (smoke run)
  holdings: 5 rows; first row all-zero (initial), rest non-zero
  PKG-10 max_drawdown = 0.2915%, reconstructed = 0.2915%
```

**Existing prototype (visual reference):**

- `.agent/prototypes/prototype-pkg-13.html` — design language baseline;
  PKG-14 reuses Card/border/shadow + slate base color scheme.

**Don't touch (file ownership):**

- `backend/` — owned by PKG-11/12
- `src/` — research layer
- `frontend/app/page.tsx` — homepage owned by PKG-13
- `frontend/components/{PortfolioChart, AgentToggle}.tsx` — PKG-13
- `frontend/app/debate/`, `frontend/app/live/` — PKG-15/16

**Flexed (documented deviation):**

- `frontend/components/MetricsTable.tsx` — wrap agent name in Link only.
  PR body calls this out (D9).

### New Files to Create

```
frontend/
├── app/
│   └── agents/
│       └── [id]/
│           └── page.tsx               # dynamic route, 4-card detail layout
└── components/
    ├── HoldingsHeatmap.tsx           # SVG 5×N grid, per-ticker normalization
    ├── DrawdownChart.tsx              # Recharts AreaChart, red fill
    ├── AgentMetricsDetail.tsx         # 2-col key-value, format by key heuristic
    └── AgentBadge.tsx                 # pill: baseline / rl / llm

Modify (PKG-13 ownership flex):
└── components/MetricsTable.tsx        # wrap agent name in <Link>
└── lib/colors.ts                      # add agentCategory() helper
```

### Relevant Documentation — ĐỌC TRƯỚC KHI IMPLEMENT

- **Next 16 Dynamic Routes** (LOCAL):
  `frontend/node_modules/next/dist/docs/01-app/03-api-reference/03-file-conventions/dynamic-routes.md`
  - Key fact: `params` is Promise; client components use `use(params)`.
  - Why: PKG-14 route signature
- **React `use()` hook**: https://react.dev/reference/react/use
  - For unwrapping Promise in client components
- **Recharts AreaChart**: https://recharts.org/en-US/api/AreaChart
  - `<Area type="monotone" dataKey="dd" fill="#ef4444" fillOpacity={0.2} stroke="#dc2626" />`
- **Next 16 `<Link>`**: https://nextjs.org/docs/app/api-reference/components/link
  - Default behavior: client-side nav, prefetch on viewport visibility
- **SVG `<rect>` + `<title>`**: https://developer.mozilla.org/en-US/docs/Web/SVG/Element/title
  - Native browser tooltip on hover, no JS needed

### Pre-implementation spikes

**Spike A — Next 16 dynamic route + params Promise:**

```bash
cd /home/duckk/personal/deep-rf-for-finance/frontend
mkdir -p app/agents/_spike/[id]
cat > app/agents/_spike/[id]/page.tsx <<'TSX'
"use client";
import { use } from "react";

export default function SpikePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  return <div className="p-8">spike id = {id}</div>;
}
TSX
npm run build 2>&1 | tail -10
# Expected: compile success, /agents/_spike/[id] in routes table
rm -rf app/agents/_spike
```

Expected: "✓ Compiled successfully" + route `/agents/_spike/[id]` listed.
Confirms params-as-Promise pattern compiles cleanly.

**Spike B — Drawdown formula port + heatmap normalization (ALREADY RUN):**

```bash
.venv/bin/python <<'PY'
"""Verify drawdown formula matches PKG-10 + inspect holdings."""
import json, numpy as np, pathlib
for name in ["buy_and_hold", "multi_agent"]:
    p = pathlib.Path(f"results/{name}/metrics.json")
    payload = json.loads(p.read_text())
    pv = np.array([pt["value"] for pt in payload["portfolio_curve"]], float)
    rm = np.maximum.accumulate(pv)
    dd = (rm - pv) / np.maximum(rm, 1e-12)
    print(f"{name}: max_dd={float(dd.max()):.4%} vs PKG-10 {payload['metrics']['max_drawdown']:.4%}")
PY
```

Expected (verified): both names match PKG-10 to 4 decimal places.

**Spike C — Heatmap rendering perf with 1240 cells:**

```bash
cd /home/duckk/personal/deep-rf-for-finance/frontend
mkdir -p app/agents/_heatmap-spike
cat > app/agents/_heatmap-spike/page.tsx <<'TSX'
"use client";
export default function Spike() {
  const cells = [];
  for (let t = 0; t < 5; t++) {
    for (let i = 0; i < 248; i++) {
      cells.push(
        <rect
          key={`${t}-${i}`}
          x={i * 5} y={t * 28} width={5} height={28}
          fill="#059669" fillOpacity={(i * t) / (248 * 5)}
        />
      );
    }
  }
  return (
    <div className="p-8">
      <svg width={1240} height={140}>{cells}</svg>
      <p>rendered {cells.length} rects</p>
    </div>
  );
}
TSX
npm run build 2>&1 | tail -5
# Expected: compiles. Visual perf only verifiable with browser.
rm -rf app/agents/_heatmap-spike
```

Expected: build succeeds. Rendering 1240 SVG rects in a single tree is
< 16ms on a laptop — well under the 60fps budget. Confirms approach is
viable.

### Patterns to Follow

**Dynamic route page (`app/agents/[id]/page.tsx`):**

```tsx
"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";

import { AgentBadge } from "@/components/AgentBadge";
import { AgentMetricsDetail } from "@/components/AgentMetricsDetail";
import { DrawdownChart } from "@/components/DrawdownChart";
import { HoldingsHeatmap } from "@/components/HoldingsHeatmap";
import { PortfolioChart } from "@/components/PortfolioChart";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { BACKEND_URL, getBacktest } from "@/lib/api";
import type { BacktestPayload } from "@/lib/types";

export default function AgentDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const [payload, setPayload] = useState<BacktestPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        setPayload(await getBacktest(id));
      } catch (e) {
        setError(String(e));
      } finally {
        setLoading(false);
      }
    })();
  }, [id]);

  if (loading) return <p className="p-8 text-gray-600">Loading {id}…</p>;
  if (error) {
    return (
      <div className="p-8">
        <p className="text-red-700 font-semibold">Error: {error}</p>
        <p className="text-sm text-gray-600 mt-2">
          Backend at <code>{BACKEND_URL}</code> may be down.
        </p>
        <Link href="/" className="text-blue-600 underline mt-4 inline-block">
          ← Back to dashboard
        </Link>
      </div>
    );
  }
  if (!payload) return <p className="p-8">No data for {id}.</p>;

  const single = { [id]: payload };
  const visible = new Set([id]);

  return (
    <main className="container mx-auto max-w-7xl space-y-6 px-4 py-6">
      <header className="border-b border-gray-200 pb-4">
        <Link href="/" className="text-sm text-blue-600 hover:underline">
          ← Back to dashboard
        </Link>
        <div className="mt-2 flex items-center gap-3">
          <h1 className="text-2xl font-bold tracking-tight">{id}</h1>
          <AgentBadge name={id} />
          <span className="text-sm text-gray-600">
            {payload.metrics.n_steps} sessions
          </span>
        </div>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold text-gray-700">
            Portfolio Curve
          </CardTitle>
        </CardHeader>
        <CardContent>
          <PortfolioChart payloads={single} visible={visible} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold text-gray-700">
            Drawdown (%)
          </CardTitle>
        </CardHeader>
        <CardContent>
          <DrawdownChart payload={payload} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold text-gray-700">
            Holdings Heatmap
          </CardTitle>
        </CardHeader>
        <CardContent>
          <HoldingsHeatmap payload={payload} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold text-gray-700">
            Metrics Detail
          </CardTitle>
        </CardHeader>
        <CardContent>
          <AgentMetricsDetail metrics={payload.metrics} />
        </CardContent>
      </Card>
    </main>
  );
}
```

**DrawdownChart (`components/DrawdownChart.tsx`):**

```tsx
"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatPercent } from "@/lib/format";
import type { BacktestPayload } from "@/lib/types";

interface Props {
  payload: BacktestPayload;
}

export function DrawdownChart({ payload }: Props) {
  // Port of src/eval/metrics.py:compute_max_drawdown — dd_t = (rm - pv) / rm
  let runningMax = -Infinity;
  const data = payload.portfolio_curve.map((pt) => {
    runningMax = Math.max(runningMax, pt.value);
    const dd = runningMax > 0 ? -(runningMax - pt.value) / runningMax : 0;
    // Negate so drawdown plots BELOW zero — visually intuitive
    return { date: pt.date, dd };
  });

  return (
    <ResponsiveContainer width="100%" height={300}>
      <AreaChart data={data} margin={{ top: 10, right: 20, left: 20, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
        <XAxis dataKey="date" tick={{ fontSize: 11 }} minTickGap={40} />
        <YAxis
          tickFormatter={(v) => formatPercent(v, 0)}
          tick={{ fontSize: 11 }}
          domain={["auto", 0]}
          width={60}
        />
        <Tooltip
          formatter={(value: number) => formatPercent(value, 2)}
          labelFormatter={(label) => `Date: ${label}`}
          contentStyle={{ fontSize: 12 }}
        />
        <Area
          type="monotone"
          dataKey="dd"
          stroke="#dc2626"
          fill="#ef4444"
          fillOpacity={0.2}
          isAnimationActive={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
```

**HoldingsHeatmap (`components/HoldingsHeatmap.tsx`):**

```tsx
"use client";

import type { BacktestPayload } from "@/lib/types";

interface Props {
  payload: BacktestPayload;
}

const CELL_W = 5;
const CELL_H = 28;
const LABEL_W = 50;
const FILL = "#059669"; // emerald-600

export function HoldingsHeatmap({ payload }: Props) {
  const tickers = Object.keys(payload.holdings[0] ?? {}).filter(
    (k) => k !== "date",
  );
  const dates = payload.holdings.map((h) => h.date);
  const N = dates.length;

  // Per-ticker max (normalize each row independently so small absolute
  // VCB doesn't get washed out by huge HPG share counts).
  const perTickerMax: Record<string, number> = {};
  for (const t of tickers) {
    let m = 0;
    for (const row of payload.holdings) {
      const v = Number(row[t] ?? 0);
      if (v > m) m = v;
    }
    perTickerMax[t] = m || 1;
  }

  const totalW = LABEL_W + N * CELL_W;
  const totalH = tickers.length * CELL_H;

  return (
    <div className="overflow-x-auto">
      <svg width={totalW} height={totalH + 18} className="text-xs">
        {tickers.map((t, row) => (
          <g key={t}>
            <text
              x={0}
              y={row * CELL_H + CELL_H / 2 + 4}
              fontSize="11"
              fill="#374151"
            >
              {t}
            </text>
            {payload.holdings.map((h, i) => {
              const v = Number(h[t] ?? 0);
              const opacity = v / perTickerMax[t];
              return (
                <rect
                  key={`${t}-${i}`}
                  x={LABEL_W + i * CELL_W}
                  y={row * CELL_H}
                  width={CELL_W}
                  height={CELL_H - 1}
                  fill={FILL}
                  fillOpacity={opacity}
                >
                  <title>{`${t} on ${h.date}: ${v.toLocaleString()} shares`}</title>
                </rect>
              );
            })}
          </g>
        ))}
        {/* X-axis: tick every ~21 sessions (≈ monthly) */}
        {dates.map((d, i) =>
          i % 21 === 0 ? (
            <text
              key={d}
              x={LABEL_W + i * CELL_W}
              y={totalH + 14}
              fontSize="10"
              fill="#6b7280"
            >
              {d.slice(0, 7)}
            </text>
          ) : null,
        )}
      </svg>
      <p className="mt-2 text-xs text-gray-500">
        Color intensity = share count, normalized per ticker (independent
        scale per row). Hover a cell for exact count.
      </p>
    </div>
  );
}
```

**AgentMetricsDetail (`components/AgentMetricsDetail.tsx`):**

```tsx
"use client";

import { formatDecimal, formatPercent, formatUSD, formatVND } from "@/lib/format";
import type { Metrics } from "@/lib/types";

interface Props {
  metrics: Metrics;
}

// Format dispatcher — key heuristic determines unit
function formatMetric(key: string, value: number | undefined): string {
  if (value === undefined) return "—";
  if (key.endsWith("_return") || key.endsWith("_drawdown") || key.endsWith("_rate")) {
    return formatPercent(value, 2);
  }
  if (key === "total_cost") return formatVND(value);
  if (key === "llm_cost_usd") return formatUSD(value);
  if (key === "n_steps" || key === "n_decisions" || key === "node_errors_total") {
    return value.toLocaleString();
  }
  if (key === "cached_tokens" || key === "llm_calls") {
    return value.toLocaleString();
  }
  if (key.endsWith("_s")) return `${formatDecimal(value)}s`;
  return formatDecimal(value, 3);
}

function prettyKey(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function AgentMetricsDetail({ metrics }: Props) {
  const entries = Object.entries(metrics).filter(
    ([, v]) => v !== undefined && v !== null,
  );
  return (
    <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {entries.map(([k, v]) => (
        <div key={k} className="border-b border-gray-100 pb-2">
          <dt className="text-xs text-gray-600">{prettyKey(k)}</dt>
          <dd className="text-sm font-medium text-gray-900 tabular-nums">
            {formatMetric(k, v as number | undefined)}
          </dd>
        </div>
      ))}
    </dl>
  );
}
```

**AgentBadge (`components/AgentBadge.tsx`):**

```tsx
"use client";

import { agentCategory } from "@/lib/colors";

interface Props {
  name: string;
}

const STYLES: Record<string, string> = {
  baseline: "bg-gray-100 text-gray-700",
  rl: "bg-blue-100 text-blue-800",
  llm: "bg-red-100 text-red-800",
};

export function AgentBadge({ name }: Props) {
  const cat = agentCategory(name);
  return (
    <span
      className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${STYLES[cat] ?? "bg-gray-100 text-gray-700"}`}
    >
      {cat.toUpperCase()}
    </span>
  );
}
```

**`lib/colors.ts` addition:**

```typescript
// Existing exports stay; add at bottom:
const RL_NAMES = new Set(["ddpg", "ppo"]);
const LLM_NAMES = new Set(["zero_shot", "single_agentic", "multi_agent"]);

export type AgentCategory = "baseline" | "rl" | "llm";

export function agentCategory(name: string): AgentCategory {
  if (BASELINE_NAMES.has(name)) return "baseline";
  if (RL_NAMES.has(name)) return "rl";
  if (LLM_NAMES.has(name)) return "llm";
  return "baseline"; // fallback
}
```

**`MetricsTable.tsx` minimal link patch:**

Replace the agent name span:

```tsx
// BEFORE (PKG-13)
<TableCell className="font-medium">
  <span className="inline-flex items-center gap-2">
    <span className="inline-block h-3 w-3 rounded-sm" style={{ backgroundColor: colorFor(name) }} />
    {name}
  </span>
</TableCell>

// AFTER (PKG-14, minimal flex)
<TableCell className="font-medium">
  <Link href={`/agents/${name}`} className="inline-flex items-center gap-2 hover:underline">
    <span className="inline-block h-3 w-3 rounded-sm" style={{ backgroundColor: colorFor(name) }} />
    {name}
  </Link>
</TableCell>
```

Add `import Link from "next/link";` at top.

**Error handling (CLAUDE.md alignment):**

- Backend down → page shows red "Error: ..." + breadcrumb back to home
- 404 from `/backtest/{id}` (unknown agent) → red error, message
  "GET /backtest/foo failed: 404"
- Empty holdings array → heatmap shows just labels, no cells (defensive
  early return when `tickers.length === 0`)
- Empty portfolio_curve → drawdown shows empty chart (Recharts handles)

---

## DESIGN DECISIONS — LOCK BEFORE IMPLEMENT

### D1. Dynamic route `app/agents/[id]/page.tsx` with `use(params)`

Next 16 params is a Promise. Client component uses React's `use()` to
unwrap. Spike A verifies the pattern compiles.

### D2. Client-side fetch via `getBacktest(id)`

Same `useEffect` pattern as homepage. NO new endpoint, NO SSR (backend
is localhost).

### D3. Reuse PortfolioChart

Wrap `{[id]: payload}` + `new Set([id])`. NO new SingleAgentChart.
Existing component handles single-line legend correctly.

### D4. DrawdownChart = Recharts AreaChart, negated values

dd values stored negative so chart plots below 0 — intuitive. Y-axis
domain `["auto", 0]`. Red fill at 20% opacity, stroke at 100%.

### D5. HoldingsHeatmap = single inline SVG

1240 `<rect>` cells. Per-ticker max normalization (each row's intensity
0-1 independent of other tickers). Native `<title>` for hover tooltip.
NO React reconciliation per cell.

### D6. AgentMetricsDetail = 2-col list with format dispatcher

Format by key suffix: `*_return | *_drawdown | *_rate` → percent;
`total_cost` → VND; `llm_cost_usd` → USD; `*_s` → seconds; integer keys
→ locale string; else → decimal.

### D7. AgentBadge in colors.ts

Add `agentCategory(name)` helper to existing `lib/colors.ts` (logical
home — already houses BASELINE_NAMES + color logic).

### D8. Link from MetricsTable agent name cell

Wrap `{name}` text in `<Link href={\`/agents/${name}\`}>`. Adds 1 import
+ 3-line cell change. Minimal touch.

### D9. PKG-13 file ownership deviation: ACCEPTED + documented

Strict ownership = user types URLs manually. Issue #15 acceptance says
"click agent from dashboard". Accept the touch. PR body has explicit
"Touched PKG-13 file: MetricsTable.tsx" section to surface the deviation
for reviewer.

### D10. Loading + error states match homepage

Same `<p className="p-8 text-gray-600">Loading…</p>` + same red Error
block. UX consistency across pages.

---

## IMPLEMENTATION PLAN

### Phase 1: Spikes (~15 min)

- Spike A: dynamic route `_spike` test compiles
- Spike B: drawdown formula port (ALREADY VERIFIED via Python)
- Spike C: heatmap perf 1240 cells

### Phase 2: Lib additions (~10 min)

- `lib/colors.ts` — add RL_NAMES, LLM_NAMES, agentCategory

### Phase 3: Components (~60 min)

- `components/AgentBadge.tsx` — simplest, do first to verify chain
- `components/DrawdownChart.tsx` — Recharts AreaChart
- `components/HoldingsHeatmap.tsx` — SVG grid
- `components/AgentMetricsDetail.tsx` — dl grid

### Phase 4: Dynamic route + MetricsTable patch (~30 min)

- `app/agents/[id]/page.tsx` — layout + fetch + 4 cards
- Patch `components/MetricsTable.tsx` (add Link import + wrap name cell)

### Phase 5: Smoke + screenshot (~15 min)

- `npm run build` clean
- Start backend + `npm run dev`
- Navigate `/` → click agent → `/agents/{name}` → verify 4 cards render
- Screenshot for PR

**Budget total: ~2 hours hands-on; ½ day with breaks/buffer.**

---

## STEP-BY-STEP TASKS

### 1. RUN Spike A — dynamic route compiles

```bash
cd /home/duckk/personal/deep-rf-for-finance/frontend
mkdir -p app/agents/_spike/[id]
cat > app/agents/_spike/[id]/page.tsx <<'TSX'
"use client";
import { use } from "react";
export default function SpikePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return <div className="p-8">spike id = {id}</div>;
}
TSX
npm run build 2>&1 | tail -10
rm -rf app/agents/_spike
```

- **VALIDATE:** "✓ Compiled successfully" + route `/agents/_spike/[id]` in routes table.
- **GOTCHA:** If "params should be awaited" warning fires at build, switch
  to `await params` (no `use()`) — but page must then be `async` server
  component. Plan path uses client component + `use()` since we need
  state (useEffect for fetch).

### 2. RUN Spike B — drawdown formula (ALREADY VERIFIED)

(Verified during planning. Skip if confidence is high; rerun if doubt.)

### 3. RUN Spike C — heatmap 1240 cells perf

```bash
cd /home/duckk/personal/deep-rf-for-finance/frontend
mkdir -p app/agents/_heatmap-spike
cat > app/agents/_heatmap-spike/page.tsx <<'TSX'
"use client";
export default function Spike() {
  const cells = [];
  for (let t = 0; t < 5; t++) {
    for (let i = 0; i < 248; i++) {
      cells.push(
        <rect key={`${t}-${i}`} x={i*5} y={t*28} width={5} height={28}
              fill="#059669" fillOpacity={(i*t)/(248*5)} />
      );
    }
  }
  return <div className="p-8"><svg width={1240} height={140}>{cells}</svg></div>;
}
TSX
npm run build 2>&1 | tail -5
rm -rf app/agents/_heatmap-spike
```

- **VALIDATE:** Build succeeds. (Visual perf only verifiable in browser.)

### 4. UPDATE `frontend/lib/colors.ts` — add agentCategory

Append at the bottom:

```typescript
const RL_NAMES = new Set(["ddpg", "ppo"]);
const LLM_NAMES = new Set(["zero_shot", "single_agentic", "multi_agent"]);

export type AgentCategory = "baseline" | "rl" | "llm";

export function agentCategory(name: string): AgentCategory {
  if (BASELINE_NAMES.has(name)) return "baseline";
  if (RL_NAMES.has(name)) return "rl";
  if (LLM_NAMES.has(name)) return "llm";
  return "baseline";
}
```

- **VALIDATE:** `cd frontend && npm run lint` clean.

### 5. CREATE `frontend/components/AgentBadge.tsx`

- **IMPLEMENT:** As shown in Patterns.
- **VALIDATE:** Compiles via `npm run build`.

### 6. CREATE `frontend/components/DrawdownChart.tsx`

- **IMPLEMENT:** As shown.
- **GOTCHA #1:** Negate dd values so chart plots below 0. Y-axis domain
  `["auto", 0]` constrains visual.
- **GOTCHA #2:** `formatPercent` already prefixes `+`/`-`; the negated
  values will display with `-` natively — correct.

### 7. CREATE `frontend/components/HoldingsHeatmap.tsx`

- **IMPLEMENT:** As shown.
- **GOTCHA #1:** Ticker keys order from `Object.keys(payload.holdings[0])`
  is insertion order from PKG-10's `build_payload` (`item["date"]` first,
  then config.TICKERS order: VCB, FPT, HPG, VIC, VNM). Filter removes
  "date" — remaining 5 in fixed order ✓.
- **GOTCHA #2:** Empty `payload.holdings` (no data) → defensive early
  return: `if (tickers.length === 0) return <p>No holdings data.</p>;`.
- **GOTCHA #3:** `fillOpacity` capped at 1.0 — `perTickerMax || 1` guards
  div-by-zero (all-zero row → opacity 0 = invisible).

### 8. CREATE `frontend/components/AgentMetricsDetail.tsx`

- **IMPLEMENT:** As shown.
- **GOTCHA:** `Object.entries(metrics)` includes inherited index-signature
  keys; filter out undefined / null. Index signature might also surface
  the named-field keys themselves as own props — both are fine.

### 9. CREATE `frontend/app/agents/[id]/page.tsx`

- **IMPLEMENT:** As shown — 4 cards.
- **GOTCHA #1:** `useEffect` dependency = `[id]` so navigating between
  agents refetches.
- **GOTCHA #2:** `const single = { [id]: payload }` is recreated every
  render — fine because PortfolioChart does shallow re-render only when
  data length changes. If perf regresses, wrap in `useMemo`.

### 10. UPDATE `frontend/components/MetricsTable.tsx` — wrap agent name in Link

- **IMPLEMENT:**
  - Add at top: `import Link from "next/link";`
  - Replace agent cell's `<span className="inline-flex...">{...}</span>`
    with `<Link href={\`/agents/${name}\`} className="inline-flex items-center gap-2 hover:underline">{...}</Link>`
- **GOTCHA:** Keep the colored swatch span inside the Link (nested);
  Link still renders an `<a>` tag, child layout intact.
- **DOCUMENT in PR**: "Touched PKG-13 MetricsTable.tsx — wrap agent name
  in Link to enable Issue #15 navigation acceptance".

### 11. BUILD + SMOKE

```bash
cd /home/duckk/personal/deep-rf-for-finance/frontend
npm run lint
npm run build
```

- **VALIDATE:** Both clean. Build output shows `/agents/[id]` in routes table.

### 12. LIVE SMOKE

```bash
# Terminal A
cd /home/duckk/personal/deep-rf-for-finance
.venv/bin/uvicorn backend.main:app --port 8000 --log-level warning

# Terminal B
cd frontend && npm run dev

# Browser: http://localhost:3000
# Click "multi_agent" in metrics table → /agents/multi_agent
# Verify: 4 cards visible (Portfolio, Drawdown, Heatmap, Metrics)
# Hover heatmap cell → tooltip "VCB on 2025-05-06: 3,172,900 shares"
# Click "← Back to dashboard" → home loads
# Click "buy_and_hold" → /agents/buy_and_hold — heatmap shows 248 cols
```

- **VALIDATE:** Screenshot for PR.

### 13. COMMIT + PR

```bash
git add .agent/plans/pkg-14-agent-detail-page.md frontend/
git status   # verify what's staged
git commit -m "PKG-14: Agent detail page ... (see Patterns)"
git push -u origin duc/PKG-14-frontend-detail
gh pr create --title "PKG-14: Agent detail page" --body "..."
```

PR body MUST include:
- D9 documentation: "Touched PKG-13 MetricsTable.tsx — minimal Link wrap"
- Screenshot
- Spike A/C results

---

## TESTING STRATEGY

### Unit tests: NONE (continuing PKG-13's D9 zero-test convention)

Manual smoke + screenshot. `npm run build` catches type errors.

### Integration smoke (mandatory, in PR description)

```bash
# Backend + frontend running
# Browser: navigate / → click multi_agent → /agents/multi_agent
# Visual check:
# - 4 cards visible
# - Portfolio chart shows 1 line (the agent's color)
# - Drawdown shows red filled area going below 0
# - Heatmap shows 5 rows × N cells (N varies per agent)
# - Metrics detail lists ALL keys (including LLM extras for multi_agent)
# - "← Back to dashboard" works
```

### Edge Cases Explicitly Covered

| # | Case | Coverage |
|---|------|----------|
| 1 | Unknown agent (typo URL) | Error message + back link |
| 2 | Empty holdings | Defensive early return in HoldingsHeatmap |
| 3 | All-zero holdings row | `perTickerMax || 1` div-by-zero guard |
| 4 | LLM agent with extras (multi_agent) | AgentMetricsDetail shows extras |
| 5 | Smoke run agent with 5 sessions | Heatmap shows 5 cols (compact) |
| 6 | Full run agent with 248 sessions | Heatmap shows 248 cols (wide, scrolls) |
| 7 | Backend down | Red error + back link |

---

## VALIDATION COMMANDS

### Level 1: Lint + type check

```bash
cd frontend && npm run lint && npm run build
```

### Level 2: Smoke

(Step 12 manual browser)

### Level 3: Backend regression unchanged

```bash
.venv/bin/pytest tests/ 2>&1 | tail -3
# Expect: 255 passed (no backend changes)
```

### Level 4: Visual confirmation

Open `http://localhost:3000/agents/multi_agent` after both servers
running. Verify all 4 cards + heatmap tooltip + back link work.

---

## ACCEPTANCE CRITERIA

Issue #15:
- [ ] Click agent từ dashboard → `/agents/multi_agent` loads with 4 charts
- [ ] Holdings heatmap đọc đúng 5 ticker × thời gian (verify hover tooltip)
- [ ] `npm run lint && npm run build` clean
- [ ] Backend regression unchanged (255 pytest)

Extra (this plan):
- [ ] AgentBadge shows correct category (Baseline/RL/LLM)
- [ ] DrawdownChart plots below 0 with red fill
- [ ] AgentMetricsDetail surfaces LLM extras for multi_agent (llm_cost,
      avg_latency, debate_rounds)
- [ ] PR documents D9 file ownership deviation explicitly
- [ ] PR includes screenshot of /agents/multi_agent

---

## COMPLETION CHECKLIST

- [ ] Spikes A + C run + cleaned up
- [ ] `lib/colors.ts` patched with `agentCategory()`
- [ ] 4 new components (AgentBadge, DrawdownChart, HoldingsHeatmap, AgentMetricsDetail)
- [ ] `app/agents/[id]/page.tsx` shipped
- [ ] `components/MetricsTable.tsx` minimal Link patch (D9 documented in PR)
- [ ] `npm run build` clean
- [ ] Manual smoke for at least 2 agents (1 baseline, 1 LLM)
- [ ] PR opened, body `Closes #15`
- [ ] No Claude attribution per CLAUDE.md
- [ ] PKG-15 unblocked (dynamic route convention proved)

---

## NOTES

### Design decisions worth flagging in PR

1. **Reuse PortfolioChart instead of new SingleAgentChart (D3)** — same
   component handles 1-line case fine, saves a file
2. **SVG heatmap, not Tailwind grid (D5)** — 1240 cells = 1240 React
   nodes if Tailwind divs; SVG single tree = much faster
3. **Per-ticker normalization (D5)** — global norm would dim VCB next to
   larger HPG holdings; per-row makes each ticker's pattern visible
4. **`use(params)` pattern (D1)** — Next 16 dynamic routes pass params as
   Promise; client components unwrap with React's `use` hook
5. **D9 ownership flex** — touched MetricsTable to enable Issue #15
   navigation; minimal (1 import + 1 cell change)

### Risks specific to PKG-14

| # | Risk | Mitigation |
|---|------|-----------|
| 1 | Next 16 `use(params)` Suspense boundary requirement | Spike A verifies before code; fall back to `loading.tsx` page-level Suspense if build complains |
| 2 | Heatmap 1240 cells lags on weaker hardware | Vanilla SVG vs Tailwind grid; if still slow, downsample (1 cell per 2 sessions = 620 cells) |
| 3 | Drawdown formula divergence from PKG-10 | Spike B verified to 4 decimals; visual sanity check |
| 4 | PortfolioChart legend reads weird with 1 series | Acceptable — single colored label centered; if ugly, hide via `<Legend hide />` |
| 5 | PKG-13 MetricsTable regression | Re-run dashboard smoke after Link wrap; assert toggle still hides rows |

### Khi gặp blocker

- `use(params)` throws → wrap component children in `<Suspense fallback={<p>Loading…</p>}>`
- Heatmap not visible → check `tickers.length`, check `perTickerMax` values, console.log first row
- Build TS errors on Link → `next/link` import path correct? Should be from `"next/link"` not `"@next/link"`
- 404 on `/agents/multi_agent` after navigation → restart `npm run dev`; Next sometimes caches dir tree
- Drawdown chart shows above 0 → forgot to negate dd values; ensure `dd = -(rm - pv) / rm`

### Phase 3 status after PKG-14

| PKG | Status |
|-----|--------|
| PKG-10 backtest + metrics | ✅ merged |
| PKG-11 FastAPI shell | ✅ merged |
| PKG-12 SSE live route | ✅ merged |
| PKG-13 Next.js dashboard | ✅ merged |
| **PKG-14 agent detail (this PR)** | 🟡 ready after impl |
| PKG-15 Debate replay UI | unblocked (dynamic route convention proven; uses `/debate/multi_agent/{date}`) |
| PKG-16 Live mode UI | unblocked (uses `/live/run` SSE from PKG-12) |
| **CHECKPOINT 24/05 (6 days out)** | Frontend on track; live mode go/no-go depends on PKG-16 budget |

---

## Confidence Score

**8.5/10** for one-pass implementation.

Subtract:
- −0.5 Next 16 `use(params)` syntax — verified in spike, but subtle if
  Suspense boundary requirements surface at runtime
- −0.5 Heatmap visual polish — SVG positioning math (label width, cell
  spacing) may need 1-2 iterations to look clean
- −0.5 D9 file ownership deviation could surprise reviewer if PR body
  doesn't surface it loudly

Add back:
- +1.5 PKG-13 patterns fully established (Card layout, useEffect fetch,
  client component pattern) — copy-paste blueprint
- +0.5 No new deps, no new endpoints — pure additive frontend work
- +0.5 Spike B already verified the only math-heavy piece (drawdown port)

PKG-14 is **medium risk** because of Next 16 + heatmap layout, but the
PKG-13 foundation makes 90% of the page mechanical. Path:
- Best case (~2h): spikes pass, components copy from plan patterns, ship
- Realistic (~3-4h): spend 1h on heatmap visual polish
- Worst case (~½ day): debug Suspense / params issues, fall back to
  simpler heatmap (Tailwind grid with downsampled cells)
