# Feature: PKG-S — Serialized integration + rehearsal (final package)

> 18/18 — package cuối trước deadline **31/05/2026** (còn 14 ngày).
> Repo đã ship 17/18; PKG-S là tổng kết: registry verify, full multi_agent
> backtest cho honest comparison numbers, offline mode, debate list endpoint,
> chart figures, README runbook, rehearsal + Loom fallback.
>
> **Code scope: ~1 day. Manual scope (recording + rehearsal): ~0.5 day.**

## Feature Description

PKG-S là **integration layer**, không thêm capability mới. 7 nhánh:

1. **S1 — Registry verify**: confirm `src/agents/__init__.py` không drift sau
   17 PRs. Một câu lệnh smoke chứng minh tất cả 8 agents import + instantiate
   được.
2. **S3 — Offline mode**: thêm `OFFLINE_MODE` flag vào `src/config.py` +
   `.env.example`. Khi bật, `POST/GET /live/run` trả 503 với message thân
   thiện thay vì cố gọi LLM (cứu cánh khi demo mất wifi).
3. **S5a — Full multi_agent backtest**: chạy `scripts/run_multi_agent.py`
   cho toàn bộ test window (~50 weekly decisions, ~25 phút wallclock, ~$2.50).
   Hiện chỉ có 4 sessions smoke → +50 transcripts cho /debate UI + honest
   numbers vs DDPG/PPO/baselines.
4. **S5b — `GET /debate/multi_agent` list endpoint**: auto-discover transcripts
   từ filesystem (~20 lines BE + ~10 lines FE), tháo coupling FE↔BE paths.
   Frontend `app/debate/page.tsx` chuyển từ hardcoded `AVAILABLE_DEBATE_DATES`
   sang fetch.
5. **S5c — `metrics_table.csv` re-gen + 4 chart PNG figures**: `python -m
   src.eval.run_all` regen metrics; `scripts/make_figures.py` (NEW) tạo
   4 chart PNG cho slide Người 1 dùng.
6. **README.md (NEW)** — runbook đầy đủ: setup → fetch data → train → backtest
   → backend → frontend → demo flow. Hôm nay chưa có README.
7. **S2/S4/S6 — manual rehearsal + Loom recording**: documented as checklist
   ở cuối plan, không phải code.

## User Story

As **Duc (demo presenter)**
I want **demo end-to-end 5 phút không crash, có fallback video, có metrics
table + chart đầy đủ cho slide**
So that **buổi defense 31/05 đi đúng kịch bản, không phụ thuộc wifi/OpenAI**.

As **Người 1 (report writer)**
I want **final `metrics_table.csv` + 4 chart PNG sẵn trong `report/figures/`**
So that **viết được kết luận với số liệu honest, không phải smoke**.

As **Người 2 (verify)**
I want **README runbook + `python -m src.eval.run_all` reproducibility check**
So that **ký off "no lookahead bias" + reproducibility với confidence**.

## Problem Statement

Sau 17 PRs:
- **Registry chưa được verify cuối**. Đã hoạt động ở PKG-10 nhưng PKG-S
  là gate cuối — phải confirm import path nào trong 8 agents drift.
- **Multi-agent chỉ có 4 sessions smoke** — return +2.79% không đại diện cho
  ~50 decision window. Report sẽ phải note "smoke only, N=4" — không honest.
- **Demo deps wifi + OpenAI uptime** — nếu mất mạng giữa demo → /live page
  crash với connection error, không graceful.
- **`/debate` UI hardcode 1 ngày** — dù full backtest sinh ra +50 dates,
  frontend không tự động pick up.
- **Không có README** — Người 2 reproduce từ scratch khó.
- **Chưa có chart PNG cho slide** — Người 1 phải tự generate hoặc Duc lo.

## Solution Statement

Approach: **bám sát TASKS.md PKG-S spec (S1-S6), thêm 2 deferred items**
(GET /debate list endpoint từ PKG-15 deferred limitation; README runbook).
Mỗi task atomic, validate ngay. Manual tasks tách rõ với checklist riêng.

**Order rationale**:
1. S1 registry verify trước — fail-fast nếu có drift (5 phút).
2. S3 offline mode trước — code thay đổi cô lập, dễ revert (15 phút).
3. S5a full multi_agent backtest — long-running, kick off sớm để parallel
   với code work khác (~25 phút wallclock; hoặc background).
4. S5b debate list endpoint — depend on S5a (cần transcripts mới hiện).
5. S5c charts + metrics — depend on S5a (cần kết quả mới).
6. README — depend on tất cả (runbook reflect final state).
7. Manual S2/S4/S6 — sau khi code merge.

## Feature Metadata

**Feature Type**: Integration + verification (no new capability)
**Estimated Complexity**: Medium — 7 nhánh, parallelizable, nhưng mỗi nhánh
nhỏ + ít risk
**Primary Systems Affected**:
- Config (`src/config.py`, `.env.example`)
- Backend (`backend/routes/live.py`, `backend/routes/debate.py`)
- Frontend (`frontend/app/debate/page.tsx`, `frontend/lib/api.ts`,
  `frontend/lib/types.ts`)
- Eval (`scripts/run_multi_agent.py` — invoke; `src/eval/run_all.py` — invoke)
- New: `scripts/make_figures.py`, `report/figures/*.png`, `README.md`
- Verify-only: `src/agents/__init__.py`
**Dependencies**: `matplotlib` (chart gen — likely missing; PKG-S thêm
nếu cần)

---

## CONTEXT REFERENCES

### Relevant Codebase Files — ĐỌC TRƯỚC KHI IMPLEMENT

- `.agent/TASKS.md` lines 770-823 — **PKG-S official spec** (S1-S6 + acceptance)
- `.agent/PRD.md` §15 — locked params; §10 — SSE event shape; §14 — risks
- `src/agents/__init__.py` (1-57) — registry; verify all 8 entries import-able
- `src/config.py` (1-60) — pattern: `_str/_int/_float/_list` helpers + dotenv;
  **mirror `_bool` helper cho `OFFLINE_MODE`**
- `backend/routes/live.py` (1-149) — POST + GET handlers; **add 503 short-circuit
  trước `event_gen()`** ở cả 2 handlers
- `backend/routes/debate.py` (1-39) — pattern: APIRouter + `app.state.results_dir`;
  **mirror cho list endpoint**
- `backend/main.py` lines 10, 32, 55 — `app.state.results_dir = RESULTS_DIR`
  setup (đã có cho test + prod)
- `backend/routes/agents.py` — pattern: list endpoint trả `list[...]` (xem
  nếu có precedent cho `/agents` list shape)
- `scripts/run_multi_agent.py` (1-50) — supports `--split test` (default) =
  full test window; `--n-sessions N` cho smoke; `--reset-transcripts` cho
  fresh start
- `src/eval/run_all.py` — single entry regen all artifacts incl. `metrics_table.csv`
- `frontend/app/debate/page.tsx` lines 10-13 — hardcoded `AVAILABLE_DEBATE_DATES`;
  thay bằng fetch
- `frontend/lib/api.ts` — pattern: `getDebate()` exists; **thêm `getDebateDates()`**
- `frontend/lib/types.ts` — extend with `DebateDatesResponse` type
- `results/metrics_table.csv` (current state) — multi_agent row có
  `n_steps=4` → sau full run sẽ là `n_steps≈50`
- `results/multi_agent/transcripts/` — hiện 1 file `2025-05-05.json`; sau
  full run sẽ +~49 files
- `pyproject.toml` — check `matplotlib` đã có chưa; nếu chưa thêm vào deps

### Files PKG-S sẽ CHẠM

**Modify:**
- `src/config.py` — add `OFFLINE_MODE` + `_bool` helper
- `.env.example` — add `OFFLINE_MODE=false`
- `backend/routes/live.py` — 503 short-circuit khi `OFFLINE_MODE` bật (cả POST + GET)
- `backend/routes/debate.py` — add `GET /debate/{agent}/dates` list endpoint
- `frontend/app/debate/page.tsx` — fetch dates thay vì hardcode
- `frontend/lib/api.ts` — `getDebateDates(agent)` helper
- `frontend/lib/types.ts` — `DebateDatesResponse` type
- `results/metrics_table.csv` — regen (artifact, không edit tay)
- `results/multi_agent/*` — overwrite từ full run (artifact)

**Verify-only (read, không edit):**
- `src/agents/__init__.py`

**Create:**
- `scripts/make_figures.py` — generate 4 chart PNG
- `report/figures/*.png` (4 files)
- `README.md` (root)

### Relevant Documentation

- FastAPI 0.x — `APIRouter` + `app.state` patterns (đã thuộc lòng từ PKG-11-12).
- sse-starlette — `EventSourceResponse` already wired; chỉ short-circuit
  return JSON 503 trước khi tạo response.
- matplotlib pyplot — `plt.figure()`, `plt.bar()`, `plt.plot()`,
  `plt.savefig(..., dpi=150, bbox_inches='tight')` (basic only — không cần
  seaborn).
- Pandas read parquet — `pd.read_parquet(path)` cho `portfolio_curve.parquet`
  của từng agent.

### Patterns to Follow

**Config helper (mirror existing in `src/config.py`):**

```python
def _bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.lower() in ("1", "true", "yes", "on")

OFFLINE_MODE: bool = _bool("OFFLINE_MODE", False)
```

**Route short-circuit (live.py):**

```python
from fastapi.responses import JSONResponse
from src import config

@router.post("/live/run")
async def live_run(...):
    if config.OFFLINE_MODE:
        return JSONResponse(
            status_code=503,
            content={"detail": "OFFLINE_MODE=true — demo dùng cached transcripts. Xem /debate."},
        )
    # ... existing body
```

Note: phải trả `JSONResponse` chứ không phải raise `HTTPException` (vì
trả thông qua SSE wrapper sẽ rối). Frontend `lib/sse.ts` đã handle network
error → banner đỏ.

**Debate list endpoint (mirror `debate.py` shape):**

```python
@router.get("/debate/{agent}/dates")
def list_debate_dates(agent: str, request: Request) -> dict:
    if agent != "multi_agent":
        raise HTTPException(400, "debate only supported for agent=multi_agent")
    transcripts_dir = request.app.state.results_dir / agent / "transcripts"
    if not transcripts_dir.exists():
        return {"agent": agent, "dates": []}
    dates = sorted(p.stem for p in transcripts_dir.glob("*.json"))
    return {"agent": agent, "dates": dates}
```

Path-collision check: `GET /debate/{agent}/dates` vs existing
`GET /debate/{agent}/{date}` — FastAPI ưu tiên route đăng ký trước. **Phải
declare `/dates` TRƯỚC `/{date}` trong file** hoặc dùng path khác như
`GET /debate/{agent}` (cleaner). Plan: dùng `GET /debate/{agent}` để tránh
collision hoàn toàn.

Final shape: `GET /debate/{agent}` → `{agent, dates: [...]}` ; existing
`GET /debate/{agent}/{date}` không đụng.

**Chart generation pattern (`scripts/make_figures.py`):**

```python
"""Generate 4 chart PNG cho report slide (PKG-S S5)."""
from __future__ import annotations
import matplotlib.pyplot as plt
import pandas as pd
from src import config

RESULTS = config.PROJECT_ROOT / "results"
FIGURES = config.PROJECT_ROOT / "report" / "figures"
FIGURES.mkdir(parents=True, exist_ok=True)

AGENTS = ["buy_and_hold", "equal_weight", "ppo", "ddpg", "zero_shot",
          "single_agentic", "multi_agent", "random"]

def fig_portfolio_curves():
    fig, ax = plt.subplots(figsize=(10, 5))
    for agent in AGENTS:
        path = RESULTS / agent / "portfolio_curve.parquet"
        if not path.exists():
            continue
        df = pd.read_parquet(path)
        # Mirror eval/aggregate.py for column names. Likely "value" or "portfolio_value".
        ax.plot(df.index, df["portfolio_value"], label=agent)
    ax.set_title("Portfolio value (VND) — test 2025-05 → 2026-04")
    ax.legend(loc="upper left", fontsize=8)
    ax.grid(True, alpha=0.3)
    plt.savefig(FIGURES / "01_portfolio_curves.png", dpi=150, bbox_inches="tight")
    plt.close()

# Similar: fig_cum_return_bar(), fig_sharpe_bar(), fig_decision_frequency()
```

**Frontend API extension (`frontend/lib/api.ts`):**

Mirror existing `getDebate()`:
```ts
export async function getDebateDates(agent: string): Promise<DebateDatesResponse> {
  const res = await fetch(`${BACKEND_URL}/debate/${agent}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}
```

**Frontend page (`app/debate/page.tsx`):**

Replace hardcoded `AVAILABLE_DEBATE_DATES` with `useState<string[]>([])` +
`useEffect` fetching dates on mount. Loading state on initial fetch. Empty
state khi `dates.length === 0` ("Chưa có transcripts; chạy `python scripts/run_multi_agent.py`").

---

## IMPLEMENTATION PLAN

### Phase 1: Verification + isolated code changes (kick off long-running in parallel)

**Tasks:**
1. S1 registry verify (5 min)
2. S3 offline mode (15 min)
3. **Kick off S5a full multi_agent backtest in background** (~25 min wallclock)

### Phase 2: Backend + Frontend integration (work while S5a runs)

**Tasks:**
4. S5b debate list endpoint (BE)
5. Frontend fetch dates (FE)
6. Tests cho cả hai

### Phase 3: Post-backtest artifacts (after S5a finishes)

**Tasks:**
7. Verify multi_agent results sanity (no crashes mid-run, n_decisions ≈ 50)
8. Re-gen `metrics_table.csv` via `python -m src.eval.run_all`
9. S5b/c charts: `scripts/make_figures.py` → 4 PNG

### Phase 4: Documentation + final validation

**Tasks:**
10. README.md runbook
11. Full validation suite (pytest, ruff, ts, build)
12. Manual rehearsal checklist (S2 + S4 + S6 — separate from code; document for Duc)

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order. Each task is atomic và independently
testable. Branch: `duc/PKG-S-integration`.

### Task 1: BRANCH + READ PKG-S SPEC

- **IMPLEMENT**: `git checkout -b duc/PKG-S-integration` from main (current
  HEAD `0bca4c1`).
- **PATTERN**: Mirror branch naming từ PKG-16 (`duc/PKG-16-frontend-live`).
- **VALIDATE**: `git status` shows clean working tree on new branch.

### Task 2: VERIFY src/agents/__init__.py registry (S1)

- **IMPLEMENT**: Read file, confirm 8 entries (buy_and_hold, ddpg, equal_weight,
  multi_agent, ppo, random, single_agentic, zero_shot). Run smoke import.
- **PATTERN**: Already in shape from PKG-10 — KHÔNG edit, chỉ verify.
- **IMPORTS**: N/A (read-only)
- **GOTCHA**: Nếu thấy drift (missing/duplicate entry), STOP và surface — không
  patch silently.
- **VALIDATE**:
  ```bash
  .venv/bin/python -c "from src.agents import AGENT_REGISTRY; assert len(AGENT_REGISTRY) == 8; print(sorted(AGENT_REGISTRY))"
  ```
  Expected: `['buy_and_hold', 'ddpg', 'equal_weight', 'multi_agent', 'ppo', 'random', 'single_agentic', 'zero_shot']`

### Task 3: ADD OFFLINE_MODE config (S3)

- **IMPLEMENT**: `src/config.py` — add `_bool` helper + `OFFLINE_MODE: bool = _bool("OFFLINE_MODE", False)`.
- **PATTERN**: Mirror `_str/_int/_float/_list` helpers (config.py lines 32-49).
- **IMPORTS**: None new.
- **GOTCHA**: Defaults to `False` — production behavior unchanged. Test bằng
  cách set env var, KHÔNG hard-code `True` trong commit.
- **VALIDATE**:
  ```bash
  .venv/bin/python -c "from src import config; assert config.OFFLINE_MODE is False; print('OK')"
  OFFLINE_MODE=true .venv/bin/python -c "from src import config; assert config.OFFLINE_MODE is True; print('OK truthy')"
  OFFLINE_MODE=False .venv/bin/python -c "from src import config; assert config.OFFLINE_MODE is False; print('OK falsy')"
  ```

### Task 4: UPDATE .env.example

- **IMPLEMENT**: Append section sau HOSE rules:
  ```
  # === Demo fallback ===
  # PKG-S S3: khi true, /live/run trả 503 thân thiện. Dùng khi demo mất
  # wifi → fallback sang /debate (cached transcripts).
  OFFLINE_MODE=false
  ```
- **PATTERN**: Mirror existing section headers (`# === Universe ===`).
- **VALIDATE**: `grep -n "OFFLINE_MODE" .env.example` returns 1 match.

### Task 5: UPDATE backend/routes/live.py — OFFLINE_MODE short-circuit

- **IMPLEMENT**: Trong cả `live_run` (POST) và `live_run_get` (GET), check
  `config.OFFLINE_MODE` ngay đầu function. Nếu true, return JSONResponse 503.
- **PATTERN**: New import `from fastapi.responses import JSONResponse`. Reuse
  existing `from src import config` (đã có).
- **IMPORTS**: `from fastapi.responses import JSONResponse`
- **GOTCHA**: `live_run_get` calls `live_run` internally — short-circuit
  trong POST handler là đủ. Nhưng để rõ ràng + decouple, đặt check ở CẢ HAI
  (defense in depth, 2 dòng code). Verify GET delegation vẫn return JSONResponse
  (FastAPI auto-handles cả EventSourceResponse và JSONResponse).
- **TYPE HINT GOTCHA**: Cả hai handler hiện hint `-> EventSourceResponse`. Khi
  short-circuit return `JSONResponse`, runtime OK (FastAPI accepts any Response)
  nhưng strict mypy/pyright sẽ flag. Fix: widen return annotation thành
  `-> Response` (`from fastapi import Response`) hoặc `EventSourceResponse | JSONResponse`.
- **VALIDATE**:
  ```bash
  # Off (default) — normal POST should fail without OPENAI_API_KEY but at least not return 503
  .venv/bin/uvicorn backend.main:app --port 8001 &
  sleep 2
  curl -sS -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8001/live/run
  # Expected: 200 (stream starts) or 500 (LLM failure). NOT 503.
  kill %1
  # On
  OFFLINE_MODE=true .venv/bin/uvicorn backend.main:app --port 8001 &
  sleep 2
  curl -sS http://localhost:8001/live/run -X POST  # POST
  # Expected: 503 + JSON body with "detail" field mentioning OFFLINE_MODE
  curl -sS http://localhost:8001/live/run          # GET
  # Expected: 503 same shape
  kill %1
  ```

### Task 6: ADD backend/routes/debate.py — list endpoint

- **IMPLEMENT**: Add `@router.get("/debate/{agent}")` returning
  `{agent, dates: list[str]}`. Sort `*.json` filenames stems từ
  `app.state.results_dir / agent / "transcripts"`.
- **PATTERN**: Mirror `get_debate()` validation (`agent != "multi_agent"` → 400).
- **IMPORTS**: None new.
- **GOTCHA**: Route order matters — FastAPI matches first-registered. Existing
  `/debate/{agent}/{date}` route is more specific (more path segments) so order
  không quan trọng ở đây. **Vẫn nên** đăng ký `/debate/{agent}` SAU
  `/debate/{agent}/{date}` để tránh ambiguity nếu future route thêm.
  Actually FastAPI dispatches by full path match — `/debate/multi_agent`
  match `/debate/{agent}` only; `/debate/multi_agent/2025-05-05` match
  `/debate/{agent}/{date}` only. OK.
- **VALIDATE**:
  ```bash
  .venv/bin/uvicorn backend.main:app --port 8001 &
  sleep 2
  curl -sS http://localhost:8001/debate/multi_agent | python -m json.tool
  # Expected: {"agent": "multi_agent", "dates": ["2025-05-05"]} (pre-S5a)
  curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:8001/debate/zero_shot
  # Expected: 400
  curl -sS http://localhost:8001/debate/multi_agent/2025-05-05 | python -c "import sys, json; d = json.load(sys.stdin); assert d['date'] == '2025-05-05'; print('OK')"
  # Existing endpoint still works
  kill %1
  ```

### Task 7: ADD backend test for list endpoint

- **IMPLEMENT**: First locate existing test file:
  ```bash
  find tests -name "test_debate*" -o -name "*debate*test*"
  ls tests/backend/ 2>/dev/null
  ```
  Add `test_list_dates_returns_sorted` in the existing test file if present;
  CREATE `tests/backend/test_debate_routes.py` if not. Use `tmp_path` +
  `app.state.results_dir` override (pattern from `backend/main.py:10`).
- **PATTERN**: Mirror the existing debate route test (whatever path the
  command above finds). If no precedent exists, mirror pattern from
  `backend/main.py:10` (`app.state.results_dir = tmp_path`).
- **GOTCHA**: Use `TestClient` from FastAPI; populate `app.state.results_dir`
  to point at a fixture directory with `multi_agent/transcripts/{2025-05-05,2025-05-12}.json`.
- **VALIDATE**:
  ```bash
  .venv/bin/pytest tests/backend/test_debate_routes.py -v -k "list_dates"
  ```

### Task 8 (LONG-RUNNING — kick off in parallel with Tasks 9-11 only): RUN full multi_agent backtest

> **Parallelism note**: Tasks 12 (regen metrics) and 13 (charts) hard-depend
> on Task 8 finishing (they read `results/multi_agent/*`). Only Tasks 9-11
> (frontend) truly run concurrent with the backtest.

- **IMPLEMENT**:
  ```bash
  .venv/bin/python scripts/run_multi_agent.py --split test --reset-transcripts 2>&1 | tee results/multi_agent/full_run.log
  ```
- **PATTERN**: Script đã shipped PKG-8; default `--split test` = full test
  window. `--reset-transcripts` ensure clean start (delete old smoke transcript).
- **IMPORTS**: N/A
- **GOTCHA**:
  - **$2.50 spend** — đảm bảo `OPENAI_API_KEY` set, `OFFLINE_MODE=false`.
  - **~25 phút wallclock** — chạy background hoặc tee tmux/screen.
  - Nếu crash giữa chừng: transcripts đã ghi vẫn dùng được (append mode).
    Check `decisions.jsonl` line count.
  - **Network rate-limit**: nếu OpenAI 429, script retry built-in từ PKG-5;
    nhưng nếu 1 decision fail toàn bộ thì log + fallback hold (PKG-8 design).
  - **Cost monitoring**: theo dõi `llm_cost_usd` column trong final metrics.
    Nếu > $5, STOP + surface.
- **VALIDATE**:
  ```bash
  ls results/multi_agent/transcripts/ | wc -l       # Expected: ~50 (not 1)
  wc -l results/multi_agent/decisions.jsonl         # Expected: ~50
  tail -1 results/multi_agent/decisions.jsonl | python -m json.tool  # Sanity check shape
  ```

### Task 9: UPDATE frontend/lib/types.ts

- **IMPLEMENT**: Add `DebateDatesResponse` type:
  ```ts
  export type DebateDatesResponse = {
    agent: string;
    dates: string[];
  };
  ```
- **PATTERN**: Mirror existing `DebateTranscript` type in same file.
- **VALIDATE**: `cd frontend && npx tsc --noEmit`

### Task 10: UPDATE frontend/lib/api.ts — getDebateDates

- **IMPLEMENT**: Add `getDebateDates(agent)` helper mirroring `getDebate()`:
  ```ts
  export async function getDebateDates(agent: string): Promise<DebateDatesResponse> {
    const res = await fetch(`${BACKEND_URL}/debate/${agent}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }
  ```
- **PATTERN**: Existing `getDebate()` in same file.
- **VALIDATE**: `cd frontend && npx tsc --noEmit`

### Task 11: UPDATE frontend/app/debate/page.tsx — fetch dates dynamically

- **IMPLEMENT**: Remove hardcoded `AVAILABLE_DEBATE_DATES`. Add top-level
  `useState<string[]>([])` + `useEffect` fetching dates on mount.
  - Loading state: "Đang load danh sách ngày…"
  - Empty state: "Chưa có transcripts. Chạy `python scripts/run_multi_agent.py`."
  - Error state: same shape as existing `DebateInner` error UI.
- **PATTERN**: Mirror `DebateInner` `useEffect` pattern (same file lines 56-66).
  Keep `key={date}` remount pattern.
- **IMPORTS**: Add `getDebateDates` import.
- **GOTCHA**:
  - Initial `date` state phải đợi fetch hoàn tất rồi set first date (hoặc
    use `useState<string | null>(null)` + nullish render).
  - Update comment trên file: "PKG-S S5b — dates fetched từ
    `GET /debate/{agent}`, không còn hardcoded."
- **VALIDATE**:
  ```bash
  cd frontend && npx tsc --noEmit && npm run build
  # Then manual:
  npm run dev  # in one terminal
  # in another: .venv/bin/uvicorn backend.main:app
  # open http://localhost:3000/debate → DatePicker shows all ~50 dates (after S5a)
  ```

### Task 12: RE-GEN metrics_table.csv (S5c)

- **IMPLEMENT**: `.venv/bin/python -m src.eval.run_all`
- **PATTERN**: Existing entry point (PRD §15 reproducibility requirement).
- **GOTCHA**:
  - Trước khi chạy, snapshot old csv: `cp results/metrics_table.csv results/metrics_table.before-pkg-s.csv`
  - Verify `multi_agent` row's `n_steps` updates ~4 → ~50.
- **VALIDATE**:
  ```bash
  grep multi_agent results/metrics_table.csv | head -1
  # Expected: n_steps column ~ 50, llm_cost_usd ~ 2.5
  ```

### Task 13a (PRECONDITION): ENSURE matplotlib installed

- **IMPLEMENT**:
  ```bash
  grep -E "^\s*\"matplotlib" pyproject.toml || echo "MISSING"
  ```
  Nếu MISSING:
  1. Edit `pyproject.toml` — add `"matplotlib>=3.7"` vào `[project.dependencies]`.
  2. `.venv/bin/pip install -e .`
  3. Verify: `.venv/bin/python -c "import matplotlib; print(matplotlib.__version__)"`
- **GOTCHA**: PHẢI hoàn tất TRƯỚC Task 13 (Task 13 import matplotlib).
- **VALIDATE**: `import matplotlib` không raise.

### Task 13: CREATE scripts/make_figures.py (S5b)

- **IMPLEMENT**: Script sinh 4 PNG cho `report/figures/`:
  1. `01_portfolio_curves.png` — line chart, value vs date, 8 agents
  2. `02_cum_return_bar.png` — horizontal bar, sorted by cum_return desc
  3. `03_sharpe_bar.png` — same shape, sharpe values (smoke agents flagged with `*`)
  4. `04_decision_frequency.png` — bar showing `n_steps` per agent (cho thấy
     LLM agents weekly = 50, RL/baseline daily = 247)
- **PATTERN**: See "Patterns to Follow → Chart generation pattern" above.
- **IMPORTS**: `matplotlib.pyplot`, `pandas`, `src.config`.
- **GOTCHA**:
  - Check `pyproject.toml` đã có `matplotlib` chưa. Nếu chưa:
    ```bash
    .venv/bin/pip install matplotlib && pip freeze | grep matplotlib >> pyproject.toml  # plus update [project.dependencies]
    ```
    Hoặc edit `pyproject.toml` thêm `"matplotlib>=3.7"` vào deps; run `pip install -e .`.
  - Column names trong parquet — verify với:
    `python -c "import pandas as pd; print(pd.read_parquet('results/buy_and_hold/portfolio_curve.parquet').columns.tolist())"`
    Có thể là `["date", "value"]` hoặc `["portfolio_value"]` — mirror exact.
  - Save dpi=150 (slide-ready, không quá nặng).
  - Color consistency với `frontend/lib/colors.ts` — optional, nice-to-have.
- **VALIDATE**:
  ```bash
  .venv/bin/python scripts/make_figures.py
  ls -la report/figures/
  # Expected: 4 PNG files, mỗi file 50-300KB
  file report/figures/01_portfolio_curves.png  # Expected: PNG image data
  ```

### Task 14: CREATE README.md (root runbook)

- **IMPLEMENT**: Runbook covering — setup, data, train, backtest, demo flow,
  offline mode, project structure (link CLAUDE.md), license note.
  Structure đề xuất:
  ```markdown
  # DRL vs LLM/Agentic Trading — VN30

  Thesis project so sánh DDPG (Xiong et al) với 3 LLM/agentic approaches
  trên thị trường VN30. Code + report + demo cho deadline 2026-05-31.

  ## Quickstart

  ```bash
  cp .env.example .env       # Edit OPENAI_API_KEY
  pip install -e .
  pytest                     # 255 tests should pass
  ```

  ## Data pipeline
  ```bash
  python scripts/fetch_data.py
  python scripts/fetch_news.py
  ```

  ## Train RL agents
  ```bash
  python scripts/train_ddpg.py
  python scripts/train_ppo.py
  ```

  ## Backtest all agents
  ```bash
  python scripts/run_baselines.py
  python scripts/run_rl_backtest.py
  python scripts/run_zero_shot.py
  python scripts/run_single_agentic.py
  python scripts/run_multi_agent.py        # ~25 min, ~$2.50
  python -m src.eval.run_all               # aggregate → metrics_table.csv
  python scripts/make_figures.py           # 4 PNG → report/figures/
  ```

  ## Demo (full stack)
  ```bash
  # Terminal 1
  uvicorn backend.main:app --reload
  # Terminal 2
  cd frontend && npm install && npm run dev
  # Browser: http://localhost:3000
  ```

  Routes: `/` (dashboard), `/agents/[id]` (detail), `/debate` (replay),
  `/live` (live run, ~$0.05 / click).

  ## Offline mode (demo fallback)
  Set `OFFLINE_MODE=true` trong `.env` → `/live/run` trả 503 thân thiện.
  `/debate` vẫn dùng cached transcripts. Cứu cánh khi mất wifi.

  ## Project conventions
  Đọc `CLAUDE.md` (universal rules, domain-specific invariants).
  PRD: `.agent/PRD.md`. Tasks: `.agent/TASKS.md`.

  ## Reproducibility
  Same seed → identical trajectory. LLM cached by `(date, ticker_set, prompt_hash)`.
  `python -m src.eval.run_all` phải sinh identical `metrics_table.csv` ở 2nd run.

  ## License
  Academic use only (thesis). Test period 2025-05 → 2026-04 dùng dữ liệu
  vnstock public API.
  ```
- **PATTERN**: Tham khảo `CLAUDE.md` cho voice + format. Keep concise — runbook
  không phải tutorial.
- **GOTCHA**: Đừng duplicate CLAUDE.md content; chỉ link tới nó.
- **VALIDATE**:
  ```bash
  test -f README.md
  wc -l README.md  # Expected: ~80-150 lines
  ```

### Task 15: VALIDATE — full test suite + ruff + ts

> (matplotlib dep was handled in Task 13a as a precondition.)

- **IMPLEMENT**: Sequential:
  ```bash
  ruff check src/ tests/ backend/ scripts/
  ruff format --check src/ tests/ backend/ scripts/
  .venv/bin/pytest                              # all 255+ tests
  cd frontend && npx tsc --noEmit && npm run build
  ```
- **GOTCHA**: Nếu test mới (Task 7) fail, fix là priority. Existing tests
  KHÔNG được break — nếu break thì rollback Task 5 hoặc Task 6.
- **VALIDATE**: Tất cả 4 lệnh exit 0.

### Task 16: COMMIT + PR

- **IMPLEMENT**: Commits từng phase (theo CLAUDE.md "Per package" workflow):
  - `PKG-S: OFFLINE_MODE config + backend short-circuit (S3)`
  - `PKG-S: GET /debate/{agent} list endpoint (BE + FE + test)`
  - `PKG-S: full multi_agent backtest results (50 sessions, $2.50)`
  - `PKG-S: scripts/make_figures.py + 4 PNG report figures (S5b)`
  - `PKG-S: README.md runbook`
  - `PKG-S: pyproject add matplotlib` (nếu cần)

  PR body: `Closes #<N>` — **verify issue number first** với
  `gh issue list --search "PKG-S"`; PRs đã ship đến #35 nhưng issue numbering
  có thể không khớp 1:1. Link checkpoint
  `20260517-102505-pkg-16-merged-pkg-s-only-package-remaining.md`.
- **GOTCHA**: CLAUDE.md project rule — KHÔNG thêm `Co-Authored-By: Claude`
  trailer; KHÔNG thêm `🤖 Generated with Claude Code` footer.
- **VALIDATE**: `gh pr view --json url`

### Task 17 (POST-MERGE MANUAL — không phải code): REHEARSAL + LOOM

Documented checklist for Duc sau khi PR merge:

- [ ] **S2 — End-to-end click-through**:
  - Terminal 1: `uvicorn backend.main:app`
  - Terminal 2: `cd frontend && npm run dev`
  - Browser:
    - [ ] `/` — 8 agent cards, click multi_agent
    - [ ] `/agents/multi_agent` — chart + metrics
    - [ ] `/debate` — DatePicker shows 50 dates (post-S5a), pick 1 → transcript renders
    - [ ] `/live` — "Run for today" → 8 agent cards sáng đèn → portfolio weights
  - [ ] Console không có error
  - [ ] Network tab: tất cả 200 (debate fetches + SSE 200)
- [ ] **S4 — Loom recording**:
  - Set `OFFLINE_MODE=false`, real OPENAI_API_KEY
  - Record 60-90s clean run: click "Run for today" → đợi 8 agents → decision panel
  - Audio: 1 dòng narration ("Đây là multi_agent debate live trên VN30, 8 vai trò
    phối hợp ra quyết định portfolio")
  - Export 1080p MP4 → `report/demo_fallback.mp4`
  - Verify file plays, audio OK
- [ ] **S6 — Timed rehearsal (x2)**:
  - Stopwatch start → mở browser → click qua 4 routes → /live run → demo end
  - Target: ≤ 5 phút total
  - Lần 1: identify slow spots
  - Lần 2: smooth narration
- [ ] **Person 2 sign-off**:
  - Show test: `pytest tests/test_trading_env.py -v -k "lookahead"`
  - Show env code path: `_get_state()` không expose future data
  - Show news rule: `news_align.py` shifts D → D+1
  - Get verbal "no lookahead bias" approval

---

## TESTING STRATEGY

### Unit Tests

- **Backend** (`tests/backend/test_debate_routes.py`): list endpoint
  empty/populated/wrong-agent paths.
- **Backend** (`tests/backend/test_live_routes.py` nếu có, hoặc thêm): OFFLINE_MODE
  toggle → 503; off → normal flow (mock LLM).
- **Config** (existing `tests/test_config.py` nếu có): `_bool` helper truthy/falsy
  parsing.
- **Frontend**: KHÔNG thêm JS tests (continuing convention, checkpoint note).

### Integration Tests

- `pytest` whole suite must remain green (255+ tests, all PRs).
- `python -m src.eval.run_all` re-runs → bit-identical `metrics_table.csv`
  (reproducibility, PRD §15).

### Edge Cases

- **OFFLINE_MODE=true mid-stream**: không khả thi (config read at module
  import) — document trong PR: env change requires restart.
- **Multi_agent backtest mid-fail**: transcripts đã ghi vẫn dùng được;
  decisions.jsonl shows partial count. Re-run với `--resume` không có
  (PKG-8 scope) → phải `--reset-transcripts` + chạy lại full.
- **Empty `transcripts/` dir** trước S5a hoàn tất: list endpoint trả
  `dates: []`; frontend empty state hiển thị message hướng dẫn.
- **OPENAI_API_KEY missing khi `OFFLINE_MODE=false`**: backend crash bình
  thường (PKG-12 behavior unchanged).

---

## VALIDATION COMMANDS

### Level 1: Syntax & Style

```bash
ruff check src/ tests/ backend/ scripts/
ruff format --check src/ tests/ backend/ scripts/
```

### Level 2: Unit Tests

```bash
.venv/bin/pytest
```

### Level 3: Integration

```bash
.venv/bin/python -m src.eval.run_all        # regen metrics, bit-identical 2nd run
.venv/bin/python scripts/make_figures.py    # 4 PNG sinh ra
```

### Level 4: Manual

```bash
# Backend smoke
.venv/bin/uvicorn backend.main:app --port 8000 &
sleep 2
curl -sS http://localhost:8000/healthz
curl -sS http://localhost:8000/debate/multi_agent | python -m json.tool   # dates list
curl -sS http://localhost:8000/debate/multi_agent/2025-05-05 | head -c 200
kill %1

# Frontend build
cd frontend && npm run build

# Full end-to-end (manual rehearsal, Task 18)
```

### Level 5: OFFLINE_MODE smoke

```bash
OFFLINE_MODE=true .venv/bin/uvicorn backend.main:app --port 8000 &
sleep 2
curl -sS -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/live/run
# Expected: 503
curl -sS http://localhost:8000/debate/multi_agent | python -m json.tool
# Expected: 200, dates list (cached transcripts still served)
kill %1
```

---

## ACCEPTANCE CRITERIA

From TASKS.md PKG-S spec §"Acceptance criteria (final go for defense)":

- [ ] Demo end-to-end 5 phút không crash (Task 17 rehearsal x2)
- [ ] Mọi unit test pass: `pytest` clean (Task 15)
- [ ] `ruff check` + `ruff format --check` clean (Task 15)
- [ ] Loom video sẵn sàng tại `report/demo_fallback.mp4` (Task 17 S4)
- [ ] Người 2 ký off "no lookahead bias" (Task 17 sign-off)
- [ ] Người 1 đã có đủ chart + metrics: `report/figures/*.png` + `results/metrics_table.csv` (Tasks 12, 13)

**Plus PKG-S-specific:**
- [ ] Registry import smoke pass (Task 2)
- [ ] OFFLINE_MODE=true → 503 trên /live/run (Task 5)
- [ ] `GET /debate/multi_agent` returns ~50 dates (Tasks 6, 8)
- [ ] Frontend /debate page hiển thị + chọn được nhiều dates (Task 11)
- [ ] Full multi_agent backtest: `n_steps ≈ 50`, `llm_cost_usd ≈ 2.5` (Task 8)
- [ ] `README.md` exists, runbook complete (Task 14)
- [ ] PR merged (Task 16)

---

## COMPLETION CHECKLIST

- [ ] Branch `duc/PKG-S-integration` created from `main` (Task 1)
- [ ] Registry verified (Task 2)
- [ ] OFFLINE_MODE config + .env.example (Tasks 3, 4)
- [ ] live.py short-circuit + manual curl validation (Task 5)
- [ ] debate.py list endpoint + test (Tasks 6, 7)
- [ ] Full multi_agent backtest results in `results/multi_agent/` (Task 8)
- [ ] Frontend types + api + page (Tasks 9, 10, 11)
- [ ] metrics_table.csv regen (Task 12)
- [ ] matplotlib precondition (Task 13a)
- [ ] 4 PNG figures in `report/figures/` (Task 13)
- [ ] README.md root (Task 14)
- [ ] Full validation suite green (Task 15)
- [ ] Commits + PR (Task 16)
- [ ] PR merged
- [ ] Manual rehearsal x2 done (Task 17)
- [ ] Loom recorded (Task 17)
- [ ] Person 2 sign-off (Task 17)

---

## NOTES

### Design decisions
- **OFFLINE_MODE = JSONResponse 503**, không phải SSE error event: vì user-facing
  expectation là "503 = server cố tình từ chối", phù hợp HTTP semantics. Frontend
  `lib/sse.ts` already handles non-200 → error banner (PKG-16 D5).
- **Debate list endpoint URL** = `GET /debate/{agent}` (không `/{agent}/dates`):
  cleaner, không collision với existing `/{agent}/{date}` (FastAPI dispatch
  by full path match).
- **make_figures.py độc lập, không tích hợp `run_all.py`**: Người 1 chỉ cần
  PNG; tích hợp = thêm matplotlib import vào core eval path (over-coupling).
  Keep them separate.
- **KHÔNG có `--resume` flag cho run_multi_agent.py**: out of PKG-S scope
  (PKG-8 design); nếu fail mid-run dùng `--reset-transcripts` + chạy lại.

### Trade-offs
- **Cost $2.50 vs honest numbers**: full backtest tốn ~$2.50 (within budget),
  cho phép report nói "multi_agent N=50" thay vì "smoke N=4". Budget cumulative
  hậu PKG-S ~ $3.00, vẫn well within $30-60 budget.
- **`/debate` URL `/{agent}` vs `/{agent}/dates`**: trade off path simplicity
  vs explicitness. Chọn simplicity.
- **README ngắn vs dài**: ngắn (1 trang) — runbook là entry point, không
  phải tutorial. Tutorial sống trong notebooks/.

### Risks
- **OpenAI rate-limit khi Task 8**: PKG-5 client có retry, nhưng nếu sustained
  429 thì backtest chậm hơn 25 phút. Mitigation: chạy late evening VN time
  (sáng US, lower load).
- **matplotlib chart format mismatch column names**: VALIDATE step trong Task
  13 yêu cầu inspect parquet columns trước. Nếu trật, fix script.
- **Time pressure 14 ngày trước deadline**: Tasks 1-17 ~ 1 day. Tasks 18 manual
  ~ 0.5 day. Buffer ~ 12.5 days cho report writing + slides + debug surprises.

### Out of scope (do NOT do)
- T+2 settlement implementation (nice-to-have, không trong PKG-S).
- Multi-seed variance study (out per PRD §4).
- New strategy/agent additions (frozen post-PKG-10).
- DDPG re-tune (saturated tanh issue documented in PRD §14 Risk #7; PPO is
  the backup story for report).
- Real-money trading hookup (out per PRD §4).
- Public deployment / Vercel push (out per PRD §4).

### Next session start (post-merge)
- `git log --oneline -3` → confirm PKG-S PR merged
- 18/18 packages done
- Pivot to: report writing (Người 1 lead, Duc support figures),
  defense slides, rehearsal narration
