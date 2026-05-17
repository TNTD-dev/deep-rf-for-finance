# Frontend — DRL vs LLM/Agentic Trading dashboard (PKG-13+)

Next.js 16 + Tailwind v4 + shadcn/ui + Recharts. Localhost comparison
dashboard for the 8 trading agents shipped by PKG-4…10. Consumes the
FastAPI backend at `http://localhost:8000` (PKG-11).

## Requirements

- Node ≥ 18.18 (tested with v24.14)
- npm ≥ 9 (tested with v11.11)
- Backend running at `localhost:8000` (see root `CLAUDE.md` for setup)

## Setup

```bash
cd frontend
npm install                          # first-time only (~40s)
```

## Run dev

```bash
# Terminal 1 (repo root): backend
.venv/bin/uvicorn backend.main:app --port 8000

# Terminal 2 (frontend dir): Next.js dev server
npm run dev                          # → http://localhost:3000
```

## Build

```bash
npm run build                        # smoke type check + static build
npm run lint                         # eslint
```

## Backend URL

Hardcoded to `http://localhost:8000` in `lib/api.ts` (constant `BACKEND_URL`).
For a moving demo, edit that one line.

## Layout (PKG-13 scope)

```
app/
├── layout.tsx                       # root layout, light mode only
├── page.tsx                         # comparison dashboard (homepage)
└── globals.css                      # Tailwind v4 import + theme tokens
components/
├── AgentToggle.tsx                  # chip grid to show/hide agents
├── PortfolioChart.tsx               # Recharts LineChart, 8 agents
├── MetricsTable.tsx                 # shadcn Table, sortable
└── ui/                              # shadcn-generated primitives
lib/
├── api.ts                           # getAgents, getBacktest
├── types.ts                         # TS mirror of backend/models.py
├── colors.ts                        # name → hex map
├── format.ts                        # percent / VND / USD / decimal helpers
└── utils.ts                         # shadcn cn() helper
```

## Roadmap (later PKGs — do not touch in PKG-13)

- `app/agents/[id]/` — PKG-14 agent detail page
- `app/debate/` — PKG-15 debate replay UI
- `app/live/` — PKG-16 live mode (SSE consumer of `POST /live/run`)
