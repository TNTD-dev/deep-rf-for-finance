# Feature: PKG-11 — FastAPI shell + cache routes

> Backend HTTP layer trên top PKG-10. Đọc `results/{agent}/metrics.json` +
> `results/multi_agent/transcripts/{date}.json` (đã tồn tại trên đĩa), serve
> qua FastAPI cho PKG-13 (comparison dashboard) + PKG-15 (debate replay) +
> PKG-16 (live mode UI) consume.
>
> PKG-11 KHÔNG sinh dữ liệu. **Mọi route là pure file-read** — business
> logic đã shipped trong PKG-4/6/7/8/9/10. Route handler trung bình 5-10 dòng.
>
> Cold-start mục tiêu < 2s. Lazy load + mtime invalidation (một cache class
> shared cho tất cả routes). Tests dùng pytest + httpx.TestClient với fixture
> results_dir.

## Feature Description

4 routes + 1 cache + 1 pydantic models module + 1 main app:

1. **`GET /healthz`** — liveness check + diagnostics (results dir exists,
   n_cached_agents).
2. **`GET /agents`** — list 8 agents từ `AGENT_REGISTRY`, group thành
   `{agents: [...], baselines: [...]}` khớp PRD §10.
3. **`GET /backtest/{agent}`** — đọc `results/{agent}/metrics.json` (đã
   matching PRD §10 shape via PKG-10 `build_payload`). Pydantic response
   validate shape; 404 nếu agent không có metrics.json.
4. **`GET /debate/{agent}/{date}`** — đọc `results/multi_agent/transcripts/
   {date}.json`, map `{role, output, ...}` → `{role, content}` khớp PRD §10
   debate shape. 404 nếu file không tồn tại; chỉ chấp nhận `agent=multi_agent`.

Acceptance criteria (Issue #12):
- `uvicorn backend.main:app` start không lỗi
- curl 3 endpoints trả schema khớp PRD §10
- Cold start < 2s

## User Story

As a **PKG-13 Next.js comparison dashboard**
I want **`GET /agents` + `GET /backtest/{agent}` to return PRD §10 JSON**
So that **frontend code is pure `fetch + render` — no schema massaging, no
LLM-specific reader branching**.

As a **PKG-15 debate replay UI**
I want **`GET /debate/multi_agent/{date}` to return ordered transcript
entries with `{role, content}` shape**
So that **the UI maps 1-to-1 over the response array, no extraction logic
in the frontend**.

As a **PKG-12 SSE live mode (next package)**
I want **`backend/` module structure already established (main.py, routes/,
cache/, models.py)**
So that **PKG-12 only adds `routes/live.py` + `sse.py` — no scaffolding
work on the critical path**.

As a **demo presenter (Duc)**
I want **healthz endpoint with cached-agent count**
So that **trong buổi bảo vệ, một `curl /healthz` confirm backend đã load
đúng cache trước khi mở dashboard**.

## Problem Statement

5 challenges:

1. **Schema must match PRD §10 exactly.** PKG-10 đã ghi `metrics.json` đúng
   shape (PKG-10 plan §D7). Pydantic response schemas trong PKG-11 phải:
   (a) validate that PKG-10 output is correct (catch regressions),
   (b) be the TS-source-of-truth that PKG-13 mirrors.
2. **Holdings dict key uses ticker code, not `h_VCB`.** PRD §10 example:
   `{"VCB": 1200, "FPT": 800}`. PKG-10 already strips `h_` prefix in
   `build_payload`. ✓ Schema must use `dict[str, int]` not fixed fields
   (extensibility: VN30 expansion later).
3. **Debate transcript shape diverges from PRD §10.** Actual transcript
   JSON has `{role, ts, model, output, usage}` per entry; PRD says
   `{role, content}` (+ optional `decision`). Map `output → content` at
   the route layer; do NOT change transcript schema (PKG-8 owns it).
4. **Cache invalidation when PKG-10 re-runs.** Dev iterates: re-run
   `scripts/run_all.py`, expect refreshed dashboard. Option A: restart
   uvicorn (acceptable for localhost demo). Option B: mtime check per
   request (~50µs stat() vs ~5ms file read — negligible). Pick B for
   transparency: dev never wonders "did the cache update?".
5. **Cold start < 2s.** FastAPI + uvicorn boot ≈ 300ms. Eager-loading all
   metrics.json upfront = ~10ms (8 files × 50KB). Lazy is fine; do NOT
   eager-load (keeps startup deterministic + avoids importing pandas/numpy
   transitively for a no-data startup).

## Solution Statement

10 design decisions LOCK before code:

- **D1.** **Cache helper: `JSONFileCache` class** with `get(path) → dict | None`
  semantics. Internal `dict[Path, tuple[float_mtime, dict]]`. On each call:
  stat() path → if mtime unchanged, return cached; else reload + cache. Missing
  file → return None (NOT exception — callers decide 404 vs default).
- **D2.** **One cache instance per app** via `app.state.cache`. Routes call
  `request.app.state.cache.get(path)` — no module-level globals.
- **D3.** **Pydantic v2 response models** trong `backend/models.py`:
  `AgentList`, `BacktestPayload`, `Provenance`, `PortfolioPoint`,
  `HoldingsPoint`, `Metrics`, `DebateTranscript`, `DebateEntry`. Validate
  on response (FastAPI's `response_model=...`). Tests catch schema drift.
- **D4.** **Routes are pure file readers.** No `if/else` business logic. Route
  pattern:
  ```python
  @router.get("/backtest/{agent}", response_model=BacktestPayload)
  def get_backtest(agent: str, request: Request) -> dict:
      path = request.app.state.results_dir / agent / "metrics.json"
      data = request.app.state.cache.get(path)
      if data is None:
          raise HTTPException(404, f"no metrics for agent {agent!r}")
      return data
  ```
- **D5.** **Dependency injection via `app.state`** (not `Depends(...)`).
  `app.state.results_dir` + `app.state.cache` set in `lifespan`. Tests
  override `app.state.results_dir = tmp_path` before TestClient. Simpler
  than `Depends`-callable factories for this scope.
- **D6.** **CORS:** `allow_origins=["http://localhost:3000",
  "http://localhost:8000"]`, methods=["GET", "POST"]. PKG-12 may add OPTIONS
  for SSE preflight; we keep both POST + OPTIONS in the allowlist now to
  avoid PKG-12 touching `main.py`.
- **D7.** **`GET /healthz` returns `{status, results_dir, n_cached_agents,
  uptime_s}`.** `n_cached_agents` = count of `metrics.json` files currently
  on disk (not cache size — distinguishes "loaded into cache" from "exists
  on disk"). Useful smoke before demo.
- **D8.** **`GET /agents` groups by baseline-set.** Baselines hardcoded
  `{"buy_and_hold", "equal_weight", "random"}` (the 3 from `src.baselines`);
  the rest from `AGENT_REGISTRY` keys minus baseline-set = agents. Output:
  `{"agents": ["ddpg", "multi_agent", "ppo", "single_agentic", "zero_shot"],
  "baselines": ["buy_and_hold", "equal_weight", "random"]}`. Both sorted
  alphabetically.
- **D9.** **`GET /debate/{agent}/{date}` agent guard.** `if agent !=
  "multi_agent"` → 400 (not 404 — semantic error, not missing resource).
  Map transcript entries: `{role, content: output, model, ts}` (keep
  `model` + `ts` as bonus fields — PRD §10 example uses 2 keys but doesn't
  forbid extras).
- **D10.** **`backend/__init__.py` + `backend/routes/__init__.py` empty
  package markers.** No re-exports. `backend.main:app` is the ASGI entry
  (`uvicorn backend.main:app`).

## Feature Metadata

- **Feature Type:** New Capability (first HTTP layer; unblocks PKG-12/13/14/15/16)
- **Estimated Complexity:** **Low** — 4 file-read routes, no logic; deps
  already installed; PRD shape locked; PKG-10 payload already matches.
  Risk concentrated in cache + Pydantic round-trip.
- **Primary Systems Affected:**
  - New package: `backend/` (main.py, models.py, cache.py, routes/{healthz,agents,backtest,debate}.py)
  - New tests: `tests/test_routes_healthz.py`, `test_routes_agents.py`,
    `test_routes_backtest.py`, `test_routes_debate.py`, `test_cache.py`
- **Dependencies:** Already in `pyproject.toml`: `fastapi>=0.110`,
  `uvicorn[standard]>=0.27`, `sse-starlette>=2.1`, `httpx>=0.27`. **No new deps.**

---

## CONTEXT REFERENCES

### Relevant Codebase Files — ĐỌC TRƯỚC KHI IMPLEMENT

**The contract PKG-11 serves (PKG-10):**

- `src/eval/backtest.py:40-78` — `build_payload(result, metrics, llm_metrics, test_window, seed) → dict`. Single source of truth for PRD §10 shape. PKG-11 schema is the Pydantic mirror.
- `src/eval/aggregate.py:118-160` — `build_metrics_table(results_dir)`. PKG-11 does NOT use this (per-agent payloads are richer than the CSV row); reference only.
- `src/agents/__init__.py:30-46` — `AGENT_REGISTRY` keys. `GET /agents` derives the agent list from this.
- `src/baselines.py:26-94` — `BuyAndHold`, `EqualWeightRebalance`, `RandomAgent` class names. `GET /agents` baseline-set comes from inspecting these (or hardcode the 3 names — cheaper, same result).

**Existing artifacts (`results/` layout — confirmed via shell):**

```
results/
├── metrics_table.csv          (PKG-10 cross-agent)
├── buy_and_hold/metrics.json  54KB, 248 sessions  | PRD §10 shape
├── equal_weight/metrics.json  54KB                 | "
├── ppo/metrics.json           50KB                 | "
├── ddpg/metrics.json          51KB                 | "
├── random/metrics.json        50KB                 | "
├── zero_shot/metrics.json      3KB, 10 sessions    | "
├── single_agentic/metrics.json 3KB, 10             | " + extra LLM keys
├── multi_agent/
│   ├── metrics.json            2KB,  4 sessions    | " + multi keys
│   ├── decisions.jsonl
│   └── transcripts/
│       └── 2025-05-05.json     ← /debate consumes this
└── models/{ddpg,ppo}_best.zip  (not served)
```

**Transcript JSON shape (CONFIRMED via shell):**

```
top-level keys: date, agent, duration_s, debate_rounds, timed_out,
                node_errors, models_used, transcript, trader_proposal,
                risk_review, portfolio_manager_output, debate_exchanges
transcript[i] keys: role, ts, model, output, usage
```

**PRD §10 target shapes (locked — Pydantic mirrors):**

```json
// GET /agents
{ "agents": ["ddpg", "llm_zeroshot", "single_agentic", "multi_agent"],
  "baselines": ["buy_and_hold", "equal_weight"] }

// GET /backtest/{agent}
{ "agent": "multi_agent",
  "portfolio_curve": [{"date": "2025-05-02", "value": 1003200000}, ...],
  "holdings": [{"date": "...", "VCB": 1200, "FPT": 800, ...}],
  "metrics": { "cumulative_return": 0.18, "sharpe": 1.42, ... } }

// GET /debate/{agent}/{date}
{ "date": "2025-08-04",
  "transcript": [
    { "role": "technical_analyst", "content": "RSI VCB đang ở 71..." },
    { "role": "portfolio_manager",  "content": "...",
      "decision": {"VCB": 0.15, "FPT": 0.30, ...} } ] }
```

**Note PRD vs registry naming drift:** PRD example uses `"llm_zeroshot"`
but PKG-10 + PKG-6 ship as `"zero_shot"`. PKG-11 `GET /agents` returns
**`zero_shot`** (matches `AGENT_REGISTRY` + `results/zero_shot/`); PRD
example is illustrative only. PKG-13 must use registry names.

**Don't touch (file ownership):**

- All `src/` — PKG-11 imports only `src.agents.AGENT_REGISTRY` (read-only).
- `backend/routes/live.py` — owned by PKG-12.
- `frontend/` — owned by PKG-13+.
- `src/llm/multi_agent/transcript.py` — owned by PKG-8.

### New Files to Create

```
backend/
├── __init__.py                       # empty package marker
├── main.py                           # FastAPI app + CORS + lifespan + mount
├── models.py                         # Pydantic v2 response schemas
├── cache.py                          # JSONFileCache class
└── routes/
    ├── __init__.py                   # empty
    ├── healthz.py                    # GET /healthz
    ├── agents.py                     # GET /agents
    ├── backtest.py                   # GET /backtest/{agent}
    └── debate.py                     # GET /debate/{agent}/{date}

tests/
├── test_cache.py                     # 4 tests: hit, miss, mtime invalidation, missing
├── test_routes_healthz.py            # 2 tests: status ok, n_cached counts files
├── test_routes_agents.py             # 2 tests: shape, sorted, registry-derived
├── test_routes_backtest.py           # 5 tests: 200 ok, 404, schema, all 8 agents, cache hit
└── test_routes_debate.py             # 4 tests: 200, 404 missing date, 400 wrong agent, mapping
```

### Relevant Documentation — ĐỌC TRƯỚC KHI IMPLEMENT

- **FastAPI lifespan** (modern startup/shutdown): https://fastapi.tiangolo.com/advanced/events/#lifespan
  - Why: replaces deprecated `@app.on_event("startup")`; use for cache init
- **FastAPI app.state + request.app.state**: https://fastapi.tiangolo.com/reference/request/?h=app.state
  - Why: DI without `Depends()` for app-scoped singletons
- **Pydantic v2 ConfigDict + model_config**: https://docs.pydantic.dev/latest/concepts/models/#model-config
  - Why: `extra="allow"` for backtest metrics (LLM agents add `llm_cost_usd`, multi_agent adds `n_decisions`, etc. — schema must permit superset)
- **httpx.TestClient (pytest)**: https://www.starlette.io/testclient/
  - Why: FastAPI test pattern; works in-process, no server start
- **CORSMiddleware**: https://fastapi.tiangolo.com/tutorial/cors/
  - Why: localhost:3000 (Next.js) → localhost:8000 (FastAPI); need explicit allow

### Pre-implementation spikes

**Spike A — Load + validate metrics.json round-trips through Pydantic:**

```bash
.venv/bin/python <<'PY'
"""Verify Pydantic models accept all 8 existing metrics.json files."""
import json, pathlib
from pydantic import BaseModel, ConfigDict, Field

class Provenance(BaseModel):
    ts: str
    seed: int
    test_window: list[str] | None = None
    n_steps: int

class PortfolioPoint(BaseModel):
    date: str
    value: int

class Metrics(BaseModel):
    model_config = ConfigDict(extra="allow")
    cumulative_return: float
    sharpe: float
    sortino: float
    max_drawdown: float
    turnover: float
    total_cost: float
    n_steps: int

class BacktestPayload(BaseModel):
    agent: str
    portfolio_curve: list[PortfolioPoint]
    holdings: list[dict[str, int | str]]  # date is str, ticker counts are int
    metrics: Metrics
    provenance: Provenance

for p in sorted(pathlib.Path("results").glob("*/metrics.json")):
    try:
        payload = BacktestPayload.model_validate_json(p.read_text())
        print(f"OK  {p.parent.name}: pc={len(payload.portfolio_curve)} extras={set(payload.metrics.model_extra)}")
    except Exception as e:
        print(f"FAIL {p.parent.name}: {e}")
PY
```

Expected: all 8 OK. LLM agents show `extras` = `{llm_cost_usd, ...}`,
multi_agent shows `{n_decisions, avg_latency_s, ...}`. Confirms `extra="allow"`
captures the superset cleanly + locks the Pydantic field set against drift.

**Spike B — Load transcript + map to PRD §10 debate shape:**

```bash
.venv/bin/python <<'PY'
"""Verify transcript → debate response mapping."""
import json, pathlib
p = pathlib.Path("results/multi_agent/transcripts/2025-05-05.json")
raw = json.loads(p.read_text())
print(f"raw keys: {sorted(raw)}")
print(f"transcript len: {len(raw['transcript'])}")
print(f"entry[0] raw: {raw['transcript'][0]}")
mapped = {
    "date": raw["date"],
    "transcript": [
        {"role": e["role"], "content": e["output"], "model": e.get("model")}
        for e in raw["transcript"]
    ],
}
# Optional: surface portfolio_manager_output as decision on the last entry
pm_out = raw.get("portfolio_manager_output")
if pm_out and mapped["transcript"]:
    last = mapped["transcript"][-1]
    if last["role"] == "portfolio_manager":
        last["decision"] = pm_out
print(f"mapped[0]: {mapped['transcript'][0]}")
print(f"mapped[-1]: {mapped['transcript'][-1]}")
PY
```

Expected: 10 entries, last entry is `portfolio_manager` with `decision` populated.
Locks the mapping logic before writing the route.

**Spike C — TestClient smoke against real `results/`:**

```bash
.venv/bin/python <<'PY'
"""Smoke: spin up app, hit 4 routes, assert 200."""
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse
# Bare-bones stand-in to test the import/CORS/file-read stack BEFORE
# routes exist. The real app is built in Step 4 below.
app = FastAPI()
@app.get("/healthz")
def h(): return {"status": "ok"}
client = TestClient(app)
r = client.get("/healthz")
print(r.status_code, r.json())
PY
```

Expected: `200 {'status': 'ok'}`. Confirms toolchain works end-to-end before
writing the real app. Skip if you already trust the fastapi+httpx install.

### Patterns to Follow

**Pydantic v2 response model with extras allowed (`backend/models.py`):**

```python
from pydantic import BaseModel, ConfigDict


class Metrics(BaseModel):
    """Financial + LLM-specific metrics. LLM agents add llm_cost_usd,
    avg_latency_s, etc.; multi_agent adds n_decisions, avg_debate_rounds.
    extra='allow' surfaces those without a per-agent subclass."""

    model_config = ConfigDict(extra="allow")

    cumulative_return: float
    sharpe: float
    sortino: float
    max_drawdown: float
    turnover: float
    total_cost: float
    n_steps: int
```

**Cache class (`backend/cache.py`):**

```python
"""Lazy JSON file cache with mtime-based invalidation.

Per-process singleton accessed via `request.app.state.cache`. Each call:
- stat() the path (cheap, ~50µs)
- if mtime unchanged, return cached dict (no I/O)
- else read + parse + cache, return fresh dict
- missing file → return None (callers decide 404 vs default)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)


class JSONFileCache:
    def __init__(self) -> None:
        self._store: dict[Path, tuple[float, dict]] = {}

    def get(self, path: Path) -> dict | None:
        try:
            mtime = path.stat().st_mtime
        except FileNotFoundError:
            self._store.pop(path, None)
            return None
        cached = self._store.get(path)
        if cached is not None and cached[0] == mtime:
            return cached[1]
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            log.warning("cache read failed %s: %s", path, e)
            return None
        self._store[path] = (mtime, data)
        return data

    def clear(self) -> None:
        self._store.clear()

    def size(self) -> int:
        return len(self._store)
```

**Lifespan + app wiring (`backend/main.py`):**

```python
"""FastAPI app entry. Run with: uvicorn backend.main:app --reload --port 8000"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.cache import JSONFileCache
from backend.routes import agents, backtest, debate, healthz
from src import config

RESULTS_DIR = config.PROJECT_ROOT / "results"


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.results_dir = RESULTS_DIR
    app.state.cache = JSONFileCache()
    app.state.started_at = time.monotonic()
    yield
    app.state.cache.clear()


def create_app() -> FastAPI:
    app = FastAPI(
        title="deep-rf-finance API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://localhost:8000"],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    app.include_router(healthz.router)
    app.include_router(agents.router)
    app.include_router(backtest.router)
    app.include_router(debate.router)
    return app


app = create_app()
```

**Route handler (`backend/routes/backtest.py` — the canonical 5-line route):**

```python
from fastapi import APIRouter, HTTPException, Request

from backend.models import BacktestPayload

router = APIRouter()


@router.get("/backtest/{agent}", response_model=BacktestPayload)
def get_backtest(agent: str, request: Request) -> dict:
    path = request.app.state.results_dir / agent / "metrics.json"
    data = request.app.state.cache.get(path)
    if data is None:
        raise HTTPException(404, f"no metrics for agent {agent!r}")
    return data
```

**Test pattern (`tests/test_routes_backtest.py` — TestClient + tmp results):**

```python
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app


@pytest.fixture
def app(tmp_path: Path) -> TestClient:
    a = create_app()
    a.state.results_dir = tmp_path  # override the production results/
    a.state.cache.clear()
    return TestClient(a)


def _write_backtest(root: Path, name: str, **overrides) -> None:
    payload = {
        "agent": name,
        "portfolio_curve": [{"date": "2025-05-05", "value": 1_000_000_000}],
        "holdings": [{"date": "2025-05-05", "VCB": 100, "FPT": 0,
                      "HPG": 0, "VIC": 0, "VNM": 0}],
        "metrics": {
            "cumulative_return": 0.1, "sharpe": 1.0, "sortino": 1.5,
            "max_drawdown": 0.05, "turnover": 0.02, "total_cost": 1_500_000,
            "n_steps": 247,
        },
        "provenance": {"ts": "2026-05-17T00:00:00+00:00", "seed": 42,
                       "test_window": ["2025-05-05", "2026-04-30"], "n_steps": 247},
        **overrides,
    }
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "metrics.json").write_text(json.dumps(payload))


def test_get_backtest_returns_pkg10_payload(app, tmp_path):
    _write_backtest(tmp_path, "buy_and_hold")
    r = app.get("/backtest/buy_and_hold")
    assert r.status_code == 200
    body = r.json()
    assert body["agent"] == "buy_and_hold"
    assert body["metrics"]["cumulative_return"] == 0.1
```

**Error handling (CLAUDE.md alignment):**

- Missing `metrics.json` → 404 with agent name in detail
- Missing `transcripts/{date}.json` → 404 with date in detail
- Wrong agent on debate (e.g. `/debate/ddpg/...`) → 400 "debate only supported for multi_agent"
- Malformed JSON on disk → cache returns None → 404 (logged WARNING); shouldn't happen in practice
- CORS preflight from disallowed origin → handled by middleware (returns no CORS headers)

---

## DESIGN DECISIONS — LOCK BEFORE IMPLEMENT

### D1. `JSONFileCache` class with mtime invalidation

`get(path)` semantics:
- File missing → return None (caller raises 404)
- File present + mtime matches cached → return cached dict (no I/O)
- File present + mtime newer → reload + cache + return
- Malformed JSON → log WARNING + return None (same as missing)

NOT using `functools.lru_cache` — needs invalidation that LRU doesn't offer.
NOT using thread-safe primitives — uvicorn workers are async single-thread per
worker; localhost demo doesn't fork.

### D2. App-level state via `app.state` (not `Depends()`)

Tests override:
```python
app = create_app()
app.state.results_dir = tmp_path
app.state.cache.clear()
client = TestClient(app)
```

Cleaner than `Depends(get_results_dir)` factories for app-singleton resources.
If PKG-12 needs request-scoped deps, it can add `Depends()` then without
refactoring PKG-11.

### D3. Pydantic v2 with `extra="allow"` on `Metrics`

Why: LLM agents and multi_agent ship extra keys (`llm_cost_usd`,
`n_decisions`, `avg_latency_s`, `node_errors_total`, …). Schema MUST allow
them through without rejection. PKG-13 reads extras as `metrics["llm_cost_usd"]
?? null`.

`PortfolioPoint`, `HoldingsPoint`, `Provenance` get default `extra="ignore"`
(reject unknown) — those shapes are tight, drift = bug.

### D4. Routes are pure file readers (max 10 lines each)

Anti-goal: ORM-style query builders, response massaging, multi-file joins.
Goal: route handler reads ONE path, returns ONE payload, lets Pydantic +
caching handle the rest.

If you find yourself writing more than 10 lines, push the logic into
`src/` (the science layer) or a helper in `backend/cache.py`.

### D5. CORS: localhost-only, GET + POST + OPTIONS

`allow_origins=["http://localhost:3000", "http://localhost:8000"]`. No `*`
even on localhost — explicit safer + harder to accidentally deploy.

POST + OPTIONS allowed now so PKG-12 (`POST /live/run` + SSE preflight)
doesn't have to touch `main.py`.

### D6. 404 missing, 400 semantic-error, 500 unexpected

- 404: file not on disk (most common — agent name typo, smoke didn't run)
- 400: client violates contract (`/debate/buy_and_hold/...` — debate only
  exists for multi_agent)
- 500: Pydantic validation fails on disk JSON (PKG-10 schema drift — surface loudly)

### D7. `/healthz` returns diagnostics, not just `{"status": "ok"}`

```json
{ "status": "ok",
  "results_dir": "/abs/path/to/results",
  "results_dir_exists": true,
  "n_metrics_files": 8,
  "n_cached": 0,
  "uptime_s": 12.4 }
```

`n_metrics_files` = `len(glob('*/metrics.json'))`; `n_cached` =
`app.state.cache.size()`. Distinguishes "what exists" from "what's been
hit". Demo smoke: `curl /healthz` before opening the dashboard.

### D8. `/agents` baseline-set hardcoded

```python
BASELINE_AGENTS = frozenset({"buy_and_hold", "equal_weight", "random"})
```

Hardcoding 3 names is faster + clearer than `isinstance` checks on factories
(factories are lambdas — class is opaque). Trade: if PKG-S adds a new
baseline, update the set. Acceptable for ½-day scope.

### D9. Debate route maps `output → content` + decision-injection

```python
mapped = [
    {"role": e["role"], "content": e["output"], "model": e.get("model")}
    for e in raw["transcript"]
]
pm = raw.get("portfolio_manager_output")
if pm and mapped and mapped[-1]["role"] == "portfolio_manager":
    mapped[-1]["decision"] = pm
return {"date": raw["date"], "transcript": mapped}
```

`model` extra is bonus — PRD §10 doesn't forbid extras on transcript entries
and PKG-15 UI may show "Generated by gpt-4o" badges.

### D10. `backend.main:app` is the ASGI entry

```bash
uvicorn backend.main:app --reload --port 8000  # dev
uvicorn backend.main:app --port 8000           # demo
```

`create_app()` factory exists so tests build fresh instances; the
module-level `app = create_app()` is what uvicorn imports.

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation — package skeleton + cache

- `backend/__init__.py`, `backend/routes/__init__.py` (empty)
- `backend/cache.py` — `JSONFileCache`
- `tests/test_cache.py` — 4 tests (hit, miss, mtime invalidation, malformed)

### Phase 2: Schemas + healthz

- `backend/models.py` — all 8 Pydantic models
- `backend/routes/healthz.py` — depends on `app.state` only, no other routes
- `backend/main.py` — lifespan + CORS + mount healthz
- `tests/test_routes_healthz.py` — 2 tests

### Phase 3: Read-only routes

- `backend/routes/agents.py`
- `backend/routes/backtest.py`
- `backend/routes/debate.py`
- `tests/test_routes_agents.py`, `test_routes_backtest.py`, `test_routes_debate.py`

### Phase 4: Real-data smoke + cold-start measurement

- `curl http://localhost:8000/healthz`, `/agents`, `/backtest/buy_and_hold`,
  `/backtest/multi_agent`, `/debate/multi_agent/2025-05-05`
- Time cold start with `time uvicorn backend.main:app --port 8001 &` ⇒ < 2s

---

## STEP-BY-STEP TASKS

### 1. RUN Spike A + B + C

- **VALIDATE:** Spike A prints `OK` for all 8 agents. Spike B prints mapped
  transcript with `decision` on last entry. Spike C prints `200 {'status': 'ok'}`.

### 2. CREATE `backend/__init__.py` + `backend/routes/__init__.py`

- **IMPLEMENT:** Empty files (package markers).

### 3. CREATE `backend/cache.py`

- **IMPLEMENT:** Class as shown in "Patterns to Follow". ~30 lines.
- **VALIDATE:** `.venv/bin/python -c "from backend.cache import JSONFileCache; c=JSONFileCache(); print(c.get(__import__('pathlib').Path('results/buy_and_hold/metrics.json')) is not None)"` → prints `True`.

### 4. CREATE `tests/test_cache.py` (~4 tests)

- **IMPLEMENT:**
  1. `test_cache_returns_none_for_missing_file(tmp_path)` — assert None
  2. `test_cache_round_trips_dict(tmp_path)` — write JSON, get, compare
  3. `test_cache_invalidates_on_mtime_change(tmp_path)` — write, get; rewrite with `os.utime(path, (t+10, t+10))`, get, expect new value
  4. `test_cache_returns_none_for_malformed_json(tmp_path)` — write `"not json"`, get, expect None
- **VALIDATE:** `.venv/bin/pytest tests/test_cache.py -v` → 4 pass.

### 5. CREATE `backend/models.py`

- **IMPLEMENT:**
  ```python
  """Pydantic v2 response schemas. Mirror PRD §10 verbatim — PKG-10
  build_payload is the producer; these models are the consumer contract."""

  from __future__ import annotations

  from pydantic import BaseModel, ConfigDict


  class Provenance(BaseModel):
      ts: str
      seed: int
      test_window: list[str] | None = None
      n_steps: int


  class PortfolioPoint(BaseModel):
      date: str
      value: int


  class Metrics(BaseModel):
      """Financial + LLM-specific. extra='allow' surfaces per-agent extras
      (llm_cost_usd, n_decisions, avg_latency_s, …) without subclassing."""

      model_config = ConfigDict(extra="allow")

      cumulative_return: float
      sharpe: float
      sortino: float
      max_drawdown: float
      turnover: float
      total_cost: float
      n_steps: int


  class BacktestPayload(BaseModel):
      agent: str
      portfolio_curve: list[PortfolioPoint]
      holdings: list[dict[str, int | str]]   # date is str; per-ticker counts are int
      metrics: Metrics
      provenance: Provenance


  class AgentList(BaseModel):
      agents: list[str]
      baselines: list[str]


  class DebateEntry(BaseModel):
      model_config = ConfigDict(extra="allow")  # decision, model are optional extras
      role: str
      content: str


  class DebateTranscript(BaseModel):
      date: str
      transcript: list[DebateEntry]


  class HealthzResponse(BaseModel):
      status: str
      results_dir: str
      results_dir_exists: bool
      n_metrics_files: int
      n_cached: int
      uptime_s: float
  ```
- **GOTCHA:** `holdings` field is `list[dict[str, int | str]]` not a fixed
  pydantic class — the date is a string, all other keys are ints, and we
  don't want to lock to 5 specific tickers (extensibility).
- **VALIDATE:** `.venv/bin/python -c "from backend.models import BacktestPayload; import json; p='results/buy_and_hold/metrics.json'; print(BacktestPayload.model_validate_json(open(p).read()).agent)"` → prints `buy_and_hold`.

### 6. CREATE `backend/routes/healthz.py`

- **IMPLEMENT:**
  ```python
  import time
  from pathlib import Path

  from fastapi import APIRouter, Request

  from backend.models import HealthzResponse

  router = APIRouter()


  @router.get("/healthz", response_model=HealthzResponse)
  def healthz(request: Request) -> dict:
      rd: Path = request.app.state.results_dir
      n_files = (
          len(list(rd.glob("*/metrics.json"))) if rd.exists() else 0
      )
      return {
          "status": "ok",
          "results_dir": str(rd),
          "results_dir_exists": rd.exists(),
          "n_metrics_files": n_files,
          "n_cached": request.app.state.cache.size(),
          "uptime_s": time.monotonic() - request.app.state.started_at,
      }
  ```

### 7. CREATE `backend/main.py`

- **IMPLEMENT:** As shown in "Patterns to Follow". `lifespan` + `create_app()`
  + module-level `app`. Mount all 4 routers (healthz, agents, backtest, debate)
  even though only healthz exists yet — import errors will catch missing files
  at next step boundary, which is fine.
- **GOTCHA #1:** Use `from contextlib import asynccontextmanager` — not
  `@app.on_event("startup")` (deprecated in 0.110+).
- **GOTCHA #2:** Mount routers BEFORE the `app = create_app()` line — the
  factory needs them imported at module top.
- **TEMP:** During Step 7, comment out non-existent router includes; uncomment
  as Steps 9-11 create them.

### 8. CREATE `tests/test_routes_healthz.py` (~2 tests)

- **IMPLEMENT:**
  1. `test_healthz_returns_ok(tmp_path)` — fixture sets `app.state.results_dir = tmp_path`; assert 200, status=="ok", n_metrics_files==0
  2. `test_healthz_counts_metrics_files(tmp_path)` — write 2 fake metrics.json in tmp; assert n_metrics_files==2
- **VALIDATE:** `.venv/bin/pytest tests/test_routes_healthz.py -v` → 2 pass.

### 9. CREATE `backend/routes/agents.py`

- **IMPLEMENT:**
  ```python
  from fastapi import APIRouter

  from backend.models import AgentList
  from src.agents import AGENT_REGISTRY

  BASELINE_AGENTS = frozenset({"buy_and_hold", "equal_weight", "random"})

  router = APIRouter()


  @router.get("/agents", response_model=AgentList)
  def get_agents() -> dict:
      all_names = set(AGENT_REGISTRY.keys())
      baselines = sorted(all_names & BASELINE_AGENTS)
      agents = sorted(all_names - BASELINE_AGENTS)
      return {"agents": agents, "baselines": baselines}
  ```
- **VALIDATE:** Includes `multi_agent`, `zero_shot`, `single_agentic`, `ddpg`,
  `ppo` in `agents`; `buy_and_hold`, `equal_weight`, `random` in `baselines`.

### 10. CREATE `tests/test_routes_agents.py` (~2 tests)

- **IMPLEMENT:**
  1. `test_agents_returns_registry_partition` — assert shape + content
  2. `test_agents_alphabetical` — both lists sorted asc
- **VALIDATE:** `.venv/bin/pytest tests/test_routes_agents.py -v` → 2 pass.

### 11. CREATE `backend/routes/backtest.py`

- **IMPLEMENT:** As shown in "Patterns to Follow". 5-line handler.

### 12. CREATE `tests/test_routes_backtest.py` (~5 tests)

- **IMPLEMENT:**
  1. `test_get_backtest_returns_pkg10_payload(app, tmp_path)` — write fixture, GET, assert shape
  2. `test_get_backtest_404_on_missing_agent(app)` — GET unknown, expect 404
  3. `test_get_backtest_schema_validates_all_required_keys(app, tmp_path)` — missing metrics.cumulative_return → 500 (Pydantic validation)
  4. `test_get_backtest_extra_metrics_keys_pass_through(app, tmp_path)` — write metrics with `llm_cost_usd`; expect in response
  5. `test_get_backtest_uses_cache_on_second_call(app, tmp_path)` — write once, GET twice, mock cache to assert hit
- **GOTCHA:** Use the `_write_backtest` helper from Patterns; reuse across tests.
- **VALIDATE:** `.venv/bin/pytest tests/test_routes_backtest.py -v` → 5 pass.

### 13. CREATE `backend/routes/debate.py`

- **IMPLEMENT:**
  ```python
  from fastapi import APIRouter, HTTPException, Request

  from backend.models import DebateTranscript

  router = APIRouter()


  @router.get("/debate/{agent}/{date}", response_model=DebateTranscript)
  def get_debate(agent: str, date: str, request: Request) -> dict:
      if agent != "multi_agent":
          raise HTTPException(
              400, "debate only supported for agent=multi_agent"
          )
      path = (
          request.app.state.results_dir
          / "multi_agent" / "transcripts" / f"{date}.json"
      )
      raw = request.app.state.cache.get(path)
      if raw is None:
          raise HTTPException(404, f"no transcript for date {date!r}")
      mapped = [
          {"role": e["role"], "content": e.get("output", ""),
           "model": e.get("model"), "ts": e.get("ts")}
          for e in raw.get("transcript", [])
      ]
      pm = raw.get("portfolio_manager_output")
      if pm and mapped and mapped[-1]["role"] == "portfolio_manager":
          mapped[-1]["decision"] = pm
      return {"date": raw["date"], "transcript": mapped}
  ```
- **GOTCHA #1:** `e.get("output", "")` — defensive: a transcript entry without
  `output` (node error) shouldn't crash; surface empty content + the UI can
  show "error in node" if `model` is None.
- **GOTCHA #2:** Date is a path parameter (str), no parsing — FastAPI passes
  through. Validation happens at file-existence (404 if `{date}.json` missing).

### 14. CREATE `tests/test_routes_debate.py` (~4 tests)

- **IMPLEMENT:**
  1. `test_get_debate_returns_prd_shape(app, tmp_path)` — write multi_agent/transcripts/2025-05-05.json fixture; GET → assert role+content mapped
  2. `test_get_debate_404_on_missing_date(app, tmp_path)` — GET nonexistent date → 404
  3. `test_get_debate_400_on_non_multi_agent(app)` — GET `/debate/buy_and_hold/2025-05-05` → 400
  4. `test_get_debate_injects_pm_decision(app, tmp_path)` — fixture has portfolio_manager_output → assert last entry has `decision` key
- **VALIDATE:** `.venv/bin/pytest tests/test_routes_debate.py -v` → 4 pass.

### 15. UNCOMMENT all 4 router includes in `backend/main.py`

- Now all 4 routes exist; main.py mounts all.

### 16. SMOKE — real `results/` over uvicorn

- **IMPLEMENT:**
  ```bash
  (.venv/bin/uvicorn backend.main:app --port 8001 &) && sleep 1
  curl -s http://localhost:8001/healthz | python -m json.tool
  curl -s http://localhost:8001/agents | python -m json.tool
  curl -s http://localhost:8001/backtest/buy_and_hold | python -m json.tool | head -20
  curl -s http://localhost:8001/backtest/multi_agent | python -m json.tool | head -30
  curl -s http://localhost:8001/debate/multi_agent/2025-05-05 | python -m json.tool | head -30
  curl -s http://localhost:8001/backtest/nonexistent -w "\nHTTP %{http_code}\n"
  curl -s http://localhost:8001/debate/buy_and_hold/2025-05-05 -w "\nHTTP %{http_code}\n"
  pkill -f "uvicorn backend.main:app --port 8001"
  ```
- **EXPECTED:** First 5 return 200 + JSON; missing agent returns 404; wrong
  agent on debate returns 400.

### 17. MEASURE cold start

- **IMPLEMENT:**
  ```bash
  time .venv/bin/python -c "from backend.main import create_app; app = create_app(); print('imported')"
  ```
- **EXPECTED:** Real time < 2s. Most of that is fastapi+uvicorn import (cached
  on second run).

### 18. FINAL ruff + pytest

```bash
.venv/bin/ruff check backend/ tests/
.venv/bin/ruff format backend/ tests/test_cache.py tests/test_routes_*.py
.venv/bin/pytest tests/ 2>&1 | tail -5
# Expected: ruff clean, ~240 tests pass (223 + ~17 new)
```

---

## TESTING STRATEGY

### Unit Tests (~17 new across 5 files)

| File | Count | Focus |
|------|------:|-------|
| `test_cache.py` | 4 | hit, miss, mtime invalidation, malformed JSON |
| `test_routes_healthz.py` | 2 | status, file count |
| `test_routes_agents.py` | 2 | partition, alphabetical |
| `test_routes_backtest.py` | 5 | 200, 404, schema validation, extras, cache |
| `test_routes_debate.py` | 4 | 200 + mapping, 404, 400, pm_decision injection |

Total after PKG-11: **223 (current) + ~17 = ~240 tests**.

### Integration smoke (manual, in PR description)

Step 16 commands; paste curl outputs.

### Edge Cases Explicitly Covered

| # | Case | Test |
|---|------|------|
| 1 | Missing metrics.json | backtest #2 |
| 2 | Malformed JSON on disk | cache #4 |
| 3 | Extra metrics keys (LLM agents) | backtest #4 |
| 4 | File mtime changes between requests | cache #3 |
| 5 | Wrong agent for debate | debate #3 |
| 6 | Missing transcript date | debate #2 |
| 7 | Transcript entry without `output` (node error) | debate route defensive `.get("output", "")` |
| 8 | Empty `results/` dir | healthz #1 |

---

## VALIDATION COMMANDS

### Level 1: Syntax & Style

```bash
.venv/bin/ruff check backend/ tests/
```

### Level 2: Unit tests

```bash
.venv/bin/pytest tests/test_cache.py tests/test_routes_*.py -v
```

### Level 3: Full regression

```bash
.venv/bin/pytest tests/ 2>&1 | tail -5
```

### Level 4: Cold-start time

```bash
time .venv/bin/python -c "from backend.main import create_app; create_app()"
# Expected: real < 2.0s
```

### Level 5: Live API smoke (Step 16)

```bash
(.venv/bin/uvicorn backend.main:app --port 8001 &) && sleep 1
curl -s http://localhost:8001/healthz
curl -s http://localhost:8001/agents
curl -s http://localhost:8001/backtest/buy_and_hold | head -c 200
pkill -f "uvicorn backend.main:app --port 8001"
```

### Level 6: Schema regression vs PRD §10

```bash
.venv/bin/python <<'PY'
"""Every metrics.json on disk must round-trip through Pydantic."""
import pathlib
from backend.models import BacktestPayload
bad = []
for p in pathlib.Path("results").glob("*/metrics.json"):
    try:
        BacktestPayload.model_validate_json(p.read_text())
    except Exception as e:
        bad.append((p, str(e)[:80]))
if bad:
    for p, msg in bad:
        print(f"FAIL {p}: {msg}")
    raise SystemExit(1)
print(f"OK all {sum(1 for _ in pathlib.Path('results').glob('*/metrics.json'))} payloads validate")
PY
```

---

## ACCEPTANCE CRITERIA

Issue #12:
- [ ] `uvicorn backend.main:app` start không lỗi (Level 5 smoke)
- [ ] curl 3 endpoints trả schema khớp PRD §10 (Level 5 + Level 6)
- [ ] Cold start < 2s (Level 4)
- [ ] ~17 tests pass; 223 prior still pass; ruff clean

Extra (not in issue but in this plan):
- [ ] `/healthz` returns diagnostic block useful for demo-day smoke
- [ ] `/debate/{wrong_agent}/{date}` returns 400 with helpful message
- [ ] All 8 agents on disk round-trip through `BacktestPayload` Pydantic schema (catches PKG-10 regression)

---

## COMPLETION CHECKLIST

- [ ] Spike A/B/C run, outputs captured in PR description
- [ ] `backend/` package with main.py + models.py + cache.py + 4 routes
- [ ] CORS allows localhost:3000 + localhost:8000
- [ ] Lifespan inits `app.state.{results_dir, cache, started_at}`
- [ ] ~17 new tests pass; ruff clean
- [ ] Real-data smoke (Step 16) passes for all 5 happy-path curls + 2 error curls
- [ ] Cold-start measurement captured in PR description
- [ ] PR opened `PKG-11: FastAPI shell + cache routes`, body `Closes #12`
- [ ] No Claude attribution per CLAUDE.md
- [ ] PKG-12 unblocked (`backend/sse.py` + `routes/live.py` can be added without
      touching main.py)
- [ ] PKG-13 unblocked (Next.js fetches `/agents` + `/backtest/{agent}`)

---

## NOTES

### Design decisions worth flagging in PR

1. **`JSONFileCache` over `functools.lru_cache`** — needed mtime invalidation;
   LRU has no eviction-on-source-change concept
2. **`app.state` over `Depends()`** — single-flavor singletons, simpler; PKG-12
   can introduce `Depends()` if needed
3. **`extra="allow"` on `Metrics`** — LLM agents legitimately add fields;
   schema rejection would force per-agent subclasses (over-engineered)
4. **Pydantic shipping as response_model AND test artifact** — PKG-10 regressions
   surface as 500 from Pydantic validation (loud, not silent)
5. **Hardcoded `BASELINE_AGENTS`** — frozenset of 3 names; PKG-S adds new
   baseline → update the line (acceptable cost for ½-day scope)
6. **Debate route maps `output → content` + decision injection** — adapter
   between PKG-8 transcript shape and PRD §10 debate shape lives at the
   route (single owner); transcript schema stays PKG-8's

### Risks specific to PKG-11

| # | Risk | Mitigation |
|---|------|-----------|
| 1 | PKG-10 metrics.json shape drifts; Pydantic 500s on production | Level 6 schema regression command in CI-equivalent (PR description) |
| 2 | CORS misconfigured; FE can't talk to BE | Explicit allow_origins list; test with curl + Origin header in Step 16 |
| 3 | Cold start > 2s due to transitive pandas/torch import | `backend/main.py` imports `src.agents` which imports `src.llm.multi_agent.agent` → langgraph. Measure (Level 4); fall back to lazy import of registry if > 2s |
| 4 | Cache returns stale on edited file | mtime test (cache #3) catches; manual smoke after editing metrics.json |
| 5 | Transcript entry missing `output` (node failure) crashes route | Defensive `.get("output", "")` + test |

### Khi gặp blocker

- Pydantic validation 500 on a real metrics.json → run Level 6, identify the
  failing field, decide: relax schema (`extra="allow"`) or fix PKG-10
- Cold start > 2s → profile imports with
  `.venv/bin/python -X importtime -c "from backend.main import create_app; create_app()" 2>&1 | sort -k2 -n | tail -20`
- CORS preflight fails on browser → check `Access-Control-Allow-Origin`
  response header; usually `allow_methods` missing OPTIONS
- TestClient hangs → check `lifespan` async signature; FastAPI requires
  `async def` for the asynccontextmanager

### Phase 3 status after PKG-11

| PKG | Status |
|-----|--------|
| PKG-10 backtest + metrics | ✅ merged |
| **PKG-11 FastAPI shell (this PR)** | 🟡 ready after impl |
| PKG-12 SSE live route | unblocked (consumes `backend/main.py` + `app.stream` from PKG-8) |
| PKG-13 Next.js comparison dashboard | unblocked (`/agents` + `/backtest/{agent}` serve schema) |
| PKG-14 Agent detail page | unblocked (`/backtest/{agent}` already serves full payload) |
| PKG-15 Debate replay UI | unblocked (`/debate/multi_agent/{date}` returns mapped transcript) |
| **CHECKPOINT 24/05** | 7 days out — go/no-go cho live mode (PKG-12+16) |

---

## Confidence Score

**9/10** for one-pass implementation.

Subtract:
- −0.5 transcript→debate mapping is N-key massage; first integration may
  reveal a transcript shape variation (e.g. trader_proposal entry, debate
  exchange ordering) we didn't cover with the 1 sample we have on disk
- −0.5 cold-start measurement is "trust but verify" — torch/langgraph
  import surface is large; if `from src.agents import AGENT_REGISTRY` pulls
  the full multi_agent stack at import time, may exceed 2s budget. Mitigation
  ready (lazy import) but only triggers if it fires

Add back:
- +1.5 Schema locked + already on disk in 8 files; Pydantic validates against
  reality, not against assumptions
- +1.0 Deps already installed (no env work); routes are 5-10 lines each;
  PKG-10 build_payload is the producer contract — PKG-11 just consumes

PKG-11 is the lowest-risk package of Phase 3. Real risk = transcript shape
edge cases (covered by defensive `.get()` + 1 sample). Path to ½-day:
spikes (15 min) → cache + tests (45 min) → models + healthz (30 min) → 3
routes + tests (90 min) → smoke + ruff (30 min) → PR (15 min) ≈ 4 hours.
