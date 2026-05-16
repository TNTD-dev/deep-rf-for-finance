# Feature: PKG-8 — Multi-Agent LangGraph (6 roles)

> The biggest, riskiest package. 6 LLM roles in a LangGraph state machine:
> 3 Analysts → Bull/Bear debate (≤ 2 rounds) → Trader → Risk Manager →
> Portfolio Manager (final weights). Per-portfolio decision, streamable,
> transcript stored per date.
>
> Scope-control gate at CHECKPOINT 24/05 — if multi-agent over-runs, cut to
> 3-agent custom (Technical + Fundamental + Trader, no debate, no risk
> manager). This plan ships the full stack; cut-path documented separately
> in `.agent/plans/checkpoint-24-05.md` if triggered.

## Feature Description

`MultiAgentTrader` implements the `Agent` Protocol (`src/agent_base.py`).
On a weekly cadence (first trading day of each ISO week), it:

1. Pre-fetches per-ticker data via `LookaheadSafeTools` (Python-side, NOT
   LLM tool_calls — keeps determinism + bounds cost)
2. Invokes the compiled LangGraph `app` with an initial `MultiAgentState`
3. The graph walks: `START → 3 analysts → debate (bullish ↔ bearish, ≤2 rounds)
   → trader → risk_manager → portfolio_manager → END`
4. `portfolio_manager` writes JSON weights into state; `MultiAgentTrader`
   parses via `parse_weights_json` (PKG-5)
5. Full transcript (one entry per role, plus debate exchanges) saved to
   `results/multi_agent/transcripts/<date>.json`
6. Decision summary appended to `results/multi_agent/decisions.jsonl`
   (for PKG-10 metrics + debate replay UI in PKG-15)

Per-decision wallclock budget: **30s** (PRD §14 Risk #5). Enforced via
`concurrent.futures.ThreadPoolExecutor.future.result(timeout=30)`; timeout →
hold-shares fallback + log + audit.

Per-decision cost target: **~$0.30** with mixed model lineup
(Analysts gpt-4o-mini ≈ $0.02 × 3, debate + Trader + Risk + Portfolio
gpt-4o ≈ $0.05 × 6 = $0.30). 51 weeks × $0.30 = **~$15/backtest** — meets
Issue #9 acceptance "cost report < $15".

## User Story

As a **PKG-10 backtest runner**
I want to **construct `MultiAgentTrader(market_data, news_data)` and pass
it to `run_backtest`** without touching LangGraph internals
So that **the agent comparison harness treats multi-agent identically to
zero-shot, single-agentic, DDPG, and baselines (same env, same seed)**.

As a **PKG-15 debate replay UI**
I want **structured transcripts per decision date with role-tagged messages
in causal order**
So that **the streaming replay shows analysts → debate → trader → risk →
portfolio manager exactly as the decision happened**.

As a **report writer (Person 1)**
I want **per-decision cost + latency + debate-round-count + role-output
metrics**
So that **the report's "multi-agent vs others" section quantifies overhead
vs quality lift**.

As a **CHECKPOINT 24/05 gate**
I want **a clear cut-path documented (3-agent custom, drop debate + risk
manager)**
So that **if PKG-8 overruns by 24/05, we can ship a degraded-but-working
multi-agent in < 1 day**.

## Problem Statement

5 distinct challenges this package solves:

1. **Coordination at scale.** Six LLM roles, each with its own prompt,
   role-specific data slice, and a 2-round debate loop. Done ad-hoc, this
   becomes spaghetti. LangGraph gives a typed `StateGraph` so the data
   contract between nodes is the single source of truth.
2. **Debate termination.** "Bullish researcher argues, bearish responds,
   bullish counters, bearish counters" must STOP. Without a hard counter
   in state + conditional edge, the LLMs will happily debate forever
   (cost + latency blow-up).
3. **Transcript-as-product.** The web UI (PKG-15) and the report both
   read transcripts. They must be: structured (one record per role,
   ordered), complete (no silent drops on failure), and small enough to
   serve over SSE.
4. **30s per-decision wallclock.** With 5 retries × 4 backoff and 9-12
   sequential LLM calls per decision worst-case, raw chain could exceed
   30s. Need outer timeout that always returns *something* (hold-shares).
5. **Cost ceiling.** PRD §14 Risk #5: budget $30-60 across all backtests.
   PKG-8 alone could blow this if naive (e.g., gpt-4o on every role +
   uncapped debate). Solution: mixed model lineup + hard debate cap +
   per-decision audit so PKG-10 surfaces breach before re-running.

## Solution Statement

10 design decisions LOCK before code (see DESIGN DECISIONS for details):

- **D1.** Single typed `MultiAgentState` (TypedDict) flows through the
  graph; per-key reducers handle append-list semantics
- **D2.** Nodes are plain Python functions, NOT langchain Runnables —
  they call PKG-5 `OpenAIClient` directly (preserves metrics + whitelist
  + retry; no langchain runtime in our hot path)
- **D3.** Mixed model lineup: Analysts → gpt-4o-mini; Researchers/Trader/
  Risk/Portfolio → gpt-4o
- **D4.** Debate counter in state; conditional edge re-enters debate
  while `debate_round < 2`; hard structural cap (don't trust LLM to stop)
- **D5.** Per-decision wallclock cap = 30s; enforced via
  `ThreadPoolExecutor.future.result(timeout=30)`; on timeout: hold-shares
- **D6.** Weekly cadence + cached weights (mirror PKG-6/7 exactly)
- **D7.** Transcript = JSON per decision date + JSONL decisions log;
  written by `transcript.py`, called inside `MultiAgentTrader.decide`
  AFTER graph completes (or on timeout, write partial)
- **D8.** Analysts pre-fetch data via `LookaheadSafeTools` in Python
  (NOT via LLM tool_calls) — deterministic, bounded cost, simpler audit
- **D9.** Portfolio Manager is the SOLE producer of JSON weights;
  reusing PKG-5 `parse_weights_json` → action ndarray
- **D10.** Any node failure → log + record metric + downstream nodes get
  "FAILURE: <role>" string in their input → graph still reaches portfolio
  manager → falls back to hold-shares via parser

## Feature Metadata

- **Feature Type:** New Capability (largest in project — biggest scope
  + tightest integration with PRD risk register)
- **Estimated Complexity:** **High** — 6 roles × 8 prompt files × graph
  orchestration × debate loop × timeout × transcript × tests. **Plan
  intentionally over-specifies** because one-pass execution matters more
  here than in any other package.
- **Primary Systems Affected:**
  - New module dir: `src/llm/multi_agent/`
  - New prompt dir: `src/llm/prompts/multi_agent/`
  - New CLI: `scripts/run_multi_agent.py`
  - 3-4 new test files under `tests/`
  - New output dir: `results/multi_agent/` (gitignored)
- **Dependencies:** `langgraph>=0.2` + `langchain-openai>=0.2` already in
  `pyproject.toml`; verified installed (langgraph 1.2.0, langchain-openai
  1.2.1) — but we only import `langgraph` (state graph primitives), NOT
  `langchain_openai` (we keep using PKG-5 `OpenAIClient`).
- **CHECKPOINT GATE:** 24/05 — if PKG-8 not merged by EOD, trigger
  cut-path defined in plan §"Cut-Path".

---

## CONTEXT REFERENCES

### Relevant Codebase Files — ĐỌC TRƯỚC KHI IMPLEMENT

**Reuse bắt buộc (PKG-5):**

- `src/llm/client.py` — `OpenAIClient.chat(model, messages, temperature)`
  + `ChatResult`; model whitelist enforced. Every multi-agent node calls
  this; reuses metrics counter + retry.
- `src/llm/parser.py` — `parse_weights_json(text, info, ticker_order)` +
  `_hold_shares_action(info, tickers)`; portfolio manager + fallback path.
- `src/llm/metrics.py` — `record_llm_call` auto-fires from client; `reset`
  + `get_snapshot` used by CLI; `record_parse_failure(reason=...)` called
  on graph timeout / node failure.
- `src/llm/serialize.py` — `state_to_text`, `holdings_to_text`,
  `indicators_to_text`, `news_to_bullets`. Each analyst node will call
  the SPECIFIC sub-serializer matching its role.
- `src/llm/tools.py` — `LookaheadSafeTools(market_data, news_data, asof)`
  with `.get_price_history`, `.get_indicators`, `.get_news`,
  `.get_fundamentals`. **Used Python-side from analyst nodes**, NOT via
  LLM tool_calls (D8).
- `src/data_pipeline/news_align.py` — `visible_news_at` (indirect via tools).

**Reuse bắt buộc (PKG-3/4):**

- `src/agent_base.py` — `Agent` Protocol + `BacktestResult` dataclass.
- `src/env_data_loader.py` — `MarketData` + `load_market_data(split)`.
- `src/baselines.py:_snapshot, _records_to_frames` — internal helpers
  the CLI imports (acceptable same-package).
- `src/trading_env.py` — `VNTradingEnv` (no changes; agent passed in).
- `src/baselines.py:run_backtest` (CLI full-run path).
- `src/config.py` — `TICKERS`, `LLM_ALLOWED_MODELS`, `INITIAL_CAPITAL`,
  `PROJECT_ROOT`.

**Pattern bắt buộc mirror:**

- `src/llm/single_agentic.py` (entire file, ~330 lines) — **the closest
  prior art**. Mirror exactly:
  - Weekly cadence (`_is_rebalance_day`, `_last_week`, `_cached`)
  - Constructor signature pattern (md, news, model, client, weekly_rebalance,
    audit_log_path)
  - Network failure → `metrics.record_parse_failure(reason="network_…")` +
    hold-shares
  - Audit log JSONL append; tests pass `tmp_path` path
- `src/llm/zero_shot.py` (~132 lines) — for the simpler weekly cadence
  reference + system prompt loading pattern.
- `src/llm/prompts/single_agentic.md` (~150 lines) — for prompt structure
  (role, universe, HOSE rules, output schema). The 8 multi-agent prompts
  copy the "preamble" (role + rules + universe) and add role-specific
  task sections.
- `tests/test_single_agentic.py` (entire file, ~430 lines) — `_FakeClient`
  + `_resp_text`/`_resp_tools` + `_info` builder patterns. The
  multi-agent test files extend these heavily.
- `tests/conftest.py:synthetic_market_data` — 60-session × 5-ticker
  fixture; the only fixture multi-agent tests will need beyond fakes.
- `scripts/run_single_agentic.py` (~190 lines) — CLI shape:
  `--split/--model/--seed/--n-sessions/--reset-audit/--max-iterations`.
  PKG-8 CLI mirrors with `--reset-transcripts` instead of `--reset-audit`.

**Read-only context (don't modify):**

- `CLAUDE.md` — §"Domain-Specific Rules" all 6 sections; §"Patterns"
  (decision-layer-≠-execution-layer, state-machines-for-multi-agent).
  CRITICAL: §"Commit & PR attribution — không đính kèm Claude" (no AI
  trailer in commits/PR).
- `.agent/PRD.md` §7 Feature 6 (the role list + mixed-model lineup);
  §14 Risk #5 (cost ceiling + mitigations); §11 Phase 3 (24/05 checkpoint).
- `.agent/TASKS.md:425-478` (full PKG-8 spec) + the 8A/8B split commentary.
- GitHub Issue #9 (`PKG-8: Multi-agent LangGraph (6 roles)`).
- TradingAgents paper: https://arxiv.org/abs/2412.20138 (Xiao et al);
  read §3 Architecture for role definitions and debate structure. We
  follow the paper's role taxonomy; our debate cap = 2 (paper allows
  more but we hard-cap for cost).

**Don't touch (file ownership):**

- `src/llm/{client,tools,serialize,parser,metrics}.py` — PKG-5 (merged).
  If you find a bug here, fix it in a separate commit within the PKG-8
  PR (mirror what PKG-7 did with `get_news` regression). Don't refactor.
- `src/llm/zero_shot.py`, `src/llm/single_agentic.py` — PKG-6/7.
- `src/baselines.py`, `src/trading_env.py`, `src/env_data_loader.py` —
  PKG-3/4.
- `src/agents/__init__.py` — PKG-S serialized (don't create yet).

### New Files to Create

```
src/llm/multi_agent/
├── __init__.py                   # exports MultiAgentTrader, build_app
├── state.py                      # MultiAgentState TypedDict + reducers
├── transcript.py                 # write per-date JSON + decisions.jsonl
├── nodes/
│   ├── __init__.py
│   ├── analysts.py               # 3 node fns (technical, news_sentiment, fundamental)
│   ├── researchers.py            # 2 node fns + debate router
│   ├── trader.py                 # 1 node fn
│   ├── risk_manager.py           # 1 node fn
│   └── portfolio_manager.py      # 1 node fn (final parse)
├── graph.py                      # build_graph(), build_app() — compiled graph
└── agent.py                      # MultiAgentTrader class (Agent Protocol)

src/llm/prompts/multi_agent/
├── technical_analyst.md
├── news_sentiment_analyst.md
├── fundamental_analyst.md
├── bullish_researcher.md
├── bearish_researcher.md
├── trader.md
├── risk_manager.md
└── portfolio_manager.md

scripts/run_multi_agent.py        # CLI mirror of run_single_agentic.py

tests/
├── test_multi_agent_state.py     # state reducers + initialization
├── test_multi_agent_transcript.py # JSON shape + JSONL append + partial-on-error
├── test_multi_agent_graph.py     # graph wiring, debate cap, node invocation order
└── test_multi_agent_agent.py     # MultiAgentTrader Protocol + weekly + timeout + fallbacks

results/multi_agent/              # gitignored
├── transcripts/<YYYY-MM-DD>.json
├── decisions.jsonl
├── portfolio_curve.parquet
└── holdings.parquet
```

**Why split tests across 4 files?** Mirrors the module split + keeps each
test file < 300 lines (matches conftest scale). `test_multi_agent_graph.py`
is the biggest (~10 tests on graph flow).

### Relevant Documentation — ĐỌC TRƯỚC KHI IMPLEMENT

- **LangGraph StateGraph quickstart:**
  https://langchain-ai.github.io/langgraph/tutorials/introduction/
  - Section: "Build a basic chatbot" → understanding `StateGraph`,
    `add_node`, `add_edge`, `add_conditional_edges`, `compile()`
- **LangGraph state reducers:**
  https://langchain-ai.github.io/langgraph/concepts/low_level/#reducers
  - `Annotated[list, operator.add]` for append-list semantics on debate
    exchanges + transcript records
- **LangGraph streaming modes:**
  https://langchain-ai.github.io/langgraph/concepts/streaming/
  - `app.stream(initial_state, stream_mode='updates')` yields per-node
    state updates — what PKG-12 SSE route will subscribe to
- **TradingAgents paper (Xiao et al, Dec 2024):**
  https://arxiv.org/abs/2412.20138
  - §3 Architecture (role taxonomy); §4.2 Debate (we cap at 2 rounds,
    paper allows N)
- **OpenAI Chat Completions** (same as PKG-6/7):
  https://platform.openai.com/docs/api-reference/chat/create
- **OpenAI prompt caching:**
  https://platform.openai.com/docs/guides/prompt-caching
  - Each role's system prompt must be ≥ 1024 tokens for auto-cache. 8 prompts
    × ~1500 tokens each × ~51 weeks → big savings.

### Pre-implementation spikes (run BEFORE coding)

**Spike A — LangGraph state + debate loop:**

```bash
.venv/bin/python <<'PY'
"""Verify LangGraph StateGraph + conditional debate loop works
end-to-end. No real LLM calls — just structural test."""
from typing_extensions import Annotated, TypedDict
from operator import add
from langgraph.graph import StateGraph, START, END


class S(TypedDict):
    debate_round: int
    exchanges: Annotated[list[str], add]
    summary: str


def bullish(s: S) -> dict:
    return {"exchanges": [f"BULL r{s['debate_round']}: rally"]}


def bearish(s: S) -> dict:
    # bearish increments the round (one full back-and-forth = 1 round)
    return {
        "exchanges": [f"BEAR r{s['debate_round']}: pullback"],
        "debate_round": s["debate_round"] + 1,
    }


def should_continue_debate(s: S) -> str:
    return "loop" if s["debate_round"] < 2 else "exit"


def trader(s: S) -> dict:
    return {"summary": "hold"}


g = StateGraph(S)
g.add_node("bullish", bullish)
g.add_node("bearish", bearish)
g.add_node("trader", trader)
g.add_edge(START, "bullish")
g.add_edge("bullish", "bearish")
g.add_conditional_edges(
    "bearish", should_continue_debate, {"loop": "bullish", "exit": "trader"}
)
g.add_edge("trader", END)
app = g.compile()

out = app.invoke({"debate_round": 0, "exchanges": [], "summary": ""})
print(f"final debate_round: {out['debate_round']}")
print(f"exchanges: {out['exchanges']}")
assert out["debate_round"] == 2, "cap should fire at round 2"
assert len(out["exchanges"]) == 4, "2 rounds × 2 speakers = 4 exchanges"
print("OK")
PY
```

Expected: `debate_round=2`, 4 exchanges total. Locks the cap mechanism
BEFORE wiring real nodes.

**Spike B — Streaming yields per-node updates:**

```bash
.venv/bin/python <<'PY'
"""Confirm app.stream(stream_mode='updates') gives one yield per node.
This is what PKG-12 will tail over SSE."""
from typing import TypedDict
from langgraph.graph import StateGraph, START, END


class S(TypedDict):
    x: int


def step1(s):
    return {"x": s["x"] + 1}


def step2(s):
    return {"x": s["x"] + 10}


g = StateGraph(S)
g.add_node("step1", step1)
g.add_node("step2", step2)
g.add_edge(START, "step1")
g.add_edge("step1", "step2")
g.add_edge("step2", END)
app = g.compile()
events = list(app.stream({"x": 0}, stream_mode="updates"))
print(f"event count: {len(events)}")
for e in events:
    print(f"  {e}")
assert len(events) == 2
PY
```

Expected: 2 events, each `{node_name: {patch}}`. PKG-12 will map this to
SSE messages.

**Spike C — 30s timeout via ThreadPoolExecutor:**

```bash
.venv/bin/python <<'PY'
"""Confirm thread-based timeout returns control even if graph hangs."""
import concurrent.futures
import time


def slow_graph_invoke(s):
    time.sleep(2)
    return {"action": "buy"}


with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
    fut = ex.submit(slow_graph_invoke, {"x": 0})
    try:
        result = fut.result(timeout=0.5)
        print("got:", result)
    except concurrent.futures.TimeoutError:
        print("OK timeout fired")
    # Note: future continues running in background. PKG-8 doesn't try
    # to cancel — it just abandons and falls back. The "leaked" thread
    # finishes ~1.5s later and is GC'd.
PY
```

Expected: `OK timeout fired`. Locks the timeout mechanism BEFORE wiring it
into `MultiAgentTrader.decide`.

### Patterns to Follow (from codebase đã land)

**Class shape + weekly cadence (mirror `src/llm/single_agentic.py:48-78`):**

```python
class MultiAgentTrader:
    name: str = "multi_agent"

    def __init__(
        self,
        market_data: MarketData,
        news_data: pd.DataFrame,
        models: dict[str, str] | None = None,  # role → model override
        client: OpenAIClient | None = None,
        weekly_rebalance: bool = True,
        debate_rounds: int = 2,
        decision_timeout_s: float = 30.0,
        transcript_dir: Path | None = _DEFAULT_TRANSCRIPT_DIR,
        decisions_log_path: Path | None = _DEFAULT_DECISIONS_PATH,
    ) -> None:
        ...
        self._last_week: tuple[int, int] | None = None
        self._cached: np.ndarray | None = None
        self._app = build_app(
            client=self._client,
            models=self.models,
            debate_rounds=self.debate_rounds,
        )

    def decide(self, obs, info) -> np.ndarray:
        # 1. weekly cache check (mirror PKG-7)
        # 2. build initial state
        # 3. invoke graph with timeout
        # 4. parse weights via portfolio_manager output
        # 5. write transcript + decision log
        # 6. cache + return
```

**Node function signature (LangGraph convention):**

```python
def technical_analyst(state: MultiAgentState) -> dict:
    """Pure function: takes full state, returns partial-update dict."""
    tools = state["tools"]
    md = state["market_data"]
    analyses = []
    for ticker in md.tickers:
        ind = tools.get_indicators(ticker)
        hist = tools.get_price_history(ticker, days=30)
        user_msg = _format_technical_brief(ticker, ind, hist)
        result = state["client"].chat(
            model=state["models"]["technical_analyst"],
            messages=[
                {"role": "system", "content": _PROMPTS["technical_analyst"]},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.0,
        )
        analyses.append(
            {"ticker": ticker, "report": result.text or ""}
        )
    return {
        "technical_reports": analyses,
        "transcript": [
            {
                "role": "technical_analyst",
                "ts": _now(),
                "input_summary": f"5 tickers indicators+30d history",
                "output": analyses,
                "usage": result.usage,  # approximate; last call's
            }
        ],
    }
```

**State reducers (`src/llm/multi_agent/state.py`):**

```python
from operator import add
from typing import TypedDict
from typing_extensions import Annotated, NotRequired

import numpy as np
import pandas as pd

from src.env_data_loader import MarketData
from src.llm.client import OpenAIClient
from src.llm.tools import LookaheadSafeTools


class MultiAgentState(TypedDict, total=False):
    # --- Inputs (set at initial state, never mutated) ---
    market_data: MarketData
    news_data: pd.DataFrame
    tools: LookaheadSafeTools
    client: OpenAIClient
    models: dict[str, str]            # role → model id
    info: dict                        # env info (date, holdings, pv, ...)
    universe: list[str]               # config.TICKERS

    # --- Analyst outputs (per ticker) ---
    technical_reports: list[dict]
    news_sentiment_reports: list[dict]
    fundamental_reports: list[dict]

    # --- Debate loop ---
    debate_round: int                 # incremented after each (bull, bear) pair
    debate_exchanges: Annotated[list[dict], add]  # ordered exchanges

    # --- Synthesis ---
    trader_proposal: str
    risk_review: str
    portfolio_manager_output: str     # raw text — parsed by MultiAgentTrader

    # --- Transcript (always appended) ---
    transcript: Annotated[list[dict], add]

    # --- Failure tracking ---
    node_errors: Annotated[list[dict], add]  # {role, error, ts}
```

**Mock OpenAI in tests** (mirror PKG-7 `_FakeClient` exactly; queue
responses in node-call order):

```python
@dataclass
class _FakeClient:
    responses: list[Any] = field(default_factory=list)
    calls: list[dict] = field(default_factory=list)
    raise_at: int | None = None

    def chat(self, **kwargs) -> ChatResult:
        idx = len(self.calls)
        self.calls.append(kwargs)
        if self.raise_at == idx:
            raise RuntimeError("simulated network failure")
        if not self.responses:
            raise RuntimeError("no fake responses queued")
        return self.responses.pop(0)
```

**Error handling (CLAUDE.md alignment):**

- Node LLM call exception → catch in node, append to `node_errors`,
  return empty report (`"FAILURE: <role>"` string downstream nodes see)
- Graph total wallclock > timeout → `TimeoutError` caught in
  `MultiAgentTrader.decide` → write partial transcript + hold-shares
- Portfolio manager parse failure → handled by `parse_weights_json` →
  hold-shares (mirrors PKG-6/7)
- Never propagate exceptions out of `decide()` — backtest must complete

---

## DESIGN DECISIONS — LOCK BEFORE IMPLEMENT

### D1. Single typed `MultiAgentState` TypedDict (see state.py spec above)

Why TypedDict vs Pydantic: LangGraph natively supports TypedDict; Pydantic
adds runtime validation overhead per node visit. We use Python-side
typing (mypy/ruff) + tests for invariants. `total=False` lets nodes
return partial updates without `NotRequired` markers on every field.

### D2. Nodes are plain Python functions, NOT langchain Runnables

```python
def technical_analyst(state: MultiAgentState) -> dict:
    ...  # plain function; takes state, returns dict patch
```

Why: PKG-5 `OpenAIClient` already wraps the OpenAI SDK with whitelist +
retry + metrics. Adopting `ChatOpenAI` from `langchain_openai` would:
- Bypass our model whitelist (CLAUDE.md §2 invariant)
- Double-instrument retries
- Hide call metrics from `metrics.record_llm_call` (since `_to_result`
  records, but only if WE call through `client.chat`)

LangGraph doesn't require Runnables — `add_node(name, plain_callable)`
works fine. We get the StateGraph orchestration without the
langchain runtime tax.

### D3. Mixed model lineup (locked in `MultiAgentTrader.__init__` defaults)

```python
_DEFAULT_MODELS: dict[str, str] = {
    "technical_analyst":      "gpt-4o-mini",
    "news_sentiment_analyst": "gpt-4o-mini",
    "fundamental_analyst":    "gpt-4o-mini",
    "bullish_researcher":     "gpt-4o",
    "bearish_researcher":     "gpt-4o",
    "trader":                 "gpt-4o",
    "risk_manager":           "gpt-4o",
    "portfolio_manager":      "gpt-4o",
}
```

Per-decision cost (estimate):
- 3 analysts × 5 tickers × gpt-4o-mini ≈ 15 calls × $0.001 = $0.015
- Debate: 2 rounds × 2 speakers × gpt-4o ≈ 4 calls × $0.04 = $0.16
- Trader: 1 × gpt-4o ≈ $0.04
- Risk: 1 × gpt-4o ≈ $0.04
- Portfolio: 1 × gpt-4o ≈ $0.04
- **Total: ~$0.30/decision; 51 weeks → ~$15/backtest** ✓ meets Issue #9.

User override: `MultiAgentTrader(models={"trader": "gpt-4o-mini"})` merges
with defaults. Validated against `config.LLM_ALLOWED_MODELS`.

### D4. Debate counter + conditional edge

```python
def bearish_researcher(state):
    # ... LLM call ...
    return {
        "debate_exchanges": [{"role": "bearish", "round": state["debate_round"], "text": ...}],
        "debate_round": state["debate_round"] + 1,  # bearish increments
    }

def _should_continue_debate(state) -> str:
    return "loop" if state["debate_round"] < state.get("debate_rounds_max", 2) else "exit"

# wiring:
g.add_edge("bullish_researcher", "bearish_researcher")
g.add_conditional_edges(
    "bearish_researcher",
    _should_continue_debate,
    {"loop": "bullish_researcher", "exit": "trader"},
)
```

**Critical:** `debate_round` increments in `bearish_researcher` (after a
full back-and-forth = 1 round). With cap = 2 we get exactly 4 LLM calls
(bull-bear-bull-bear), then `debate_round = 2` triggers exit.

Spike A locks this BEFORE any LLM code.

### D5. 30s wallclock cap via ThreadPoolExecutor

```python
import concurrent.futures

def decide(self, obs, info):
    ...
    initial = self._build_initial_state(info)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(self._app.invoke, initial)
        try:
            final_state = fut.result(timeout=self.decision_timeout_s)
        except concurrent.futures.TimeoutError:
            log.warning("multi_agent timeout %ss at %s", self.decision_timeout_s, info.get("date"))
            metrics.record_parse_failure(reason="multi_agent_timeout")
            action = _hold_shares_action(info, list(self.market_data.tickers))
            self._write_decision_log(info, partial=True, action=action, timed_out=True)
            self._cached = action
            return action.copy()
```

The background thread keeps running after timeout (no good way to cancel
mid-OpenAI-call). We accept the orphaned thread — it completes naturally
in ~30-60s and is GC'd. Spike C confirms.

**Why not asyncio?** PKG-5 `OpenAIClient` is sync; converting would
require touching PKG-5 (file ownership violation). Threadpool is the
right interop layer.

### D6. Weekly cadence (mirror PKG-7 exactly)

Same `_is_rebalance_day` using ISO week. Same `_cached` ndarray.
Same toggle `weekly_rebalance: bool = True`.

### D7. Transcript = JSON per date + JSONL decisions log

`results/multi_agent/transcripts/2025-05-05.json`:
```json
{
  "date": "2025-05-05",
  "agent": "multi_agent",
  "duration_s": 18.4,
  "debate_rounds": 2,
  "node_errors": [],
  "timed_out": false,
  "models_used": {"technical_analyst": "gpt-4o-mini", ...},
  "transcript": [
    {"role": "technical_analyst", "ts": "...", "output": [...], "usage": {...}},
    {"role": "news_sentiment_analyst", ...},
    ...
    {"role": "portfolio_manager", ..., "raw_text": "{...}", "parse_ok": true}
  ]
}
```

`results/multi_agent/decisions.jsonl` (one line per decision):
```json
{"date": "2025-05-05", "duration_s": 18.4, "debate_rounds": 2, "node_errors_count": 0, "timed_out": false, "parse_ok": true, "action_sum": 0.91, "cost_delta_usd": 0.31}
```

`cost_delta_usd` = `metrics.get_snapshot().estimated_cost_usd` before/after diff.

### D8. Analysts pre-fetch data via `LookaheadSafeTools` in Python

```python
def technical_analyst(state):
    tools = state["tools"]
    rows = []
    for ticker in state["universe"]:
        ind = tools.get_indicators(ticker)
        hist = tools.get_price_history(ticker, days=30)
        rows.append({"ticker": ticker, "ind": ind, "hist_summary": _summarize(hist)})
    user_text = _format_technical_brief(rows)
    # ... LLM call with [system_prompt, user_text]
```

Why NOT LLM tool_calls (like PKG-7):
- Per-decision token cost predictable (no iteration explosion)
- 6 sequential roles × tool loops would multiply latency 5-10×
- Determinism (no LLM-chosen tool order)
- Simpler audit — Python call is the audit point

We give up some LLM creativity in data gathering; we keep cost + latency
bounded for the demo. CHECKPOINT 24/05 cut-path keeps the same
architecture (just drops debate + risk manager), so this choice is
forward-compatible.

### D9. Portfolio Manager is the SOLE producer of JSON weights

Every other role outputs PROSE (markdown analysis, debate text,
proposal, risk review). Only `portfolio_manager` is prompted for
strict JSON, parsed via `parse_weights_json` exactly like PKG-6/7.
This:
- Reuses PKG-5 parser unchanged
- Localizes the "JSON output" responsibility to one prompt to engineer
- Lets analysts write rich prose for the transcript (better UX in PKG-15)

### D10. Node failure → graph degrades gracefully

```python
def technical_analyst(state):
    try:
        # ... LLM calls ...
        return {"technical_reports": rows, "transcript": [...]}
    except Exception as e:
        log.warning("technical_analyst failed: %s", e)
        return {
            "technical_reports": [{"ticker": t, "report": "FAILURE"} for t in state["universe"]],
            "node_errors": [{"role": "technical_analyst", "error": str(e), "ts": _now()}],
            "transcript": [{"role": "technical_analyst", "ts": _now(), "error": str(e)}],
        }
```

Downstream nodes (debate, trader, risk, portfolio) see "FAILURE" in
their inputs and prompt knows to handle ("if any analyst report says
FAILURE, weight it as missing signal, don't fabricate"). Portfolio
manager's prompt explicitly says "if multiple roles failed, output
near-equal-weight JSON" — the parser then converts that to a clean action.

If portfolio manager itself fails: parser falls back to hold-shares.

---

## CUT-PATH (only if CHECKPOINT 24/05 fires)

If PKG-8 not merged by EOD 24/05, write decision to
`.agent/plans/checkpoint-24-05.md` and ship the cut-path:

**3-Agent Custom (≤ 1 day):**
- Keep: `technical_analyst`, `fundamental_analyst`, `trader`
- Drop: news_sentiment_analyst, both researchers, risk_manager
- `trader` now does final JSON output (replaces portfolio_manager)
- Graph: `START → technical → fundamental → trader → END` (linear)
- Models: all gpt-4o-mini (~$0.05/decision, $2.50/backtest)
- Transcript still saved (3 entries instead of 6+)
- `MultiAgentTrader` class signature unchanged — internal graph swap only
- Trade-off documented in report §"Limitations": no debate, no risk
  manager, simpler synthesis

Cut-path is NOT part of this PR. This PR ships the full 6-role stack.
Cut-path is only written if the gate fires.

---

## IMPLEMENTATION PLAN

### Phase 1: Spikes + state + transcript foundation

**Goal:** Lock LangGraph mechanics. Define data contracts. No LLM yet.

- Run Spike A (debate loop), Spike B (streaming), Spike C (timeout) —
  paste outputs into PR description as evidence
- Write `src/llm/multi_agent/state.py` with `MultiAgentState` + helpers
- Write `src/llm/multi_agent/transcript.py` with `write_transcript` +
  `append_decision_log` + `now_iso`
- Write `tests/test_multi_agent_state.py` (~4 tests) + `test_multi_agent_transcript.py` (~5 tests)

### Phase 2: 8 prompts + 6 nodes

**Goal:** Each role has a prompt + a node function. No graph yet — nodes
testable individually with `_FakeClient`.

- Write 8 prompt files (~1500 tokens each, Vietnamese, mirror
  single_agentic.md structure)
- Write `nodes/analysts.py` (3 functions)
- Write `nodes/researchers.py` (2 functions + `_should_continue_debate`)
- Write `nodes/trader.py`, `nodes/risk_manager.py`, `nodes/portfolio_manager.py`
- Each node has a unit test (~8-12 tests in `test_multi_agent_graph.py`
  under a `class TestNodes`)

### Phase 3: Graph wiring + MultiAgentTrader class

**Goal:** Compile the graph; wrap in Agent Protocol class.

- Write `graph.py` — `build_graph(client, models, debate_rounds)` returns
  uncompiled `StateGraph`; `build_app(...)` returns compiled `app`
- Write `agent.py` — `MultiAgentTrader` class
- Write graph-level tests (`test_multi_agent_graph.py`): full traversal
  with mocked client, debate-cap-fires, node-failure-graceful, timeout

### Phase 4: CLI + smoke

**Goal:** End-to-end run on a real session.

- Write `scripts/run_multi_agent.py` (mirror `run_single_agentic.py`)
- Real-call smoke `--n-sessions 2` (= 1 decision = 1 transcript)
- Verify cost, latency, transcript shape, decisions.jsonl

---

## STEP-BY-STEP TASKS

### 1. RUN Spikes A, B, C

- **IMPLEMENT:** Run each spike from "Pre-implementation spikes" section
- **VALIDATE:** All three print `OK ...`; save outputs into PR description draft

### 2. CREATE `src/llm/multi_agent/__init__.py`

- **IMPLEMENT:**
  ```python
  """Multi-agent LangGraph trader (PKG-8).

  Six LLM roles in a state machine: 3 Analysts → Bull/Bear debate (≤2 rounds)
  → Trader → Risk Manager → Portfolio Manager. Per-portfolio weekly decision.
  See .agent/plans/pkg-8-multi-agent-langgraph.md.
  """
  from src.llm.multi_agent.agent import MultiAgentTrader
  from src.llm.multi_agent.graph import build_app, build_graph
  from src.llm.multi_agent.state import MultiAgentState

  __all__ = ["MultiAgentTrader", "MultiAgentState", "build_app", "build_graph"]
  ```
- **VALIDATE:** `.venv/bin/python -c "from src.llm.multi_agent import MultiAgentTrader; print(MultiAgentTrader.name)"`

### 3. CREATE `src/llm/multi_agent/state.py`

- **IMPLEMENT:** Full `MultiAgentState` TypedDict per D1 spec above, plus
  `make_initial_state(market_data, news_data, info, client, models, tools,
  debate_rounds_max)` factory function.
- **GOTCHA #1:** `Annotated[list, add]` requires `from operator import add`
  and `from typing_extensions import Annotated` (NOT `typing.Annotated` on
  Python 3.11 — both work on 3.12 but typing_extensions is the safer bet
  across versions).
- **GOTCHA #2:** Don't put non-serializable objects (`MarketData`,
  `OpenAIClient`, `LookaheadSafeTools`) into the transcript field — only
  into the dedicated input fields. Transcript MUST stay JSON-serializable.
- **VALIDATE:** `.venv/bin/python -c "from src.llm.multi_agent.state import MultiAgentState, make_initial_state; print('ok')"`

### 4. CREATE `src/llm/multi_agent/transcript.py`

- **IMPLEMENT:**
  ```python
  """Persist multi-agent transcripts + per-decision summaries.

  Two outputs:
  - results/multi_agent/transcripts/<YYYY-MM-DD>.json — full per-decision detail
  - results/multi_agent/decisions.jsonl — append-only one-line summary per decision

  Both are best-effort: failures are logged warnings, never raised, so a
  filesystem hiccup never crashes a backtest. PKG-15 (debate replay UI)
  consumes the JSON files; PKG-10 (metrics) consumes the JSONL.
  """
  from __future__ import annotations

  import json
  import logging
  from datetime import UTC, datetime
  from pathlib import Path

  log = logging.getLogger(__name__)


  def now_iso() -> str:
      return datetime.now(UTC).isoformat()


  def write_transcript(transcript_dir: Path, date_str: str, payload: dict) -> None:
      try:
          transcript_dir.mkdir(parents=True, exist_ok=True)
          p = transcript_dir / f"{date_str}.json"
          p.write_text(
              json.dumps(payload, ensure_ascii=False, indent=2, default=str),
              encoding="utf-8",
          )
      except OSError as e:
          log.warning("transcript write failed for %s: %s", date_str, e)


  def append_decision_log(decisions_log_path: Path, record: dict) -> None:
      try:
          decisions_log_path.parent.mkdir(parents=True, exist_ok=True)
          with decisions_log_path.open("a", encoding="utf-8") as f:
              f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
      except OSError as e:
          log.warning("decisions log append failed: %s", e)
  ```
- **VALIDATE:** `.venv/bin/python -c "from src.llm.multi_agent.transcript import now_iso, write_transcript, append_decision_log; print('ok')"`

### 5. CREATE `tests/test_multi_agent_state.py` (~4 tests)

- **IMPLEMENT:** Tests for:
  1. `test_initial_state_has_required_inputs` — `make_initial_state` returns
     all required keys
  2. `test_transcript_reducer_appends` — manually building two patches and
     verifying `Annotated[list, add]` concatenates
  3. `test_debate_exchanges_reducer_appends` — same for `debate_exchanges`
  4. `test_state_serializable_after_strip_inputs` — transcript stripped of
     `market_data`/`client` is JSON-serializable
- **PATTERN:** No fixtures beyond what's in `conftest.py`.
- **VALIDATE:** `.venv/bin/pytest tests/test_multi_agent_state.py -v`

### 6. CREATE `tests/test_multi_agent_transcript.py` (~5 tests)

- **IMPLEMENT:** Tests for:
  1. `test_write_transcript_creates_json_file` — writes valid JSON to
     `tmp_path / "<date>.json"`
  2. `test_write_transcript_overwrites_existing` — same date, new payload
  3. `test_append_decision_log_creates_jsonl` — first append creates file
  4. `test_append_decision_log_appends_not_overwrites` — second call adds line
  5. `test_write_transcript_swallows_filesystem_error` — write to read-only
     path → logged, no raise
- **VALIDATE:** `.venv/bin/pytest tests/test_multi_agent_transcript.py -v`

### 7. CREATE 8 prompt files in `src/llm/prompts/multi_agent/`

Each file ≥ 4000 chars (auto-cache trigger). Shared preamble (~2000 chars
across all 8) covers: role (quant trader, VN HOSE, academic backtest),
universe (5 tickers + lock), market rules (±7%, lot-100, fees, long-only),
lookahead rule (D+2 news), output format reminder. Role-specific section
(~2000 chars) covers role's task.

#### 7.1 `technical_analyst.md`
- Role: Read indicators (RSI/MACD/SMA/Bollinger/ATR) + recent OHLC for 5
  tickers; write a brief markdown report per ticker
- Output: Markdown bullets, NO JSON

#### 7.2 `news_sentiment_analyst.md`
- Role: Read recent news (visible at asof) + summarize sentiment per ticker
- Output: Markdown bullets per ticker (positive/neutral/negative + 1-line reason)

#### 7.3 `fundamental_analyst.md`
- Role: Read 4-quarter fundamentals + flag ticker as improving/stable/declining
- Output: Markdown bullets per ticker

#### 7.4 `bullish_researcher.md`
- Role: Argue FOR increasing allocations to whichever tickers look strongest
  across the 3 analyst reports + prior debate exchanges
- Output: Markdown argument (no JSON)

#### 7.5 `bearish_researcher.md`
- Role: Argue FOR caution / reducing exposure / preferring defensive names
- Output: Markdown argument
- NOTE: bearish_researcher increments debate counter (D4); prompt doesn't
  need to know — wiring handles it

#### 7.6 `trader.md`
- Role: Synthesize analysts + debate into a CONCRETE proposal (e.g.,
  "overweight VCB + FPT, equal-weight HPG, underweight VIC due to debate
  consensus, hold VNM as defensive")
- Output: Markdown proposal (no JSON)

#### 7.7 `risk_manager.md`
- Role: Critique the trader proposal from 3 angles (concentration risk,
  drawdown risk, regime risk); suggest adjustments
- Output: Markdown review

#### 7.8 `portfolio_manager.md`
- Role: Final arbiter; reads trader proposal + risk review; outputs
  STRICT JSON weights (mirror zero_shot/single_agentic format exactly)
- Output: `{"VCB": 0.x, "FPT": 0.x, ...}` — parsed by `parse_weights_json`
- This is the ONLY prompt with JSON output requirement; reuse PKG-6
  output schema section verbatim

**GOTCHA:** Don't paste from formatted doc apps (curly quotes break JSON
example blocks). UTF-8 encoding. Test for each: `wc -c <file>` ≥ 4000.

- **VALIDATE:**
  ```bash
  for f in src/llm/prompts/multi_agent/*.md; do
    size=$(wc -c < "$f")
    echo "$f: $size bytes"
    test "$size" -ge 4000 || echo "  TOO SMALL"
  done
  ```

### 8. CREATE `src/llm/multi_agent/nodes/__init__.py` (empty)

### 9. CREATE `src/llm/multi_agent/nodes/analysts.py`

- **IMPLEMENT:** 3 node functions following pattern in D8. Each:
  1. Loops 5 tickers, calls relevant `LookaheadSafeTools` method(s)
  2. Builds a single user message summarizing all 5 tickers' data
     (one LLM call per analyst, not per ticker — keeps cost down)
  3. Calls `state["client"].chat(model=state["models"][role_name], ...)`
  4. Parses LLM markdown output → list of per-ticker reports (split
     on `## <ticker>` headings, lenient fallback)
  5. Returns dict patch with `{role}_reports` + `transcript` entry
  6. Wraps in try/except → records `node_errors` + returns FAILURE entries
- **GOTCHA #1:** ONE LLM call per analyst (not 5). 3 analysts × 1 call =
  3 calls for the analyst phase (not 15). Cost stays bounded.
- **GOTCHA #2:** `state["models"]` lookup uses bare role name (e.g.,
  `"technical_analyst"`), NOT prefixed. Keep keys consistent with prompts.
- **VALIDATE:** Import + smoke (`from src.llm.multi_agent.nodes.analysts import technical_analyst, news_sentiment_analyst, fundamental_analyst`)

### 10. CREATE `src/llm/multi_agent/nodes/researchers.py`

- **IMPLEMENT:** `bullish_researcher`, `bearish_researcher`, and the
  `_should_continue_debate` router function.
  - Researchers read `technical_reports + news_sentiment_reports +
    fundamental_reports + debate_exchanges` (full history)
  - LLM call → output appended to `debate_exchanges`
  - `bearish_researcher` ALSO returns `{"debate_round": state["debate_round"] + 1}`
  - `_should_continue_debate(state) -> str` returns `"loop"` or `"exit"`
- **GOTCHA:** Pass `debate_rounds_max` through state (set in
  `make_initial_state`); router compares against it, not a module constant.
- **VALIDATE:** Import + ensure functions take/return correct shapes.

### 11. CREATE `src/llm/multi_agent/nodes/trader.py`

- **IMPLEMENT:** Single function `trader(state)`. Reads all analyst reports
  + debate exchanges. LLM call → markdown proposal. Returns
  `{"trader_proposal": text, "transcript": [...]}`.

### 12. CREATE `src/llm/multi_agent/nodes/risk_manager.py`

- **IMPLEMENT:** Reads `trader_proposal` + analyst reports. LLM call →
  markdown review. Returns `{"risk_review": text, "transcript": [...]}`.

### 13. CREATE `src/llm/multi_agent/nodes/portfolio_manager.py`

- **IMPLEMENT:**
  ```python
  def portfolio_manager(state: MultiAgentState) -> dict:
      """Final node. Output raw text → parsed by MultiAgentTrader.

      We do NOT call parse_weights_json here. The portfolio_manager_output
      field carries raw LLM text; MultiAgentTrader.decide() parses it. This
      separation keeps the graph state JSON-serializable (np.ndarray would
      break transcript serialization) and localizes parser metric recording
      to one place.
      """
      try:
          ... LLM call with [trader_proposal, risk_review, all analyst reports] ...
          return {
              "portfolio_manager_output": result.text or "",
              "transcript": [{"role": "portfolio_manager", "ts": now_iso(),
                              "raw_text": result.text, "usage": result.usage}],
          }
      except Exception as e:
          return {
              "portfolio_manager_output": "",  # → parser will hold-shares
              "node_errors": [{"role": "portfolio_manager", "error": str(e), "ts": now_iso()}],
              "transcript": [{"role": "portfolio_manager", "ts": now_iso(), "error": str(e)}],
          }
  ```
- **GOTCHA:** Don't import `parse_weights_json` here. Parsing happens in
  `MultiAgentTrader.decide` after graph returns (D9).

### 14. CREATE `src/llm/multi_agent/graph.py`

- **IMPLEMENT:**
  ```python
  """LangGraph wiring: build_graph(...) and build_app(...).

  Separation: build_graph returns uncompiled StateGraph (tests can inspect
  edges); build_app compiles and returns the invocable app.
  """
  from __future__ import annotations

  from langgraph.graph import END, START, StateGraph

  from src.llm.multi_agent.nodes.analysts import (
      fundamental_analyst,
      news_sentiment_analyst,
      technical_analyst,
  )
  from src.llm.multi_agent.nodes.portfolio_manager import portfolio_manager
  from src.llm.multi_agent.nodes.researchers import (
      _should_continue_debate,
      bearish_researcher,
      bullish_researcher,
  )
  from src.llm.multi_agent.nodes.risk_manager import risk_manager
  from src.llm.multi_agent.nodes.trader import trader
  from src.llm.multi_agent.state import MultiAgentState


  def build_graph() -> StateGraph:
      g = StateGraph(MultiAgentState)
      g.add_node("technical_analyst", technical_analyst)
      g.add_node("news_sentiment_analyst", news_sentiment_analyst)
      g.add_node("fundamental_analyst", fundamental_analyst)
      g.add_node("bullish_researcher", bullish_researcher)
      g.add_node("bearish_researcher", bearish_researcher)
      g.add_node("trader", trader)
      g.add_node("risk_manager", risk_manager)
      g.add_node("portfolio_manager", portfolio_manager)

      # Sequential analyst phase (simpler than parallel; deterministic
      # transcript ordering; cost identical)
      g.add_edge(START, "technical_analyst")
      g.add_edge("technical_analyst", "news_sentiment_analyst")
      g.add_edge("news_sentiment_analyst", "fundamental_analyst")
      g.add_edge("fundamental_analyst", "bullish_researcher")

      # Debate loop (D4)
      g.add_edge("bullish_researcher", "bearish_researcher")
      g.add_conditional_edges(
          "bearish_researcher",
          _should_continue_debate,
          {"loop": "bullish_researcher", "exit": "trader"},
      )

      # Synthesis chain
      g.add_edge("trader", "risk_manager")
      g.add_edge("risk_manager", "portfolio_manager")
      g.add_edge("portfolio_manager", END)
      return g


  def build_app():
      return build_graph().compile()
  ```
- **GOTCHA:** `build_graph()` takes NO args — client/models/etc. flow
  through state, not closure. This keeps the graph reusable across decisions
  with different inputs.
- **VALIDATE:** `.venv/bin/python -c "from src.llm.multi_agent.graph import build_app; app = build_app(); print(app)"`

### 15. CREATE `src/llm/multi_agent/agent.py`

- **IMPLEMENT:**
  ```python
  """MultiAgentTrader — Agent Protocol wrapper around the LangGraph app.

  Weekly cadence + timeout + transcript writes + parser. The graph itself
  is stateless across decisions; this class owns the per-decision lifecycle.
  """
  from __future__ import annotations

  import concurrent.futures
  import logging
  import time
  from pathlib import Path

  import numpy as np
  import pandas as pd

  from src import config
  from src.env_data_loader import MarketData
  from src.llm import metrics
  from src.llm.client import OpenAIClient
  from src.llm.multi_agent.graph import build_app
  from src.llm.multi_agent.state import make_initial_state
  from src.llm.multi_agent.transcript import (
      append_decision_log,
      now_iso,
      write_transcript,
  )
  from src.llm.parser import _hold_shares_action, parse_weights_json
  from src.llm.tools import LookaheadSafeTools

  log = logging.getLogger(__name__)

  _DEFAULT_TRANSCRIPT_DIR = (
      config.PROJECT_ROOT / "results" / "multi_agent" / "transcripts"
  )
  _DEFAULT_DECISIONS_PATH = (
      config.PROJECT_ROOT / "results" / "multi_agent" / "decisions.jsonl"
  )
  _DEFAULT_MODELS: dict[str, str] = {
      "technical_analyst":      "gpt-4o-mini",
      "news_sentiment_analyst": "gpt-4o-mini",
      "fundamental_analyst":    "gpt-4o-mini",
      "bullish_researcher":     "gpt-4o",
      "bearish_researcher":     "gpt-4o",
      "trader":                 "gpt-4o",
      "risk_manager":           "gpt-4o",
      "portfolio_manager":      "gpt-4o",
  }
  _DEFAULT_DEBATE_ROUNDS: int = 2
  _DEFAULT_TIMEOUT_S: float = 30.0


  class MultiAgentTrader:
      name: str = "multi_agent"

      def __init__(
          self,
          market_data: MarketData,
          news_data: pd.DataFrame,
          models: dict[str, str] | None = None,
          client: OpenAIClient | None = None,
          weekly_rebalance: bool = True,
          debate_rounds: int = _DEFAULT_DEBATE_ROUNDS,
          decision_timeout_s: float = _DEFAULT_TIMEOUT_S,
          transcript_dir: Path | None = _DEFAULT_TRANSCRIPT_DIR,
          decisions_log_path: Path | None = _DEFAULT_DECISIONS_PATH,
      ) -> None:
          self.market_data = market_data
          self.news_data = news_data
          self.models = {**_DEFAULT_MODELS, **(models or {})}
          self._validate_models()
          self._client = client or OpenAIClient()
          self.weekly_rebalance = weekly_rebalance
          self.debate_rounds = int(debate_rounds)
          self.decision_timeout_s = float(decision_timeout_s)
          self.transcript_dir = (
              Path(transcript_dir) if transcript_dir is not None else None
          )
          self.decisions_log_path = (
              Path(decisions_log_path) if decisions_log_path is not None else None
          )
          self._last_week: tuple[int, int] | None = None
          self._cached: np.ndarray | None = None
          self._app = build_app()

      def decide(self, obs: np.ndarray, info: dict) -> np.ndarray:
          is_rebal = self._is_rebalance_day(info)
          if (
              self.weekly_rebalance
              and self._cached is not None
              and not is_rebal
          ):
              return self._cached.copy()

          date_str = pd.Timestamp(info["date"]).strftime("%Y-%m-%d")
          asof = pd.Timestamp(info["date"]).normalize()
          tools = LookaheadSafeTools(self.market_data, self.news_data, asof)

          initial = make_initial_state(
              market_data=self.market_data,
              news_data=self.news_data,
              info=info,
              client=self._client,
              models=self.models,
              tools=tools,
              debate_rounds_max=self.debate_rounds,
          )

          cost_before = metrics.get_snapshot().get("estimated_cost_usd", 0.0)
          t0 = time.monotonic()
          timed_out = False
          final_state = None
          try:
              with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                  fut = ex.submit(self._app.invoke, initial)
                  final_state = fut.result(timeout=self.decision_timeout_s)
          except concurrent.futures.TimeoutError:
              timed_out = True
              log.warning(
                  "multi_agent timeout %.1fs at %s",
                  self.decision_timeout_s,
                  date_str,
              )
              metrics.record_parse_failure(reason="multi_agent_timeout")

          duration_s = time.monotonic() - t0

          if timed_out or final_state is None:
              action = _hold_shares_action(
                  info, list(self.market_data.tickers)
              )
              parse_ok = False
              self._write_outputs(
                  info, final_state, duration_s, timed_out=True,
                  action=action, parse_ok=False,
                  cost_delta=metrics.get_snapshot().get("estimated_cost_usd", 0.0) - cost_before,
              )
              self._cached = action
              return action.copy()

          raw_text = final_state.get("portfolio_manager_output", "")
          action, parse_ok = parse_weights_json(
              raw_text, info, ticker_order=list(self.market_data.tickers)
          )
          cost_delta = metrics.get_snapshot().get("estimated_cost_usd", 0.0) - cost_before
          self._write_outputs(
              info, final_state, duration_s, timed_out=False,
              action=action, parse_ok=parse_ok, cost_delta=cost_delta,
          )
          self._cached = action
          return action.copy()

      def _is_rebalance_day(self, info: dict) -> bool:
          ts = pd.Timestamp(info["date"])
          iso = ts.isocalendar()
          key = (int(iso.year), int(iso.week))
          if key != self._last_week:
              self._last_week = key
              return True
          return False

      def _validate_models(self) -> None:
          for role, model in self.models.items():
              if model not in config.LLM_ALLOWED_MODELS:
                  raise ValueError(
                      f"model {model!r} for role {role!r} not in whitelist "
                      f"{sorted(config.LLM_ALLOWED_MODELS)}"
                  )

      def _write_outputs(
          self,
          info: dict,
          final_state: dict | None,
          duration_s: float,
          timed_out: bool,
          action: np.ndarray,
          parse_ok: bool,
          cost_delta: float,
      ) -> None:
          date_str = pd.Timestamp(info["date"]).strftime("%Y-%m-%d")
          transcript = (final_state or {}).get("transcript", [])
          node_errors = (final_state or {}).get("node_errors", [])
          debate_rounds_used = (final_state or {}).get("debate_round", 0)

          if self.transcript_dir is not None:
              payload = {
                  "date": date_str,
                  "agent": self.name,
                  "duration_s": duration_s,
                  "debate_rounds": debate_rounds_used,
                  "timed_out": timed_out,
                  "node_errors": node_errors,
                  "models_used": self.models,
                  "transcript": transcript,
              }
              write_transcript(self.transcript_dir, date_str, payload)

          if self.decisions_log_path is not None:
              record = {
                  "ts": now_iso(),
                  "date": date_str,
                  "agent": self.name,
                  "duration_s": duration_s,
                  "debate_rounds": debate_rounds_used,
                  "node_errors_count": len(node_errors),
                  "timed_out": timed_out,
                  "parse_ok": parse_ok,
                  "action_sum": float(action.sum()) if action is not None else None,
                  "cost_delta_usd": cost_delta,
              }
              append_decision_log(self.decisions_log_path, record)
  ```
- **GOTCHA #1:** `metrics.get_snapshot()['estimated_cost_usd']` is a
  running total; `cost_delta` = after − before captures THIS decision's cost.
- **GOTCHA #2:** `_validate_models` runs in `__init__` so a typo'd model
  fails LOUD before any backtest steps (PRD §14 Risk #3).
- **GOTCHA #3:** Don't strip `transcript` of `usage` dicts — PKG-10 reads
  them for per-role token accounting.
- **VALIDATE:** `.venv/bin/python -c "from src.llm.multi_agent.agent import MultiAgentTrader; print(MultiAgentTrader.name)"`

### 16. CREATE `tests/test_multi_agent_graph.py` (~10 tests)

- **IMPLEMENT:** All tests use `_FakeClient` (mirror PKG-7). Queue
  responses in expected node-visit order: technical → news_sentiment →
  fundamental → bullish r1 → bearish r1 → bullish r2 → bearish r2 →
  trader → risk → portfolio_manager (10 calls for full happy path).
  - `test_graph_compiles` — `build_app()` succeeds
  - `test_full_traversal_happy_path` — mock 10 text responses; verify
    portfolio_manager output reaches state; verify transcript has 10 entries
  - `test_debate_cap_2_rounds` — even if fake returns more debate content,
    `debate_round` ends at exactly 2 (bullish ran 2x, bearish ran 2x)
  - `test_debate_cap_1_round_when_configured` — pass `debate_rounds_max=1`
    via initial state; verify only 1 round (2 LLM calls in debate phase)
  - `test_node_failure_records_error_and_continues` — `_FakeClient.raise_at=3`
    (fail bullish r1); verify `node_errors` has entry + downstream nodes
    still run + final state has portfolio_manager_output
  - `test_streaming_yields_updates_per_node` — `app.stream(initial,
    stream_mode='updates')`; verify ≥ 9 events (8 nodes + extra for debate
    loops)
  - `test_analyst_called_with_correct_model` — verify each analyst's
    `client.chat(model=...)` was `gpt-4o-mini`
  - `test_researcher_called_with_gpt_4o` — verify debate calls use `gpt-4o`
  - `test_portfolio_manager_output_is_raw_text` — final state's
    `portfolio_manager_output` is a string, not a parsed dict
  - `test_tools_pre_fetched_python_side` — fake tools instance recorded
    its method calls; verify e.g. `get_indicators` called 5x by technical_analyst
- **PATTERN:** `_FakeClient` from `test_single_agentic.py` (copy locally,
  don't import — tests own their fakes).
- **GOTCHA #1:** With 2 debate rounds, the queue needs 10 responses
  (3 analysts + 4 debate + 1 trader + 1 risk + 1 portfolio). Test
  `test_debate_cap_2_rounds` queues 12 (over-supply) to verify cap fires
  structurally (only 10 consumed).
- **GOTCHA #2:** Don't test for byte-exact transcript content (LLM mock
  outputs are placeholders). Test for STRUCTURAL invariants: count of
  entries by role, presence of `node_errors`, `debate_round` value.
- **VALIDATE:** `.venv/bin/pytest tests/test_multi_agent_graph.py -v`

### 17. CREATE `tests/test_multi_agent_agent.py` (~8 tests)

- **IMPLEMENT:**
  1. `test_protocol_runtime_check` — `isinstance(.., Agent)` + name
  2. `test_weekly_cache_skips_graph_within_same_week` — first decide()
     runs graph; second decide() same week returns cached (verify `fake.calls`
     count doesn't grow)
  3. `test_iso_week_change_triggers_new_decision`
  4. `test_invalid_model_in_constructor_raises_loud` — `models={"trader": "gpt-3.5-turbo"}` → ValueError
  5. `test_timeout_falls_back_to_hold_shares` — patch `_app.invoke` with
     `time.sleep(2)` + `decision_timeout_s=0.1` → verify hold-shares
     + `metrics.record_parse_failure(reason="multi_agent_timeout")`
  6. `test_transcript_dir_none_disables_writes` — no JSON files appear
  7. `test_decisions_log_appends_per_decision` — 2 decisions across 2 weeks
     → JSONL has 2 lines
  8. `test_portfolio_manager_parse_failure_falls_back_to_hold_shares` —
     portfolio_manager returns garbage; verify hold-shares + parser metric
- **GOTCHA:** Use `monkeypatch.setattr(agent, '_app', FakeApp())` for the
  timeout test (FakeApp.invoke sleeps); avoids needing a real graph.
- **VALIDATE:** `.venv/bin/pytest tests/test_multi_agent_agent.py -v`

### 18. CREATE `scripts/run_multi_agent.py`

- **IMPLEMENT:** Mirror `scripts/run_single_agentic.py`:
  - `--split / --seed / --n-sessions` (same flags)
  - `--debate-rounds` (default 2)
  - `--timeout-s` (default 30)
  - `--reset-transcripts` (delete `results/multi_agent/transcripts/` + `decisions.jsonl`)
  - End-of-run summary: cost, parse rates, AND audit summary
    (avg duration, debate rounds histogram, timeouts count, node_errors total)
- **PATTERN:** `_run_full` and `_run_n` exact mirror of single_agentic CLI
  (just substitute `MultiAgentTrader`).
- **VALIDATE:** `unset OPENAI_API_KEY && .venv/bin/python scripts/run_multi_agent.py --split test --n-sessions 1 2>&1 | head -5`
  Expected: `RuntimeError: OPENAI_API_KEY not set`

### 19. REAL-CALL SMOKE (gated, ~$0.30-0.60)

- **IMPLEMENT:**
  ```bash
  .venv/bin/python scripts/run_multi_agent.py --split test --n-sessions 2 --reset-transcripts
  ```
- **EXPECTED:** Completes < 60s wallclock (1 decision × ~30s + 1 cached
  step); 1 transcript file created at `results/multi_agent/transcripts/<date>.json`;
  1 line in `decisions.jsonl`; cost < $0.50; parse_ok=true.
- **CHECK:** Open the transcript JSON — verify 9-10 entries with roles
  in order: technical_analyst, news_sentiment_analyst, fundamental_analyst,
  bullish_researcher (×2), bearish_researcher (×2), trader, risk_manager,
  portfolio_manager.
- **PASTE OUTPUT** into PR description as evidence.

### 20. ruff + full pytest

- **IMPLEMENT:**
  ```bash
  .venv/bin/ruff check src/ tests/ scripts/
  .venv/bin/pytest tests/ -v 2>&1 | tail -10
  ```
- **EXPECTED:** ruff clean; 141 prior + ~27 new ≈ **168 tests pass**.

---

## TESTING STRATEGY

### Unit Tests (~27 new across 4 files)

| File | Count | Focus |
|------|------:|-------|
| `test_multi_agent_state.py` | 4 | TypedDict shape, reducers, serializability |
| `test_multi_agent_transcript.py` | 5 | JSON write, JSONL append, error-swallow |
| `test_multi_agent_graph.py` | 10 | wiring, debate cap, node failure, streaming |
| `test_multi_agent_agent.py` | 8 | Protocol, weekly, timeout, model validation, fallbacks, logs |

Total: ~27 new; running total after PKG-8 ≈ **168 tests**.

### Integration smoke (manual, in PR description)

`run_multi_agent.py --split test --n-sessions 2 --reset-transcripts` with
real `OPENAI_API_KEY`. Capture:
- Wall duration (~20-40s for 1 real decision)
- Cost USD (< $0.50 for 1 decision)
- Transcript role count (= 8 unique roles, 9-10 entries with debate)
- Decisions JSONL row contents (parse_ok, debate_rounds, node_errors_count=0)

### Edge Cases Explicitly Covered

| # | Edge case | Test |
|---|-----------|------|
| 1 | Debate counter capped at 2 even if LLM keeps "responding" | graph #3 |
| 2 | Configurable cap = 1 round | graph #4 |
| 3 | One analyst fails mid-graph | graph #5 |
| 4 | Portfolio manager returns malformed JSON | agent #8 |
| 5 | Graph exceeds 30s wallclock | agent #5 |
| 6 | Weekly cadence (mirror PKG-7) | agent #2, #3 |
| 7 | Invalid model name in config | agent #4 |
| 8 | Transcript dir disabled | agent #6 |
| 9 | JSON serializability after stripping non-serializable inputs | state #4 |
| 10 | Filesystem error during transcript write | transcript #5 |

### Edge Cases NOT Covered (deferred)

- **Real OpenAI streaming** — PKG-12 SSE route will integrate;
  `test_streaming_yields_updates_per_node` covers structural shape but
  not network reality
- **Concurrent backtests** — `metrics` is a module singleton; running
  PKG-8 in parallel with PKG-7 would interleave counters. PKG-10 will
  serialize backtest runs
- **Parallel analyst execution** — LangGraph supports it; we chose
  sequential for transcript ordering. Future PR could parallelize and
  cut analyst phase latency by ~3×

---

## VALIDATION COMMANDS

### Level 1: Syntax & Style

```bash
.venv/bin/ruff check src/ tests/ scripts/
.venv/bin/ruff format --check src/llm/multi_agent/ tests/test_multi_agent_*.py scripts/run_multi_agent.py
```

### Level 2: Unit Tests (multi_agent only)

```bash
.venv/bin/pytest tests/test_multi_agent_*.py -v
# Expected: ~27 tests pass
```

### Level 3: Full Regression

```bash
.venv/bin/pytest tests/ -v 2>&1 | tail -5
# Expected: 168 passed
```

### Level 4: CLI mocked smoke

```bash
unset OPENAI_API_KEY
.venv/bin/python scripts/run_multi_agent.py --split test --n-sessions 1 2>&1 | head -5
# Expected: RuntimeError "OPENAI_API_KEY not set"
```

### Level 5: Real-call smoke (gated, ~$0.30-0.50)

```bash
.venv/bin/python scripts/run_multi_agent.py --split test --n-sessions 2 --reset-transcripts
# Expected: 1 decision completed, transcript written, parse_ok=true
ls results/multi_agent/transcripts/ | wc -l
# Expected: 1
python -c "import json; print(json.load(open('results/multi_agent/transcripts/' + __import__('os').listdir('results/multi_agent/transcripts')[0]))['debate_rounds'])"
# Expected: 2
```

### Level 6: Acceptance invariant check

```bash
.venv/bin/python <<'PY'
import json, pathlib
log = pathlib.Path("results/multi_agent/decisions.jsonl")
if not log.exists():
    print("SKIP — run smoke first")
else:
    recs = [json.loads(l) for l in log.read_text().splitlines()]
    assert all(r["debate_rounds"] <= 2 for r in recs), "cap violated"
    assert all(r["duration_s"] < 35 for r in recs), "wallclock breach"
    print(f"OK — {len(recs)} decisions, max debate_rounds={max((r['debate_rounds'] for r in recs), default=0)}, max duration={max((r['duration_s'] for r in recs), default=0):.1f}s")
PY
```

---

## ACCEPTANCE CRITERIA

Mirrors GitHub Issue #9:

- [ ] **1 decision end-to-end < 30s với real OpenAI call** — verified by
  agent #5 (mocked) + Level 5 real-call smoke + Level 6 invariant
- [ ] **Transcript có đúng 6 role + decision + thời điểm** — 8 unique
  roles (technical_analyst, news_sentiment_analyst, fundamental_analyst,
  bullish_researcher, bearish_researcher, trader, risk_manager,
  portfolio_manager); 9-10 transcript entries (debate roles appear 2×)
  + decision summary; verified by graph #2 + Level 5 inspection
- [ ] **Debate cap 2 round verified** — graph #3 + Level 6 assertion
- [ ] **Cost report sau 1 quarter test < $15 (sanity)** — design budget
  ~$15 (D3); enforced in CLI summary; full-quarter run is post-merge
  PKG-10 territory but the per-decision cost cap (D3 estimate $0.30)
  makes this provably true
- [ ] `MultiAgentTrader` implements `Agent` Protocol; works in `run_backtest`
- [ ] Weekly cadence preserved (agent #2, #3)
- [ ] Invalid model name fails LOUD in constructor (agent #4)
- [ ] Node failures don't crash backtest (graph #5)
- [ ] Timeout falls back to hold-shares (agent #5)
- [ ] ~27 new tests pass; 141 prior tests still pass; ruff clean
- [ ] PR includes real-call smoke output + 1 transcript JSON preview

---

## COMPLETION CHECKLIST

- [ ] Spike A/B/C run + outputs in PR description
- [ ] 8 prompt files written, each ≥ 4000 chars (UTF-8, Vietnamese)
- [ ] `src/llm/multi_agent/` module: 5 files (state, transcript, graph,
      agent, __init__) + 6-node submodule + nodes/__init__.py
- [ ] All 27+ new tests pass
- [ ] Real-call smoke captured in PR (if OPENAI_API_KEY set)
- [ ] PR open with title `PKG-8: Multi-Agent LangGraph (6 roles)`,
      body `Closes #9`
- [ ] CLAUDE.md commit attribution rules followed (no AI co-author)
- [ ] PKG-10 unblocked (multi_agent agent now constructible)
- [ ] PKG-12 (SSE route) preview: `app.stream(stream_mode='updates')`
      shape confirmed and noted in PR
- [ ] CHECKPOINT 24/05: status report appended to plan

---

## NOTES

### Design decisions worth flagging in PR

1. **State machine over framework magic** — plain Python node fns +
   `StateGraph` orchestration. No `ChatOpenAI`. PKG-5 `OpenAIClient` is the
   only LLM SDK touch-point in the entire project.
2. **Mixed model lineup** — analysts cheap, debate/synthesis premium.
   Cost budget meets PRD §14 Risk #5 ceiling with headroom.
3. **Debate cap = structural** (`while debate_round < N` via conditional
   edge) — never relies on LLM "deciding" to stop. Same philosophy as
   PKG-7's iteration cap.
4. **Pre-fetch via `LookaheadSafeTools` Python-side** — not LLM tool_calls.
   Determinism + cost control + simpler audit. Trade-off documented.
5. **Portfolio Manager owns JSON output** — every other role is prose.
   Reuses PKG-5 parser unchanged; localizes JSON-engineering effort.
6. **30s timeout via threadpool** — `OpenAIClient` is sync; threadpool
   is the right interop. Orphaned thread acceptable (completes in ~60s).
7. **Transcript JSON-per-date + decisions JSONL** — JSON for rich replay
   (PKG-15 UI); JSONL for log-style aggregation (PKG-10 metrics).
8. **No code shared between `multi_agent/` and `zero_shot.py`/`single_agentic.py`** —
   30-line overlap (`_is_rebalance_day`, hold-shares fallback) is
   intentional duplication; DRY would couple three modules through a shared
   util, blocking independent evolution. Matches PKG-6/PKG-7 stance.
9. **CHECKPOINT 24/05 cut-path documented but not implemented** — if
   gate fires, cut-path needs ~½ day. Plan keeps the cut-path
   forward-compatible (same `MultiAgentTrader` signature, internal graph
   swap only).

### Risks specific to PKG-8

| # | Risk | Mitigation |
|---|------|-----------|
| 1 | LangGraph 1.2 API drift from doc examples (some tutorials use 0.x APIs) | Spikes A/B verify against installed version; tests pin behaviour |
| 2 | Cost overrun (e.g., gpt-4o on all roles + uncapped debate) | Mixed model lineup (D3); structural cap (D4); per-decision cost reported in CLI |
| 3 | Real-call latency > 30s for one decision | Threadpool timeout (D5); hold-shares fallback; analysts parallel-execution can be added in follow-up |
| 4 | Transcripts grow to MBs and break SSE delivery | Truncate analyst report sizes in prompts (each ≤ ~300 words/ticker); PKG-15 paginates by role; not blocking for PKG-8 |
| 5 | Prompt engineering: portfolio_manager keeps emitting prose around JSON | Reuse zero_shot.md output schema verbatim (proven in PKG-6); parser handles prose-wrapped JSON via `_JSON_BLOCK_RE` |
| 6 | Debate degenerates into "I agree" loops with no real disagreement | Bull/Bear prompts explicitly require dissent + concrete numbers; if observed, PKG-8 follow-up could add "force-disagreement" check |
| 7 | One slow OpenAI region triggers 30s timeout repeatedly → all hold-shares | Acceptable for academic backtest; document `multi_agent_timeout` metric in report |
| 8 | LangGraph compile time on every `MultiAgentTrader.__init__` | Compile once per agent instance, not per decision (build_app is called in `__init__`); test verifies |

### Khi gặp blocker

- LangGraph compile error → check `build_graph()` for missing
  `add_node` or `add_edge` calls; conditional edges must point to nodes
  that ARE added
- Debate cap doesn't fire → confirm `bearish_researcher` INCREMENTS the
  counter (D4); easy to forget if you only assign in bullish
- Real call: portfolio_manager outputs prose instead of JSON →
  tighten its prompt's "Output format" section; reuse `_JSON_BLOCK_RE`
  in parser handles prose-wrapped fine
- Real call: one analyst takes 20s alone → it's calling LLM 5× (per
  ticker). Verify D8/GOTCHA #1: ONE call per analyst summarizing 5 tickers
- Real call: cost > $1 per decision → check debate cap fired (decisions.jsonl
  `debate_rounds` should == 2); check no unexpected gpt-4o calls in
  analyst phase
- Transcript not appearing → check `_DEFAULT_TRANSCRIPT_DIR` exists +
  writable; check tests passed `transcript_dir=tmp_path` (not None
  unless testing that path)
- `metrics.get_snapshot()` cost_delta is 0 → metrics not reset between
  decisions; CLI does `metrics.reset()` ONCE before backtest; cost_delta
  is per-decision, not per-backtest

### Phase 2 status after PKG-8

| PKG | Status |
|-----|--------|
| PKG-5 LLM core | ✅ merged |
| PKG-6 zero-shot | ✅ merged |
| PKG-7 single-agentic | ✅ merged |
| **PKG-8 multi-agent (this PR)** | 🟡 ready after impl |
| PKG-9 DDPG | unblocked, independent track |
| PKG-10 backtest engine | needs PKG-8 + PKG-9; PKG-8 unblock biggest |
| PKG-12 SSE route | uses `app.stream` exposed by `build_app()` |
| PKG-15 debate replay UI | reads `results/multi_agent/transcripts/*.json` |

---

## Confidence Score

**6.5/10** for one-pass implementation.

Subtract:
- −1.0 LangGraph state graph wiring is the biggest single piece of NEW
  framework code in the project. Spikes A/B mitigate but won't catch
  every API quirk
- −0.5 prompt engineering for 8 roles + debate flow is 1.5x the prompt
  work of PKG-6+PKG-7 combined
- −0.5 first real-call timing/cost might breach budgets, requiring
  prompt or cap adjustments
- −0.5 transcript schema may need iteration to fit PKG-15 UI needs
  (can't fully predict ahead of UI scaffolding)
- −0.5 timeout + threadpool interaction has subtle pitfalls (e.g.,
  daemon threads on Python shutdown); spike C covers the basic case

Add back:
- +0.5 PKG-5 LLM client + tools + parser + metrics are battle-tested
- +0.5 PKG-7 patterns transfer directly (weekly cadence, fallback,
  audit log, CLI shape)
- +0.5 design intentionally over-specified (10 D-decisions, 3 spikes,
  ~27 tests) to maximize first-pass success on the biggest package

PKG-8 is the only package where I'd recommend running the spikes BEFORE
committing to the file structure, and pausing for advisor() review of
the resulting state.py + graph.py before writing nodes. Everything else
should be straight-line from this plan.
