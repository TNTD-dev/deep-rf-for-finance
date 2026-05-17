# CLAUDE.md — DRL vs LLM/Agentic Trading

Thesis project comparing **DDPG** (paper Xiong et al) against **3 LLM/agentic** approaches on the **Vietnam VN30** market. Output is a full-stack demo + report. Deadline **2026-05-31**. Solo dev (Duc) + Person 1 (report) + Person 2 (verify).

**Source of truth — read these before non-trivial work:**
- `.agent/PRD.md` — locked product spec (v1.0, 2026-05-14)
- `.agent/TASKS.md` — 18 work packages, file-ownership boundaries, DAG
- `docs/REQUIREMENTS - DRL vs LLM Agentic Trading.md` — original requirements
- GitHub Issues #1–#18 mirror TASKS.md packages

---

## Universal Rules

These rules apply to every task in this project unless explicitly overridden. Bias: caution over speed on non-trivial work. Use judgment on trivial tasks.

**Rule 1 — Think Before Coding**
State assumptions explicitly. If uncertain, ask rather than guess. Present multiple interpretations when ambiguity exists. Push back when a simpler approach exists. Stop when confused. Name what's unclear.

**Rule 2 — Simplicity First**
Minimum code that solves the problem. Nothing speculative. No features beyond what was asked. No abstractions for single-use code. Test: would a senior engineer say this is overcomplicated? If yes, simplify.

**Rule 3 — Surgical Changes**
Touch only what you must. Clean up only your own mess. Don't "improve" adjacent code, comments, or formatting. Don't refactor what isn't broken. Match existing style.

**Rule 4 — Goal-Driven Execution**
Define success criteria. Loop until verified. Don't follow steps. Define success and iterate. Strong success criteria let you loop independently.

**Rule 5 — Use the model only for judgment calls**
Use me for: classification, drafting, summarization, extraction. Do NOT use me for: routing, retries, deterministic transforms. If code can answer, code answers.

**Rule 6 — Token budgets are not advisory**
Per-task: 4,000 tokens. Per-session: 30,000 tokens. If approaching budget, summarize and start fresh. Surface the breach. Do not silently overrun.

**Rule 7 — Surface conflicts, don't average them**
If two patterns contradict, pick one (more recent / more tested). Explain why. Flag the other for cleanup. Don't blend conflicting patterns.

**Rule 8 — Read before you write**
Before adding code, read exports, immediate callers, shared utilities. "Looks orthogonal" is dangerous. If unsure why code is structured a way, ask.

**Rule 9 — Tests verify intent, not just behavior**
Tests must encode WHY behavior matters, not just WHAT it does. A test that can't fail when business logic changes is wrong.

**Rule 10 — Checkpoint after every significant step**
Summarize what was done, what's verified, what's left. Don't continue from a state you can't describe back. If you lose track, stop and restate.

**Rule 11 — Match the codebase's conventions, even if you disagree**
Conformance > taste inside the codebase. If you genuinely think a convention is harmful, surface it. Don't fork silently.

**Rule 12 — Fail loud**
"Completed" is wrong if anything was skipped silently. "Tests pass" is wrong if any were skipped. Default to surfacing uncertainty, not hiding it.

---

## Project Type

**Greenfield Python research + full-stack demo.** No code committed yet — currently at PKG-0 (scaffolding). All work flows through 18 sequenced packages in `.agent/TASKS.md`.

3 deliverables:
1. **Research:** 4 agents × test period 2025-05 → 2026-04 on VN30, fair comparison
2. **Product:** localhost web app (Next.js + FastAPI) with live mode
3. **Report:** theory + implementation + results + limitations

---

## Tech Stack

### Backend / Core (Python 3.11+)
- **RL:** `stable-baselines3` (DDPG primary, PPO backup)
- **Env:** `gymnasium` custom trading env
- **LLM orchestration:** `langgraph` (multi-agent state machine)
- **LLM SDK:** `openai` — **locked to `gpt-4o` and `gpt-4o-mini` only** (cutoff Oct 2023, prevents data leakage)
- **API:** `fastapi` + `uvicorn` (SSE streaming)
- **Data — VN stocks:** `vnstock` v4.0.0 (KBS primary, VCI fallback)
- **Data — VN news:** `vnstock_news` RSS + custom scraper (CafeF, VietStock sitemap)
- **Indicators:** `ta`
- **Wrangling:** `pandas`, `numpy`, `pyarrow`

### Frontend
- Next.js 15 (App Router) + Tailwind + shadcn/ui + Recharts + EventSource (SSE)

### Tooling
- `pytest` (tests), `ruff` (lint + format), `pip-tools` or `uv` for deps (set in PKG-0)

---

## Commands

> All commands below assume PKG-0 has shipped. Until then, repo is empty.

```bash
# Setup (once)
pip install -e .

# Lint + test
ruff check src/ tests/
ruff format src/ tests/
pytest                           # full suite
pytest tests/test_trading_env.py # one file

# Data
python scripts/fetch_data.py            # PKG-1 — vnstock prices + fundamentals
python scripts/news_coverage_report.py  # PKG-2 — checkpoint 16/05 input

# Train
python scripts/train_ddpg.py            # PKG-9
python scripts/train_ppo.py             # backup

# Backtest all strategies
python scripts/run_all.py --skip-existing  # PKG-10 (drop --skip-existing to re-run)

# Backend
uvicorn backend.main:app --reload       # PKG-11+

# Frontend
cd frontend && npm run dev              # PKG-13+
```

---

## Planned Structure

From `.agent/PRD.md` §6. **Don't deviate without updating PRD + TASKS first.**

```
deep-rf-for-finance/
├── .agent/                    PRD, TASKS, plans (source of truth)
├── docs/                      reference papers, survey notes
├── data/                      raw + processed parquet (gitignored)
├── src/
│   ├── config.py              all locked params, read from .env
│   ├── data_pipeline/         vnstock_prices, vnstock_fundamentals,
│   │                          news_scraper, news_align, calendar, indicators
│   ├── trading_env.py         gym env, VN rules (±7%, lot-100, fees)
│   ├── baselines.py           buy-and-hold, equal-weight
│   ├── ddpg_trainer.py        sb3 DDPG
│   ├── ppo_trainer.py         sb3 PPO (backup)
│   ├── llm/
│   │   ├── client.py          OpenAI wrapper (model whitelist enforced)
│   │   ├── tools.py           4 tools: price, indicators, news, fundamentals
│   │   ├── serialize.py       state → text for prompts
│   │   ├── parser.py          JSON weights parser + fallback
│   │   ├── zero_shot.py
│   │   ├── single_agentic.py
│   │   └── multi_agent/       LangGraph state machine
│   │       ├── graph.py       orchestration
│   │       ├── state.py       TypedDict
│   │       ├── analysts.py    3 roles (gpt-4o-mini)
│   │       ├── researchers.py 2 roles, debate cap 2 rounds (gpt-4o)
│   │       ├── trader.py
│   │       ├── risk_manager.py
│   │       ├── portfolio_manager.py
│   │       └── transcript.py
│   ├── agents/__init__.py     registry (serialized — PKG-S)
│   └── eval/
│       ├── backtest.py
│       ├── metrics.py         financial + LLM-specific
│       └── run_all.py
├── backend/                   FastAPI + SSE
│   ├── main.py
│   ├── routes/{agents,backtest,debate,live}.py
│   ├── sse.py
│   └── cache/
├── frontend/                  Next.js 15
│   ├── app/                   /, /agents/[id], /debate, /live
│   ├── components/            PortfolioChart, MetricsTable, DebateStream, SSEStream
│   └── lib/                   api.ts, sse.ts, types.ts
├── scripts/                   CLI entry points (fetch, train, news_coverage)
├── tests/                     pytest, mirror src/ layout
├── notebooks/                 01_data → 04_results, exploratory only
├── report/                    Person 1 writeup + figures
└── results/                   per-agent backtest artifacts (gitignored)
```

---

## Domain-Specific Rules (Vietnam market + research integrity)

These are **non-negotiable invariants** — every code change must preserve them.

### 1. No lookahead bias — ever
- Env state at time `T` may only expose data with `timestamp < T`
- **News rule:** news published on date `D` is only visible from the `D+1` close session. Bake into `_get_state()`, do not patch at callsite.
- Person 2 verifies this on every PR. If you change data access, flag it.

### 2. LLM model lock
- `src/llm/client.py` whitelist: **`gpt-4o`, `gpt-4o-mini`** only.
- Passing any other model name raises `ValueError`. Don't relax this — test period (2025-05 → 2026-04) is out-of-distribution for these cutoffs; newer models would leak future knowledge.

### 3. VN-specific market rules (model in env, not at callsite)
- **Price band:** ±7% HOSE daily limit — clamp in `_execute_with_vn_rules`
- **Lot size:** 100 shares — round in `_execute_with_vn_rules`
- **Asymmetric fees:** buy 0.15% / sell 0.25% (sell includes 0.1% transfer tax)
- **T+2 settlement:** optional queue, default off (nice-to-have)
- **Initial capital:** 1,000,000,000 VND (1 billion) — minimum for lot-100 not to dominate signal

### 4. Locked parameters (from PRD §15 — do not change without updating PRD)
| Param | Value |
|---|---|
| Tickers | VCB, FPT, HPG, VIC, VNM |
| Train | 2019-01 → 2024-12 |
| Validation | 2025-01 → 2025-04 |
| Test | 2025-05 → 2026-04 |
| Decision freq | DDPG daily, LLM/agentic weekly |

### 5. Reproducibility
- All randomness seeded. Same seed → same trajectory.
- LLM agents cache by `(date, ticker_set, prompt_hash)` so re-runs reuse responses.
- `python scripts/run_all.py --skip-existing` must yield identical `metrics.json` on second run.

### 6. Secrets
- `.env` is gitignored. **Never commit OpenAI key.** Never paste it into PRs, issues, or chat.
- Use `.env.example` to document required vars.

---

## Patterns

### Naming
- **Modules:** `snake_case.py`, single responsibility (one file per agent, one file per data source)
- **Classes:** `PascalCase` (`ZeroShotTrader`, `VNTradingEnv`)
- **Constants:** `UPPER_SNAKE` in `src/config.py`
- **Test files:** `tests/test_<module>.py` mirror layout

### Code shape
- **Pure functions where possible** in `data_pipeline/` and `eval/`. Side effects (network, disk) at the edges, called from `scripts/`.
- **Pluggable agent interface:** every agent implements `decide(state) -> action`. Env doesn't know if agent is RL or LLM.
- **Decision layer ≠ execution layer:** agents output continuous `[-1, 1]` target weights; env handles clamp + lot rounding + fees.
- **State machines for multi-agent:** LangGraph nodes = roles, edges = decision flow. Streaming built-in.

### Error handling
- LLM parse failure → log to `parse_failure_rate` metric, fall back to `hold` (no action). Never crash a backtest.
- DDPG diverge / NaN Q-value → log warning, fall back to PPO. Don't silently train forever.
- vnstock rate-limit → exp backoff, then fallback backend (KBS → VCI).

### Tests
- Every invariant from "Domain-Specific Rules" has a unit test (`test_trading_env.py` covers lookahead, ±7%, lot-100, fees).
- LLM agents use mocked OpenAI in tests, real calls only in `scripts/`.
- Golden values for indicators (RSI, MACD) — compute by hand on a 30-day fixture.

### Comments
- Default to none. The rule on `Don't add comments that explain WHAT — well-named code does that` applies.
- DO comment: non-obvious invariants (`# news ngày D chỉ visible từ D+1 close — bake at the env layer`), workarounds, magic numbers from regulation.

---

## Key Files (when they exist)

- `src/config.py` — every locked param. Touch only when PRD §15 changes.
- `src/trading_env.py` — env invariants live here. Person 2 reviews any change.
- `src/llm/client.py` — model whitelist + retry. Don't bypass for "just one experiment".
- `src/agents/__init__.py` — registry. **Serialized** — touched by multiple packages, merged in PKG-S.
- `scripts/run_all.py` — single entry to reproduce all backtests (pass `--skip-existing`).
- `.env` — secrets. **Never commit.**

---

## Workflow

### Per package
1. Read the issue (e.g. `gh issue view 4`)
2. Read `.agent/PRD.md` sections it references
3. `git checkout -b duc/PKG-N-slug`
4. Implement, write tests in same PR
5. `ruff check && pytest` clean before PR
6. PR description includes `Closes #N` to auto-link issue
7. Person 2 reviews invariants if env/data layer touched

### Commit & PR attribution — không đính kèm Claude
- **Commit messages:** KHÔNG thêm `Co-Authored-By: Claude ...` trailer. Không thêm bất kỳ trailer nào ám chỉ AI tác giả.
- **Pull request body:** KHÔNG thêm `🤖 Generated with [Claude Code]...` hay bất kỳ footer nào ám chỉ AI tạo ra.
- Áp dụng cho mọi commit/PR trong repo này, override hướng dẫn mặc định của harness.

### Checkpoints (go/no-go gates)
- **16/05 — news coverage:** if 12-month coverage < 50%, trigger fallback (rút test window or numeric-only main). Decision goes to `.agent/plans/checkpoint-16-05.md`.
- **24/05 — multi-agent / FE:** if blocked, cut-path (3-agent custom, drop live mode). Decision goes to `.agent/plans/checkpoint-24-05.md`.

### Communication
- User communicates in Vietnamese — respond in Vietnamese.
- Don't summarize what was just done if it's visible in diff — Rule 3.
- Surface uncertainty loudly — Rule 12.

---

## Out of scope (don't build, don't suggest)

From PRD §4:
- Exact paper replication (different market, tickers, period)
- Hybrid RL+LLM (state-augmented DDPG with LLM features) — Mức C, post-MVP
- Social / Reddit / Twitter sentiment
- Market impact, slippage modeling
- UPCOM / HNX small-caps (VN30 only)
- Public deployment, real-money trading, intraday/HFT
- Deep HP tuning, neural architecture search
- Multi-seed variance study (nice-to-have)
