# Feature: PKG-7 — Single-LLM Agentic Trader (tool-using)

> 2nd LLM agent. Same weekly cadence as zero-shot, but the LLM may call any
> of the 4 `LookaheadSafeTools` (price/indicators/news/fundamentals) to
> discover data before emitting weights. Adds an audit log
> (`results/single_agentic/tool_calls.jsonl`) so PKG-10 can measure
> hallucination + tool-use patterns.
>
> Glue layer: PKG-5 client + tools + parser + metrics already exist; PKG-6
> proved the weekly-cadence/fallback patterns. PKG-7 is mostly a tool_calls
> loop on top of that.

## Feature Description

`SingleAgenticTrader` implements `Agent` (`src/agent_base.py`). On a weekly
cadence (first trading day per ISO week), it:

1. Builds a bound `LookaheadSafeTools(market_data, news_data, asof=info["date"])`
2. Calls `OpenAIClient.chat(model, messages, tools=specs, tool_choice="auto")`
3. **Loop** while response has `tool_calls` and `iteration < 10`:
   - Append the assistant message (with `tool_calls`) to `messages`
   - For each `tool_call`: dispatch via `tools.dispatch(name, arguments)`,
     append `{"role": "tool", "tool_call_id": id, "content": json.dumps(result)}`
   - Re-call `client.chat(messages=...)` with the same tools spec
4. Once final `result.text` arrives (no more tool_calls) OR cap hits:
   parse JSON weights via `parse_weights_json`
5. Cache weights for the rest of the ISO week
6. Append one record per LLM iteration + one decision summary to
   `results/single_agentic/tool_calls.jsonl`

Failure modes:
- Parser failure → hold-shares (parser handles)
- Network failure (RuntimeError after 5 retries) → hold-shares
- Tool dispatch `ValueError` (LLM hallucinated unknown tool / unknown ticker)
  → feed error string back as the tool result; loop continues so LLM can recover
- Iteration cap reached without text response → record cap-hit, hold-shares fallback

Cost target: **~$0.50–$1.50 per backtest** with gpt-4o-mini default
(~51 ISO weeks × ~3–8 LLM calls/decision × ~$0.005/call). PRD §14 Risk #5
notes single-agentic is the cheap track; multi-agent (PKG-8) is where cost risk concentrates.

## User Story

As a **PKG-10 backtest runner**
I want to **construct `SingleAgenticTrader(market_data, news_data,
model='gpt-4o-mini')` and pass it to `run_backtest`**
So that **I can compare zero-shot vs tool-using vs DDPG vs multi-agent on
the same env, on equal footing (same MarketData + news_data + seed)**.

As a **person 2 (verifier)**
I want **every tool call audited to disk with arguments + result preview +
asof date**
So that **I can spot lookahead violations or hallucinated tickers without
re-running the backtest**.

As a **report writer (Person 1)**
I want **per-decision iteration count + tool-name histogram in
`metrics.get_snapshot()`**
So that **the report's "hallucination rate" + "tool-use pattern" sections
have numeric grounding**.

## Problem Statement

3 distinct problems beyond what PKG-6 solved:

1. **Conversation state across `client.chat` calls.** OpenAI tool-calling
   is multi-turn: assistant message with `tool_calls` → tool result messages
   → next assistant message. The current `OpenAIClient.chat` is single-shot;
   PKG-7 has to reconstruct the OpenAI wire shape from `ChatResult` (which
   exposes `tool_calls: list[dict]` of parsed `{id, name, arguments(dict)}`).
2. **Iteration cap = correctness invariant.** Without a hard cap a runaway
   LLM could loop forever, burning cost. Issue #8 acceptance criterion
   explicitly requires "no decision > 10 tool calls". Cap must be enforced
   in our code, not "we hope the LLM stops".
3. **Tool-error recovery without crashing the backtest.** `LookaheadSafeTools`
   raises `ValueError` on unknown tool / unknown ticker. The agent must
   convert that into a tool result the LLM can read (not propagate the
   exception, which would crash 248 sessions). This is the only place where
   we let an LLM "self-correct" mid-decision.

## Solution Statement

8 design decisions LOCK before code (see DESIGN DECISIONS):

- **D1.** Weekly trigger via ISO week (mirror PKG-6 `_is_rebalance_day`).
- **D2.** System prompt locked in `src/llm/prompts/single_agentic.md`,
  loaded at module import. Pad to ≥ 1024 tokens for OpenAI auto-cache.
- **D3.** Tools = `LookaheadSafeTools.tool_specs()`. `tool_choice="auto"`
  (let LLM decide; don't force a call).
- **D4.** Iteration cap = **10** (hard). Cap counts assistant turns that
  contained `tool_calls`. Final text turn is not counted.
- **D5.** Default model = `gpt-4o-mini`. Override allowed.
- **D6.** Temperature = 0; no seed (same caveat as PKG-6).
- **D7.** Tool dispatch error → string error fed back as tool result.
- **D8.** Audit log = JSONL append-only, one row per tool_call + one
  "decision" summary row per `decide()` call.

## Feature Metadata

- **Feature Type:** New Capability (first tool-using LLM in the codebase)
- **Estimated Complexity:** **Medium** — single new core loop (tool_calls
  reconstruction); plumbing risk in OpenAI wire shape; rest is glue on
  patterns from PKG-6
- **Primary Systems Affected:** `src/llm/single_agentic.py`,
  `src/llm/prompts/single_agentic.md`, `tests/test_single_agentic.py`,
  `scripts/run_single_agentic.py`, `results/single_agentic/`
- **Dependencies:** All in PKG-5 (`OpenAIClient`, `LookaheadSafeTools`,
  `parse_weights_json`, `metrics`). No new external deps.

---

## CONTEXT REFERENCES

### Relevant Codebase Files — ĐỌC TRƯỚC KHI IMPLEMENT

**Reuse bắt buộc:**

- `src/agent_base.py` (toàn bộ, ~56 dòng) — `Agent` Protocol; `BacktestResult`
- `src/llm/client.py`:
  - `OpenAIClient.chat(model, messages, tools, tool_choice, temperature, max_retries)`
    — already supports `tools=` + `tool_choice=`; we ARE allowed to pass them.
  - `ChatResult` shape: `text: str | None`, `tool_calls: list[dict]` where
    each dict = `{"id": str, "name": str, "arguments": dict}` (arguments
    already JSON-decoded by `_to_result`, see `client.py:104-111`).
  - `finish_reason: str` — useful for telemetry but NOT the loop terminator
    (we terminate on "no tool_calls in response").
- `src/llm/tools.py`:
  - `LookaheadSafeTools(market_data, news_data, asof_session)` — dataclass,
    `__post_init__` normalizes `asof_session`. Bind once per decision.
  - `.tool_specs()` (classmethod, line 132) — OpenAI function-calling specs.
  - `.dispatch(name, arguments)` — raises `ValueError` on unknown name or
    unknown ticker. We MUST catch.
- `src/llm/parser.py`:
  - `parse_weights_json(text, info, ticker_order)` → `(action, success)`;
    success=False already triggers `_hold_shares_action` internally and
    records `parse_failure` metric.
  - `_hold_shares_action(info, tickers)` — re-export (same pattern PKG-6
    already does at `src/llm/zero_shot.py:29`).
- `src/llm/metrics.py`:
  - `record_llm_call(model, usage)` — already called inside
    `OpenAIClient._to_result`. Agent must NOT call again (double-count).
  - `record_parse_failure(reason)` — call ONLY on our own network catch
    (parser records its own).
  - `get_snapshot()` — read at end of backtest.
- `src/llm/serialize.py`:
  - `state_to_text(info, market_data, news_df=None, session_idx=None, total_sessions=None)`
    — same as PKG-6. **In PKG-7 we pass `news_df=None`** — the LLM should
    fetch news via the `get_news` tool, not get it pre-injected.
- `src/data_pipeline/news_align.py`:
  - `visible_news_at` (used by tools internally; agent does NOT call
    directly — defer to `LookaheadSafeTools.get_news`).
- `src/env_data_loader.py`:
  - `MarketData` (frozen dataclass), `load_market_data(split)` for CLI.

**Pattern bắt buộc mirror:**

- `src/llm/zero_shot.py` (entire file, ~132 lines) — class shape, `__init__`
  signature, `_is_rebalance_day`, `decide()` skeleton, fallback handling.
  PKG-7 is "PKG-6 + tool_calls loop in `decide()`".
- `tests/test_zero_shot.py` (entire file) — `_FakeClient` shape, response
  queue pattern, monkey-injected client. Mirror exactly; just add tool_calls
  to fake responses.
- `tests/test_llm_tools.py:14-42` — `_news_df` fixture helper. Re-derive in
  test file (acceptable duplication for PR boundary).
- `scripts/run_zero_shot.py` (entire file, ~138 lines) — CLI shape;
  `_run_n` smoke runner; `_write` parquet writer; metrics snapshot print.
- `src/baselines.py:_snapshot, _records_to_frames` — internal helpers
  imported by both `run_zero_shot.py` and (will be) `run_single_agentic.py`.
  Acceptable same-package private import.

**Read-only context (don't modify):**

- `CLAUDE.md` §"Domain-Specific Rules" §1 (no lookahead — `LookaheadSafeTools`
  is the audit point)
- `CLAUDE.md` §"Domain-Specific Rules" §2 (model lock — client enforces)
- `CLAUDE.md` §"Patterns" → "Pluggable agent interface" + "Decision layer ≠
  execution layer"
- `CLAUDE.md` §"Error handling" — "LLM parse failure → log + fallback hold";
  "DDPG diverge → fallback PPO"; same spirit for tool-error
- `.agent/PRD.md` §7 Feature 5 (Single-LLM Agentic description), §14 Risk #5
  (LLM cost ceiling)
- `.agent/TASKS.md:394-422` (PKG-7 spec, full text)
- GitHub Issue #8 (`PKG-7: Single-LLM agentic trader`) — acceptance criteria

**Don't touch (file ownership):**

- `src/llm/{client,tools,serialize,parser,metrics}.py` — PKG-5
- `src/llm/zero_shot.py` — PKG-6 (DO NOT refactor "to share code")
- `src/llm/prompts/zero_shot.md` — PKG-6
- `src/llm/multi_agent/*` — PKG-8
- `src/baselines.py`, `src/trading_env.py`, `src/env_data_loader.py` —
  earlier PKGs
- `src/agents/__init__.py` — PKG-S serialized

### New Files to Create

```
src/llm/
├── single_agentic.py                  # SingleAgenticTrader class
└── prompts/
    └── single_agentic.md              # System prompt (Vietnamese, ≥ 4000 chars)
scripts/
└── run_single_agentic.py              # CLI: backtest single-agentic on a split
tests/
└── test_single_agentic.py             # ~10 tests
results/single_agentic/                 # gitignored: tool_calls.jsonl,
                                       # portfolio_curve.parquet, holdings.parquet
```

### Relevant Documentation — ĐỌC TRƯỚC KHI IMPLEMENT

- **OpenAI Chat Completions — function calling multi-turn:**
  https://platform.openai.com/docs/guides/function-calling
  - Loop shape: assistant message với tool_calls → tool results với
    `tool_call_id` → continue assistant turn
  - **Wire shape of assistant message we re-send:**
    ```python
    {
      "role": "assistant",
      "content": result.text,            # may be None when only tool_calls
      "tool_calls": [
        {
          "id": tc["id"],
          "type": "function",
          "function": {
            "name": tc["name"],
            "arguments": json.dumps(tc["arguments"]),  # MUST be JSON STRING
          },
        }
        for tc in result.tool_calls
      ],
    }
    ```
  - **Wire shape of tool result message:**
    ```python
    {
      "role": "tool",
      "tool_call_id": tc["id"],
      "content": json.dumps(tool_output, ensure_ascii=False),
    }
    ```
  - `tool_call_id` MUST match assistant's `tool_calls[i].id` exactly or
    OpenAI rejects with 400.
- **`finish_reason` values:** `stop` (text done), `tool_calls` (wants tools
  next), `length` (hit max_tokens). We loop while `result.tool_calls` is
  non-empty regardless of `finish_reason`, because `finish_reason="tool_calls"`
  is the documented signal but we trust the structural check.
- **Auto prompt caching:** https://platform.openai.com/docs/guides/prompt-caching
  - Same as PKG-6: system prompt ≥ 1024 tokens caches automatically.
  - Multi-turn caches the PREFIX. As messages grow, only the static prefix
    (system + first user) caches; tool round-trips after grow uncached.
    Cost grows with iterations; cap helps bound it.
- **Issue #8 acceptance criteria:**
  - Audit log `results/single_agentic/tool_calls.jsonl` ghi đủ mọi call
  - Iteration cap enforced — không decision nào > 10 tool calls

### Pre-implementation spike (1 lệnh check trước khi code)

```bash
# Spike A: verify ChatResult.tool_calls round-trips correctly through
# message reconstruction → fake OpenAI mock. NO real OpenAI call.
.venv/bin/python <<'PY'
import json
from src.llm.client import ChatResult

# Simulate what _to_result produces for an assistant turn that called 2 tools
sim = ChatResult(
    text=None,
    tool_calls=[
        {"id": "call_1", "name": "get_indicators", "arguments": {"ticker": "VCB"}},
        {"id": "call_2", "name": "get_price_history",
         "arguments": {"ticker": "FPT", "days": 30}},
    ],
    usage={"prompt_tokens": 1500, "completion_tokens": 80, "cached_tokens": 1024,
           "total_tokens": 1580},
    model="gpt-4o-mini",
    finish_reason="tool_calls",
)

# Reconstruct OpenAI assistant message shape
assistant_msg = {
    "role": "assistant",
    "content": sim.text,
    "tool_calls": [
        {"id": tc["id"], "type": "function",
         "function": {"name": tc["name"],
                      "arguments": json.dumps(tc["arguments"])}}
        for tc in sim.tool_calls
    ],
}
print("Assistant message:")
print(json.dumps(assistant_msg, indent=2, ensure_ascii=False))
print()
# Tool result example
tool_msg = {
    "role": "tool",
    "tool_call_id": "call_1",
    "content": json.dumps({"ticker": "VCB", "indicators": {"rsi14": 0.5}}),
}
print("Tool message:")
print(json.dumps(tool_msg, indent=2, ensure_ascii=False))
# Expected: arguments are JSON-encoded strings inside function dict; ids match.
PY
```

Expected: arguments come out as JSON strings (NOT dicts) inside the assistant
message. This is the easy-to-miss gotcha that crashes the loop on first
real call.

```bash
# Spike B: hit dispatch ValueError to confirm error path
.venv/bin/python <<'PY'
import pandas as pd
from src.llm.tools import LookaheadSafeTools

md_stub = type("MD", (), {
    "tickers": ("VCB", "FPT", "HPG", "VIC", "VNM"),
    "dates": pd.DatetimeIndex(pd.date_range("2025-01-02", periods=10, freq="B")),
})()

tools = LookaheadSafeTools(md_stub, pd.DataFrame(), pd.Timestamp("2025-01-15"))
try:
    tools.dispatch("get_market_cap", {})
except ValueError as e:
    print(f"OK — caught: {e}")

try:
    tools.dispatch("get_price_history", {"ticker": "GOOGL"})
except ValueError as e:
    print(f"OK — caught: {e}")
PY
```

Expected: both raise `ValueError` with clear messages. PKG-7 catches and
turns into tool-result strings.

### Patterns to Follow (from codebase đã land)

**Class with weekly cadence + cached weights (mirror `src/llm/zero_shot.py`):**

```python
class SingleAgenticTrader:
    name: str = "single_agentic"

    def __init__(
        self,
        market_data: MarketData,
        news_data: pd.DataFrame,
        model: str = "gpt-4o-mini",
        client: OpenAIClient | None = None,
        weekly_rebalance: bool = True,
        max_iterations: int = 10,
        audit_log_path: Path | None = None,
    ) -> None:
        ...
        self._last_week: tuple[int, int] | None = None
        self._cached: np.ndarray | None = None
```

**Tool_calls loop (the NEW pattern PKG-7 introduces):**

```python
messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": user_text},
]
tool_specs = LookaheadSafeTools.tool_specs()
tools = LookaheadSafeTools(self.market_data, self.news_data, asof)

iteration = 0
final_text: str | None = None
while iteration < self.max_iterations:
    result = self._client.chat(
        model=self.model,
        messages=messages,
        tools=tool_specs,
        tool_choice="auto",
        temperature=0.0,
    )
    self._audit(iteration, info, result)  # log every turn
    if not result.tool_calls:
        final_text = result.text
        break
    messages.append(_assistant_message(result))
    for tc in result.tool_calls:
        try:
            tool_out = tools.dispatch(tc["name"], tc["arguments"])
            tool_payload = tool_out
        except ValueError as e:
            tool_payload = {"error": str(e)}
        messages.append({
            "role": "tool",
            "tool_call_id": tc["id"],
            "content": json.dumps(tool_payload, ensure_ascii=False, default=str),
        })
    iteration += 1
else:
    # cap hit without break → no final text
    log.warning("iteration cap reached at %s", info.get("date"))

action, ok = parse_weights_json(final_text, info,
                                ticker_order=list(self.market_data.tickers))
self._cached = action
return action.copy()
```

**Mock OpenAI in tests (extend PKG-6's `_FakeClient` to queue tool_calls
responses):**

```python
def _resp_tools(tool_calls: list[dict]) -> ChatResult:
    """ChatResult that asks for tool calls."""
    return ChatResult(
        text=None, tool_calls=tool_calls,
        usage={"prompt_tokens": 1200, "completion_tokens": 30,
               "cached_tokens": 1024, "total_tokens": 1230},
        model="gpt-4o-mini", finish_reason="tool_calls",
    )

def _resp_text(text: str) -> ChatResult:
    """Final assistant text (no tool_calls)."""
    return ChatResult(
        text=text, tool_calls=[],
        usage={"prompt_tokens": 1500, "completion_tokens": 50,
               "cached_tokens": 1024, "total_tokens": 1550},
        model="gpt-4o-mini", finish_reason="stop",
    )
```

**Audit log format (one JSON object per line):**

```python
# Per LLM iteration:
{"ts": "2026-...", "date": "2025-05-05", "agent": "single_agentic",
 "iteration": 0, "n_tool_calls": 2,
 "tool_calls": [{"name": "get_indicators", "args": {"ticker": "VCB"}}, ...],
 "usage": {"prompt_tokens": 1500, "cached_tokens": 1024, ...}}

# Per decision (last row):
{"ts": "2026-...", "date": "2025-05-05", "agent": "single_agentic",
 "event": "decision", "iterations_used": 3, "cap_hit": false,
 "final_text_preview": "{\"VCB\": 0.2, ...}",
 "parse_ok": true, "action_sum": 0.95,
 "tool_name_counts": {"get_indicators": 5, "get_news": 2}}
```

**Error handling (CLAUDE.md alignment):**

- Tool dispatch `ValueError` → JSON error string fed back; LLM can recover
- Network `RuntimeError` (after 5 retries) → log + `metrics.record_parse_failure(reason="network_…")` + hold-shares fallback
- Parser failure already handled by `parse_weights_json` (records `parse_failure`)
- Iteration cap reached → `metrics.record_parse_failure(reason="iteration_cap")` + hold-shares
- Audit log write failure → catch + log warning, do NOT crash backtest

---

## DESIGN DECISIONS — LOCK BEFORE IMPLEMENT

### D1. Weekly trigger = ISO week change (mirror PKG-6)

```python
def _is_rebalance_day(self, info: dict) -> bool:
    ts = pd.Timestamp(info["date"])
    iso = ts.isocalendar()
    key = (int(iso.year), int(iso.week))
    if key != self._last_week:
        self._last_week = key
        return True
    return False
```

Identical logic to `ZeroShotTrader._is_rebalance_day`. Don't import — copy.
Two modules, two owners; private state.

### D2. System prompt locked in `prompts/single_agentic.md`

```python
_PROMPT_PATH = Path(__file__).parent / "prompts" / "single_agentic.md"
SYSTEM_PROMPT: str = _PROMPT_PATH.read_text(encoding="utf-8")
```

Content includes:

- Role: Vietnamese quant trader (same boilerplate as PKG-6)
- Universe + HOSE rules + lookahead rule (same)
- **NEW: Tool usage guidance.** Describe each of the 4 tools, when to call
  them, that arguments must use `enum` tickers, and that the LLM should
  iterate AT MOST a handful of times before emitting weights.
- Output schema (same JSON shape as PKG-6) + final instruction "after you
  have enough information, emit weights"
- Pad to ≥ 4000 chars (~1024 tokens) for auto-cache

Test for byte count: `wc -c src/llm/prompts/single_agentic.md` ≥ 4000.

### D3. Tools = full `LookaheadSafeTools.tool_specs()`; `tool_choice="auto"`

```python
result = self._client.chat(
    model=self.model,
    messages=messages,
    tools=LookaheadSafeTools.tool_specs(),
    tool_choice="auto",
    temperature=0.0,
)
```

We pass ALL 4 tools every iteration (specs are cheap; ~600 tokens, cached).
`tool_choice="auto"` lets LLM choose; we don't force a tool call. Avoid
`"required"` — sometimes LLM has enough info from the state + prior tool
returns and should be allowed to skip directly to text.

### D4. Iteration cap = 10 (hard)

```python
max_iterations: int = 10  # constructor default; per-instance override OK
```

Counts iterations of the **outer loop**: each iteration = 1 LLM call that
returned `tool_calls`. The final LLM call that returns text is NOT counted
as an iteration (it terminates the loop). So at iteration cap = 10, up to
11 LLM calls (10 tool-call rounds + 1 final text round) per decision — but
cap is hit only if LLM keeps asking after 10 rounds.

If cap hits without a text response: `metrics.record_parse_failure(reason="iteration_cap")`,
emit hold-shares, log warning, audit `cap_hit=true`. Issue #8: "không decision nào > 10 tool calls" → enforce by EXITING loop, not by silent truncation.

Justification of 10: Sonnet-class LLMs typically settle in 3-5 iterations on this prompt structure. 10 leaves 2x headroom. Per-decision cost ceiling: 10 × ~$0.005 = $0.05/decision worst case, × 51 weeks = $2.55 worst case full backtest. Acceptable.

### D5. Default model = `gpt-4o-mini`

Cost estimate per backtest (51 weeks, ~5 iter avg):
- gpt-4o-mini: 51 × 5 × ~$0.005 ≈ **$1.30/backtest**
- gpt-4o: 51 × 5 × ~$0.05 ≈ **$13/backtest** (use only for ablation)

User override: `SingleAgenticTrader(..., model="gpt-4o")`. Client whitelist still applies.

### D6. Temperature = 0; no seed (same as PKG-6)

Document residual ~1-2% non-determinism across runs in PR + report.

### D7. Tool dispatch error → string error fed back

```python
for tc in result.tool_calls:
    try:
        tool_out = tools.dispatch(tc["name"], tc["arguments"])
    except (ValueError, TypeError) as e:
        tool_out = {"error": f"{type(e).__name__}: {e}"}
    messages.append({
        "role": "tool",
        "tool_call_id": tc["id"],
        "content": json.dumps(tool_out, ensure_ascii=False, default=str),
    })
```

LLM sees `{"error": "unknown ticker 'GOOGL'..."}` as tool result and can
correct on next turn. NEVER propagate the exception — that would crash a
248-session backtest on one hallucination.

Audit log captures `error=true` per call so PKG-10 can compute
`hallucination_rate = errored_tool_calls / total_tool_calls`.

### D8. Audit log = JSONL append-only

```python
def _audit(self, iteration: int, info: dict, result: ChatResult,
           tool_results: list[dict] | None = None) -> None:
    if self.audit_log_path is None:
        return
    self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "agent": self.name,
        "date": str(info.get("date", ""))[:10],
        "iteration": iteration,
        "model": result.model,
        "n_tool_calls": len(result.tool_calls),
        "tool_calls": [
            {"id": tc["id"], "name": tc["name"], "args": tc["arguments"],
             "errored": (tool_results or [{}])[i].get("errored", False)}
            for i, tc in enumerate(result.tool_calls)
        ] if result.tool_calls else [],
        "usage": result.usage,
        "finish_reason": result.finish_reason,
    }
    try:
        with self.audit_log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    except OSError as e:
        log.warning("audit log write failed: %s", e)
```

Default path: `config.PROJECT_ROOT / "results" / "single_agentic" / "tool_calls.jsonl"`.
Caller can override (tests pass `tmp_path / "audit.jsonl"`). Tests also
pass `audit_log_path=None` for cases where log is not under test.

JSONL chosen over JSON: append-only, no need to load+rewrite, robust to
crash mid-backtest (last line truncated, prior intact).

---

## IMPLEMENTATION PLAN

### Phase 1: Prompt + skeleton

**Goal:** Lock the system prompt, set up module structure.

- Author `src/llm/prompts/single_agentic.md` (Vietnamese, ≥ 4000 chars,
  mirror PKG-6 structure + tool-usage section)
- Author `src/llm/single_agentic.py` skeleton: imports, `SYSTEM_PROMPT`
  load, class with `__init__`, attributes, `_is_rebalance_day`

### Phase 2: Tool_calls loop in `decide()`

**Goal:** The new core. Wire `client.chat` → tool dispatch → re-call.

- `_build_user_message(info)` — same as PKG-6 minus pre-injected news
  (LLM fetches via `get_news` tool instead)
- `_assistant_message(result)` — convert `ChatResult` → OpenAI wire shape
- `_dispatch_tool_call(tools, tc)` — try/except wrapper returning
  `(payload, errored: bool)`
- `decide(obs, info)` — week check → loop → parse → cache + audit

### Phase 3: Audit log

**Goal:** Per-iteration + per-decision JSONL.

- `_audit_iteration(iteration, info, result, tool_results)`
- `_audit_decision(info, iterations_used, cap_hit, final_text, action, ok)`
- Both no-op when `audit_log_path is None`

### Phase 4: Tests

**Goal:** ~10 tests covering: protocol, weekly cadence, tool loop,
iteration cap, tool error recovery, parse fallback, network fallback,
audit log shape, news NOT pre-injected, weekly_rebalance toggle.

### Phase 5: CLI + real smoke

**Goal:** 1-command run on test split; smoke 10 sessions with real key.

- `scripts/run_single_agentic.py` — mirror `run_zero_shot.py`
- Real-call smoke (manual, PR description)

---

## STEP-BY-STEP TASKS

### 1. CREATE `src/llm/prompts/single_agentic.md`

- **IMPLEMENT:** Vietnamese system prompt with these sections (order
  matters — front-load stable content for cache):
  1. **Vai trò** — same as PKG-6 (quant trader, VN HOSE, academic backtest)
  2. **Vũ trụ đầu tư (đã khóa)** — same 5 tickers
  3. **Quy tắc thị trường HOSE** — same env-handled constraints
  4. **Quy tắc thông tin (NGHIÊM NGẶT — lookahead-safe)** — same lookahead
     rule + explicit note that the `get_news` tool already filters to
     visible news; LLM doesn't need to worry
  5. **Tần suất quyết định** — weekly
  6. **NEW: Công cụ điều tra (Tools)** — describe each of the 4 tools:
     - `get_price_history(ticker, days=30)` — historical OHLC
     - `get_indicators(ticker)` — 9 z-scored technicals at last pre-asof bar
     - `get_news(date?, ticker?)` — visible news (D+2 lag)
     - `get_fundamentals(ticker)` — 4-quarter snapshot, ~30d reporting lag
     - **Suggested workflow**: 1 round of indicators + 1 round of news
       for tickers with strong signals, then emit weights. Max 10 rounds.
  7. **NEW: Quy trình ra quyết định** — explicit "after you've gathered
     enough information, emit weights as JSON. If unsure, default near
     equal-weight (0.18 each, 10% cash)."
  8. **Định dạng phản hồi (BẮT BUỘC)** — same JSON shape as PKG-6 (so
     `parse_weights_json` reuses identical logic)
  9. **Thận trọng & disclaimer** — same as PKG-6
- **PATTERN:** Open `src/llm/prompts/zero_shot.md`, fork content; insert
  sections 6+7 (tools + decision workflow) between sections 5 and 8.
- **GOTCHA:** Vietnamese diacritics — save UTF-8. Don't paste from formatted
  doc app (auto-replaces straight quotes with curly quotes which break the
  example JSON block).
- **VALIDATE:**
  ```bash
  test $(wc -c < src/llm/prompts/single_agentic.md) -ge 4000 && echo OK
  ```

### 2. CREATE `src/llm/single_agentic.py`

- **IMPLEMENT:**
  ```python
  """Single-LLM agentic trader — tool-using.

  One LLM. 4 tools (price, indicators, news, fundamentals) via
  LookaheadSafeTools. Per ISO week: client.chat loops up to 10 iterations,
  feeding tool results back, until LLM emits text → parse JSON weights.

  Weekly cadence (D1): same as zero_shot. Network/parse/cap failures all
  fall back to hold-shares (parser semantics). Tool dispatch errors are
  fed back to the LLM so it can self-correct mid-decision.

  Audit log: one JSONL row per LLM iteration + one decision summary row,
  written to results/single_agentic/tool_calls.jsonl (PRD §"hallucination
  metrics" + Issue #8 acceptance criterion).
  """

  from __future__ import annotations

  import json
  import logging
  from collections import Counter
  from datetime import datetime, timezone
  from pathlib import Path

  import numpy as np
  import pandas as pd

  from src import config
  from src.env_data_loader import MarketData
  from src.llm import metrics
  from src.llm.client import ChatResult, OpenAIClient
  from src.llm.parser import _hold_shares_action, parse_weights_json
  from src.llm.serialize import state_to_text
  from src.llm.tools import LookaheadSafeTools

  log = logging.getLogger(__name__)

  _PROMPT_PATH = Path(__file__).parent / "prompts" / "single_agentic.md"
  SYSTEM_PROMPT: str = _PROMPT_PATH.read_text(encoding="utf-8")
  _DEFAULT_AUDIT_PATH = (
      config.PROJECT_ROOT / "results" / "single_agentic" / "tool_calls.jsonl"
  )
  _DEFAULT_MAX_ITERATIONS: int = 10


  class SingleAgenticTrader:
      """LLM agent that uses 4 tools to investigate before emitting weights."""

      name: str = "single_agentic"

      def __init__(
          self,
          market_data: MarketData,
          news_data: pd.DataFrame,
          model: str = "gpt-4o-mini",
          client: OpenAIClient | None = None,
          weekly_rebalance: bool = True,
          max_iterations: int = _DEFAULT_MAX_ITERATIONS,
          audit_log_path: Path | None = _DEFAULT_AUDIT_PATH,
      ) -> None:
          self.market_data = market_data
          self.news_data = news_data
          self.model = model
          self._client = client or OpenAIClient()
          self.weekly_rebalance = weekly_rebalance
          self.max_iterations = int(max_iterations)
          self.audit_log_path = (
              Path(audit_log_path) if audit_log_path is not None else None
          )
          self._last_week: tuple[int, int] | None = None
          self._cached: np.ndarray | None = None

      def decide(self, obs: np.ndarray, info: dict) -> np.ndarray:
          is_rebal = self._is_rebalance_day(info)
          if (
              self.weekly_rebalance
              and self._cached is not None
              and not is_rebal
          ):
              return self._cached.copy()

          asof = pd.Timestamp(info["date"]).normalize()
          tools = LookaheadSafeTools(self.market_data, self.news_data, asof)
          tool_specs = LookaheadSafeTools.tool_specs()
          messages: list[dict] = [
              {"role": "system", "content": SYSTEM_PROMPT},
              {"role": "user", "content": self._build_user_message(info)},
          ]

          tool_name_counts: Counter[str] = Counter()
          iterations_used = 0
          cap_hit = False
          final_text: str | None = None

          try:
              while iterations_used < self.max_iterations:
                  result = self._client.chat(
                      model=self.model,
                      messages=messages,
                      tools=tool_specs,
                      tool_choice="auto",
                      temperature=0.0,
                  )
                  if not result.tool_calls:
                      self._audit_iteration(iterations_used, info, result, [])
                      final_text = result.text
                      break

                  # Reconstruct assistant message + dispatch tool calls
                  messages.append(self._assistant_message(result))
                  per_call_results: list[dict] = []
                  for tc in result.tool_calls:
                      payload, errored = self._dispatch_tool_call(tools, tc)
                      tool_name_counts[tc["name"]] += 1
                      per_call_results.append({"errored": errored})
                      messages.append(
                          {
                              "role": "tool",
                              "tool_call_id": tc["id"],
                              "content": json.dumps(
                                  payload, ensure_ascii=False, default=str
                              ),
                          }
                      )
                  self._audit_iteration(
                      iterations_used, info, result, per_call_results
                  )
                  iterations_used += 1
              else:
                  cap_hit = True
                  log.warning(
                      "single_agentic iteration cap %d hit at %s",
                      self.max_iterations,
                      info.get("date"),
                  )
          except RuntimeError as e:
              log.warning(
                  "LLM call failed for %s at %s: %s — hold-shares fallback",
                  self.name,
                  info.get("date"),
                  e,
              )
              metrics.record_parse_failure(reason=f"network_{type(e).__name__}")
              action = _hold_shares_action(
                  info, list(self.market_data.tickers)
              )
              self._audit_decision(
                  info, iterations_used, cap_hit, None, action, False,
                  tool_name_counts, network_error=str(e),
              )
              self._cached = action
              return action.copy()

          if cap_hit and final_text is None:
              metrics.record_parse_failure(reason="iteration_cap")
              action = _hold_shares_action(
                  info, list(self.market_data.tickers)
              )
              ok = False
          else:
              action, ok = parse_weights_json(
                  final_text,
                  info,
                  ticker_order=list(self.market_data.tickers),
              )

          self._audit_decision(
              info, iterations_used, cap_hit, final_text, action, ok,
              tool_name_counts,
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

      def _build_user_message(self, info: dict) -> str:
          # Note: PKG-7 does NOT pre-inject news — the LLM should call
          # get_news() when it wants headlines. Keeps the prompt small +
          # lets the LLM steer.
          state_text = state_to_text(info, self.market_data, news_df=None)
          return (
              state_text
              + "\n\n## Yêu cầu\n"
                "Bạn có thể gọi các công cụ (get_price_history, "
                "get_indicators, get_news, get_fundamentals) nếu cần "
                "thêm thông tin. Khi đã đủ căn cứ, trả về DUY NHẤT một "
                "khối JSON với weights cho 5 mã (VCB, FPT, HPG, VIC, VNM)."
          )

      @staticmethod
      def _assistant_message(result: ChatResult) -> dict:
          """Reconstruct OpenAI assistant wire shape from ChatResult.

          ChatResult.tool_calls[i].arguments is already a parsed dict (from
          OpenAIClient._to_result) — we must JSON-encode it back to a string
          for the OpenAI function-calling wire format.
          """
          return {
              "role": "assistant",
              "content": result.text,
              "tool_calls": [
                  {
                      "id": tc["id"],
                      "type": "function",
                      "function": {
                          "name": tc["name"],
                          "arguments": json.dumps(
                              tc["arguments"], ensure_ascii=False
                          ),
                      },
                  }
                  for tc in result.tool_calls
              ],
          }

      @staticmethod
      def _dispatch_tool_call(
          tools: LookaheadSafeTools, tc: dict
      ) -> tuple[object, bool]:
          """Dispatch a single tool call; convert errors to LLM-readable payloads.

          Returns (payload, errored). errored is True if dispatch raised —
          PKG-10 reads this to compute hallucination_rate.
          """
          try:
              return tools.dispatch(tc["name"], tc.get("arguments") or {}), False
          except (ValueError, TypeError) as e:
              return {"error": f"{type(e).__name__}: {e}"}, True

      def _audit_iteration(
          self,
          iteration: int,
          info: dict,
          result: ChatResult,
          per_call_results: list[dict],
      ) -> None:
          if self.audit_log_path is None:
              return
          rec = {
              "ts": datetime.now(timezone.utc).isoformat(),
              "agent": self.name,
              "event": "iteration",
              "date": str(info.get("date", ""))[:10],
              "iteration": iteration,
              "model": result.model,
              "finish_reason": result.finish_reason,
              "n_tool_calls": len(result.tool_calls),
              "tool_calls": [
                  {
                      "id": tc["id"],
                      "name": tc["name"],
                      "args": tc["arguments"],
                      "errored": (
                          per_call_results[i]["errored"]
                          if i < len(per_call_results)
                          else False
                      ),
                  }
                  for i, tc in enumerate(result.tool_calls)
              ],
              "usage": result.usage,
          }
          self._write_audit(rec)

      def _audit_decision(
          self,
          info: dict,
          iterations_used: int,
          cap_hit: bool,
          final_text: str | None,
          action: np.ndarray,
          parse_ok: bool,
          tool_name_counts: Counter[str],
          network_error: str | None = None,
      ) -> None:
          if self.audit_log_path is None:
              return
          preview = (final_text or "")[:200]
          rec = {
              "ts": datetime.now(timezone.utc).isoformat(),
              "agent": self.name,
              "event": "decision",
              "date": str(info.get("date", ""))[:10],
              "iterations_used": iterations_used,
              "cap_hit": cap_hit,
              "network_error": network_error,
              "final_text_preview": preview,
              "parse_ok": parse_ok,
              "action_sum": float(action.sum()) if action is not None else None,
              "tool_name_counts": dict(tool_name_counts),
          }
          self._write_audit(rec)

      def _write_audit(self, rec: dict) -> None:
          try:
              self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
              with self.audit_log_path.open("a", encoding="utf-8") as f:
                  f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
          except OSError as e:
              log.warning("audit log write failed: %s", e)
  ```
- **PATTERN:** Mirror `src/llm/zero_shot.py` for shape; the tool loop is
  the only genuinely new logic.
- **GOTCHA #1:** `tc["arguments"]` is a dict in `ChatResult` but OpenAI
  wire format expects a JSON-STRING. Re-encode with `json.dumps` when
  appending to messages. Spike A verifies.
- **GOTCHA #2:** `_to_result` falls back to `{"_raw": <str>}` when
  `tc.function.arguments` is non-JSON (`client.py:106-108`). Don't crash
  on dispatch — `tools.dispatch(name, {"_raw": ...})` will raise TypeError
  (unexpected kwarg), caught by D7 path → error fed back.
- **GOTCHA #3:** `messages.append(self._assistant_message(result))` MUST
  preserve `tc["id"]` exactly. If you regenerate IDs you'll get OpenAI
  400 "tool_call_id mismatch".
- **GOTCHA #4:** Do NOT call `metrics.record_llm_call` from the agent —
  `OpenAIClient._to_result` already records it for every chat call.
  Double-counting would skew cost reporting.
- **GOTCHA #5:** The `while/else` clause runs only if the loop exits via
  `iterations_used >= max_iterations` (not via `break`). This is the
  `cap_hit = True` path. Python idiom — verify with a quick `for/else`
  refresher if uncertain.
- **GOTCHA #6:** Audit log path defaults to a hardcoded location.
  Tests MUST pass `audit_log_path=tmp_path / "audit.jsonl"` (or None) or
  they pollute `results/` between runs.
- **GOTCHA #7:** `default=str` in `json.dumps` handles `pd.Timestamp`,
  `np.ndarray`, etc. that tool results may contain. Don't remove it.
- **VALIDATE:**
  ```bash
  .venv/bin/python -c "from src.llm.single_agentic import SingleAgenticTrader; print(SingleAgenticTrader.name)"
  # Expect: single_agentic
  .venv/bin/ruff check src/llm/single_agentic.py
  ```

### 3. CREATE `tests/test_single_agentic.py`

- **IMPLEMENT:** ~10 tests using `_FakeClient` (extend PKG-6 pattern):
  ```python
  """SingleAgenticTrader invariants — tool loop, cap, audit log, fallbacks.

  Uses synthetic_market_data fixture + fake OpenAIClient queue (mirror
  test_zero_shot.py). No real OpenAI calls. No real disk pollution
  (audit_log_path uses tmp_path).
  """
  from __future__ import annotations
  import json
  from dataclasses import dataclass, field
  from pathlib import Path
  from typing import Any

  import numpy as np
  import pandas as pd
  import pytest

  from src.agent_base import Agent
  from src.data_pipeline.news_align import compute_available_for_session
  from src.env_data_loader import MarketData
  from src.llm import metrics
  from src.llm.client import ChatResult
  from src.llm.single_agentic import SingleAgenticTrader


  @dataclass
  class _FakeClient:
      responses: list[Any]
      raise_on_call: int | None = None  # raise on the Nth call (0-indexed)
      calls: list[dict] = field(default_factory=list)

      def chat(self, **kwargs) -> ChatResult:
          idx = len(self.calls)
          self.calls.append(kwargs)
          if self.raise_on_call is not None and idx == self.raise_on_call:
              raise RuntimeError("OpenAI all retries failed")
          if not self.responses:
              raise RuntimeError("no fake responses queued")
          return self.responses.pop(0)


  def _resp_tools(tool_calls: list[dict]) -> ChatResult:
      return ChatResult(
          text=None, tool_calls=tool_calls,
          usage={"prompt_tokens": 1200, "completion_tokens": 30,
                 "cached_tokens": 1024, "total_tokens": 1230},
          model="gpt-4o-mini", finish_reason="tool_calls",
      )


  def _resp_text(text: str) -> ChatResult:
      return ChatResult(
          text=text, tool_calls=[],
          usage={"prompt_tokens": 1500, "completion_tokens": 50,
                 "cached_tokens": 1024, "total_tokens": 1550},
          model="gpt-4o-mini", finish_reason="stop",
      )


  def _tool_call(idx: int, name: str, args: dict) -> dict:
      return {"id": f"call_{idx}", "name": name, "arguments": args}


  def _info(date: str, holdings=None, pv: float = 1_000_000_000.0,
            close_t=None) -> dict:
      return {
          "date": date, "t": 0, "cash": pv * 0.05,
          "holdings": holdings or [3_200_000, 2_100_000, 6_900_000, 880_000, 3_000_000],
          "portfolio_value": pv,
          "close_t": close_t or [55.5, 90.1, 27.4, 215.2, 62.0],
      }


  def test_protocol_runtime_check(synthetic_market_data, tmp_path):
      fake = _FakeClient(responses=[_resp_text('{"VCB":0.2,"FPT":0.2,"HPG":0.2,"VIC":0.2,"VNM":0.1}')])
      agent = SingleAgenticTrader(
          synthetic_market_data, pd.DataFrame(),
          client=fake, audit_log_path=tmp_path / "audit.jsonl",
      )
      assert isinstance(agent, Agent)
      assert agent.name == "single_agentic"


  def test_zero_tool_calls_emits_weights_immediately(synthetic_market_data, tmp_path):
      """LLM may decide it has enough info from the user message alone —
      then it emits text in turn 0 and we exit the loop without tools."""
      fake = _FakeClient(responses=[_resp_text('{"VCB":0.3,"FPT":0.2,"HPG":0.1,"VIC":0.2,"VNM":0.1}')])
      agent = SingleAgenticTrader(synthetic_market_data, pd.DataFrame(),
                                  client=fake,
                                  audit_log_path=tmp_path / "a.jsonl")
      obs = np.zeros(56, dtype=np.float32)
      a = agent.decide(obs, _info(synthetic_market_data.dates[0].isoformat()))
      assert len(fake.calls) == 1
      assert a.sum() == pytest.approx(0.9, abs=0.01)


  def test_tool_loop_dispatches_and_continues(synthetic_market_data, tmp_path):
      """LLM asks for get_indicators(VCB) → we dispatch and feed result back
      → LLM emits weights. 2 LLM calls; 1 tool dispatch."""
      tc = _tool_call(1, "get_indicators", {"ticker": "VCB"})
      fake = _FakeClient(responses=[
          _resp_tools([tc]),
          _resp_text('{"VCB":0.4,"FPT":0.2,"HPG":0.1,"VIC":0.2,"VNM":0.1}'),
      ])
      agent = SingleAgenticTrader(synthetic_market_data, pd.DataFrame(),
                                  client=fake,
                                  audit_log_path=tmp_path / "a.jsonl")
      obs = np.zeros(56, dtype=np.float32)
      a = agent.decide(obs, _info(synthetic_market_data.dates[5].isoformat()))
      assert len(fake.calls) == 2
      # 2nd call should have role=tool message with the right tool_call_id
      second_msgs = fake.calls[1]["messages"]
      tool_msg = [m for m in second_msgs if m.get("role") == "tool"][0]
      assert tool_msg["tool_call_id"] == "call_1"
      payload = json.loads(tool_msg["content"])
      assert payload["ticker"] == "VCB"


  def test_iteration_cap_enforced(synthetic_market_data, tmp_path):
      """LLM that NEVER stops asking → cap fires at max_iterations.
      Issue #8 acceptance: 'không decision nào > 10 tool calls'."""
      metrics.reset()
      tc = _tool_call(99, "get_indicators", {"ticker": "VCB"})
      # Queue 15 tool-call responses — way more than cap
      responses = [_resp_tools([tc]) for _ in range(15)]
      fake = _FakeClient(responses=responses)
      agent = SingleAgenticTrader(
          synthetic_market_data, pd.DataFrame(),
          client=fake, max_iterations=3,
          audit_log_path=tmp_path / "a.jsonl",
      )
      obs = np.zeros(56, dtype=np.float32)
      a = agent.decide(obs, _info(synthetic_market_data.dates[5].isoformat()))
      # Exactly max_iterations LLM calls, no more
      assert len(fake.calls) == 3
      # Hold-shares fallback (significant non-zero allocation)
      assert a.sum() > 0.5
      snap = metrics.get_snapshot()
      assert snap["parse_failure_reasons"].get("iteration_cap", 0) >= 1


  def test_tool_dispatch_error_fed_back_to_llm(synthetic_market_data, tmp_path):
      """LLM hallucinates 'get_market_cap' → tools.dispatch raises ValueError →
      we feed {'error': ...} back; LLM recovers and emits weights."""
      tc_bad = _tool_call(1, "get_market_cap", {})
      fake = _FakeClient(responses=[
          _resp_tools([tc_bad]),
          _resp_text('{"VCB":0.2,"FPT":0.2,"HPG":0.2,"VIC":0.2,"VNM":0.1}'),
      ])
      agent = SingleAgenticTrader(synthetic_market_data, pd.DataFrame(),
                                  client=fake,
                                  audit_log_path=tmp_path / "a.jsonl")
      obs = np.zeros(56, dtype=np.float32)
      # Must NOT raise
      a = agent.decide(obs, _info(synthetic_market_data.dates[5].isoformat()))
      assert len(fake.calls) == 2
      tool_msg = [m for m in fake.calls[1]["messages"] if m.get("role") == "tool"][0]
      payload = json.loads(tool_msg["content"])
      assert "error" in payload
      assert "unknown tool" in payload["error"].lower()
      # Audit log should mark errored
      lines = (tmp_path / "a.jsonl").read_text().splitlines()
      iter_recs = [json.loads(line) for line in lines
                   if json.loads(line)["event"] == "iteration"]
      assert any(tc.get("errored") for rec in iter_recs for tc in rec["tool_calls"])


  def test_weekly_cache_skips_llm_within_same_week(synthetic_market_data, tmp_path):
      """Second decide() within same ISO week reuses cached weights → 0
      additional LLM calls. Mirror PKG-6 invariant for cost control."""
      fake = _FakeClient(responses=[_resp_text('{"VCB":0.3,"FPT":0.2,"HPG":0.1,"VIC":0.2,"VNM":0.1}')])
      agent = SingleAgenticTrader(synthetic_market_data, pd.DataFrame(),
                                  client=fake,
                                  audit_log_path=tmp_path / "a.jsonl")
      obs = np.zeros(56, dtype=np.float32)
      a1 = agent.decide(obs, _info(synthetic_market_data.dates[0].isoformat()))
      a2 = agent.decide(obs, _info(synthetic_market_data.dates[1].isoformat()))
      assert len(fake.calls) == 1
      np.testing.assert_allclose(a1, a2)


  def test_iso_week_change_triggers_new_decision(synthetic_market_data, tmp_path):
      fake = _FakeClient(responses=[
          _resp_text('{"VCB":0.3,"FPT":0.2,"HPG":0.1,"VIC":0.2,"VNM":0.1}'),
          _resp_text('{"VCB":0.1,"FPT":0.3,"HPG":0.3,"VIC":0.1,"VNM":0.1}'),
      ])
      agent = SingleAgenticTrader(synthetic_market_data, pd.DataFrame(),
                                  client=fake,
                                  audit_log_path=tmp_path / "a.jsonl")
      obs = np.zeros(56, dtype=np.float32)
      agent.decide(obs, _info(synthetic_market_data.dates[0].isoformat()))
      agent.decide(obs, _info(synthetic_market_data.dates[5].isoformat()))
      assert len(fake.calls) == 2


  def test_parse_failure_falls_back_to_hold_shares(synthetic_market_data, tmp_path):
      metrics.reset()
      fake = _FakeClient(responses=[_resp_text("I refuse to give weights.")])
      agent = SingleAgenticTrader(synthetic_market_data, pd.DataFrame(),
                                  client=fake,
                                  audit_log_path=tmp_path / "a.jsonl")
      obs = np.zeros(56, dtype=np.float32)
      a = agent.decide(obs, _info(synthetic_market_data.dates[0].isoformat()))
      assert a.sum() > 0.5  # hold-shares
      snap = metrics.get_snapshot()
      assert snap["parse_failure"] >= 1


  def test_network_failure_falls_back_to_hold_shares(synthetic_market_data, tmp_path):
      metrics.reset()
      fake = _FakeClient(responses=[], raise_on_call=0)
      agent = SingleAgenticTrader(synthetic_market_data, pd.DataFrame(),
                                  client=fake,
                                  audit_log_path=tmp_path / "a.jsonl")
      obs = np.zeros(56, dtype=np.float32)
      a = agent.decide(obs, _info(synthetic_market_data.dates[0].isoformat()))
      assert a.sum() > 0.5
      snap = metrics.get_snapshot()
      assert any(k.startswith("network_") for k in snap["parse_failure_reasons"])


  def test_audit_log_contains_decision_summary(synthetic_market_data, tmp_path):
      """JSONL must contain at least 1 'iteration' and 1 'decision' record
      per decide() call, with iterations_used + cap_hit + tool_name_counts."""
      tc = _tool_call(1, "get_indicators", {"ticker": "VCB"})
      fake = _FakeClient(responses=[
          _resp_tools([tc]),
          _resp_text('{"VCB":0.4,"FPT":0.2,"HPG":0.1,"VIC":0.2,"VNM":0.1}'),
      ])
      audit = tmp_path / "audit.jsonl"
      agent = SingleAgenticTrader(synthetic_market_data, pd.DataFrame(),
                                  client=fake, audit_log_path=audit)
      obs = np.zeros(56, dtype=np.float32)
      agent.decide(obs, _info(synthetic_market_data.dates[5].isoformat()))

      records = [json.loads(line) for line in audit.read_text().splitlines()]
      events = [r["event"] for r in records]
      assert "iteration" in events
      assert "decision" in events
      decision = [r for r in records if r["event"] == "decision"][-1]
      assert decision["iterations_used"] == 1
      assert decision["cap_hit"] is False
      assert decision["tool_name_counts"] == {"get_indicators": 1}
      assert decision["parse_ok"] is True


  def test_audit_log_can_be_disabled(synthetic_market_data, tmp_path):
      """audit_log_path=None must NOT create files."""
      fake = _FakeClient(responses=[_resp_text('{"VCB":0.2,"FPT":0.2,"HPG":0.2,"VIC":0.2,"VNM":0.1}')])
      agent = SingleAgenticTrader(synthetic_market_data, pd.DataFrame(),
                                  client=fake, audit_log_path=None)
      obs = np.zeros(56, dtype=np.float32)
      agent.decide(obs, _info(synthetic_market_data.dates[0].isoformat()))
      # No audit files should appear anywhere in tmp_path
      assert not list(tmp_path.glob("**/*.jsonl"))


  def test_news_not_pre_injected_into_user_message(synthetic_market_data, tmp_path):
      """PKG-7 leaves news for the LLM to fetch via get_news tool. The
      user message must NOT mention 'Recent news' section.

      Differs from PKG-6 which pre-filters and serializes news."""
      md = synthetic_market_data
      pub = pd.to_datetime([md.dates[1].strftime("%Y-%m-%d") + " 09:00"]).tz_localize(
          "Asia/Ho_Chi_Minh"
      ).tz_convert("UTC")
      news = pd.DataFrame({
          "published_at_utc": pub, "source": ["cafef"], "url": ["https://x"],
          "title": ["VCB earnings"], "summary": [None], "tickers": [["VCB"]],
      })
      news["available_for_session"] = compute_available_for_session(
          news["published_at_utc"], md.dates
      )
      fake = _FakeClient(responses=[_resp_text('{"VCB":0.2,"FPT":0.2,"HPG":0.2,"VIC":0.2,"VNM":0.1}')])
      agent = SingleAgenticTrader(md, news, client=fake,
                                  audit_log_path=tmp_path / "a.jsonl")
      obs = np.zeros(56, dtype=np.float32)
      agent.decide(obs, _info(md.dates[10].isoformat()))
      user_msg = fake.calls[0]["messages"][1]["content"]
      assert "Recent news" not in user_msg
      assert "VCB earnings" not in user_msg


  def test_weekly_rebalance_false_calls_llm_every_step(synthetic_market_data, tmp_path):
      """Ablation: disable weekly cache → every decide() calls the LLM."""
      fake = _FakeClient(responses=[
          _resp_text('{"VCB":0.2,"FPT":0.2,"HPG":0.2,"VIC":0.2,"VNM":0.1}')
          for _ in range(3)
      ])
      agent = SingleAgenticTrader(
          synthetic_market_data, pd.DataFrame(),
          client=fake, weekly_rebalance=False,
          audit_log_path=tmp_path / "a.jsonl",
      )
      obs = np.zeros(56, dtype=np.float32)
      for i in range(3):
          agent.decide(obs, _info(synthetic_market_data.dates[i].isoformat()))
      assert len(fake.calls) == 3
  ```
- **PATTERN:** `tests/test_zero_shot.py` for `_FakeClient`/`_info` shape;
  extend with `_resp_tools` + `_tool_call` builders for new turn shapes.
- **GOTCHA #1:** `audit_log_path=tmp_path / "audit.jsonl"` in EVERY test
  that doesn't explicitly test the disabled path. Forgetting pollutes
  the real `results/single_agentic/`.
- **GOTCHA #2:** Don't `metrics.reset()` in every test — leaks across
  tests. Only reset where the test asserts on metric counters
  (iteration_cap, network_, parse_failure).
- **GOTCHA #3:** When the LLM mock returns a parsed action that sums to
  hold-shares level (~0.9 from `_info` defaults), assertions like
  `a.sum() > 0.5` distinguish hold-shares (~0.95) from a zero action
  (panic-sell signal).
- **GOTCHA #4:** `_FakeClient` consumes responses from the front; queue
  in the order calls fire. For looped tool tests, queue tool-call
  response(s) BEFORE the terminal text response.
- **VALIDATE:**
  ```bash
  .venv/bin/pytest tests/test_single_agentic.py -v
  # Expected: ~12 tests pass (10 listed + room for 1-2 you may add)
  ```

### 4. CREATE `scripts/run_single_agentic.py`

- **IMPLEMENT:**
  ```python
  """CLI: run SingleAgenticTrader backtest on a split (default test).

  Writes results/single_agentic/{portfolio_curve,holdings}.parquet +
  tool_calls.jsonl. Prints metrics snapshot + agent-specific stats
  (avg iterations, hallucination_rate from audit log).

  Usage:
      .venv/bin/python scripts/run_single_agentic.py                     # full test
      .venv/bin/python scripts/run_single_agentic.py --n-sessions 10     # smoke
      .venv/bin/python scripts/run_single_agentic.py --model gpt-4o      # upgrade
  """

  from __future__ import annotations

  import argparse
  import json
  import logging
  import sys
  from pathlib import Path

  import pandas as pd

  from src import config
  from src.agent_base import BacktestResult
  from src.baselines import _records_to_frames, _snapshot
  from src.env_data_loader import load_market_data
  from src.llm import metrics
  from src.llm.single_agentic import SingleAgenticTrader
  from src.trading_env import VNTradingEnv

  RESULTS_DIR = config.PROJECT_ROOT / "results" / "single_agentic"
  AUDIT_PATH = RESULTS_DIR / "tool_calls.jsonl"
  NEWS_PATH = config.PROJECT_ROOT / "data" / "processed" / "news.parquet"


  def main() -> int:
      logging.basicConfig(
          level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
      )
      p = argparse.ArgumentParser()
      p.add_argument("--split", default="test",
                     choices=["train", "val", "test", "full"])
      p.add_argument("--model", default="gpt-4o-mini",
                     choices=sorted(config.LLM_ALLOWED_MODELS))
      p.add_argument("--seed", type=int, default=42)
      p.add_argument("--max-iterations", type=int, default=10)
      p.add_argument("--n-sessions", type=int, default=None,
                     help="Smoke cap; default = full split")
      p.add_argument("--reset-audit", action="store_true",
                     help="Delete existing audit log before running")
      args = p.parse_args()

      if args.reset_audit and AUDIT_PATH.exists():
          AUDIT_PATH.unlink()

      md = load_market_data(args.split)
      news = pd.read_parquet(NEWS_PATH) if NEWS_PATH.exists() else pd.DataFrame()
      print(f"split={args.split}  sessions={len(md.dates)}  "
            f"news_rows={len(news)}  model={args.model}  "
            f"max_iter={args.max_iterations}")

      metrics.reset()
      env = VNTradingEnv(md)
      agent = SingleAgenticTrader(
          market_data=md, news_data=news, model=args.model,
          max_iterations=args.max_iterations, audit_log_path=AUDIT_PATH,
      )
      result = (_run_n(env, agent, args.seed, args.n_sessions)
                if args.n_sessions
                else _run_full(env, agent, args.seed))
      _write(result)

      snap = metrics.get_snapshot()
      cum = result.final_pv / float(config.INITIAL_CAPITAL) - 1
      print("\n=== Backtest summary ===")
      print(f"agent:           {result.agent_name}")
      print(f"steps:           {result.n_steps}")
      print(f"final pv:        {result.final_pv:,.0f} VND")
      print(f"cum return:      {cum:+.2%}")
      print(f"LLM calls:       {snap['llm_calls']}")
      print(f"by model:        {snap['by_model']}")
      print(f"prompt tokens:   {snap['total_prompt_tokens']:,} "
            f"(cached {snap['total_cached_tokens']:,})")
      print(f"completion:      {snap['total_completion_tokens']:,}")
      print(f"est cost:        ${snap['estimated_cost_usd']:.4f}")
      print(f"parse success:   {snap['parse_success']}")
      print(f"parse failure:   {snap['parse_failure']} "
            f"({snap['parse_failure_rate']:.1%})")
      if snap["parse_failure_reasons"]:
          print(f"failure reasons: {snap['parse_failure_reasons']}")
      _print_audit_summary()
      return 0


  def _print_audit_summary() -> None:
      """Per-decision summary from audit log: avg iterations, hallucination_rate."""
      if not AUDIT_PATH.exists():
          return
      lines = AUDIT_PATH.read_text(encoding="utf-8").splitlines()
      recs = [json.loads(ln) for ln in lines]
      decisions = [r for r in recs if r.get("event") == "decision"]
      iters = [r for r in recs if r.get("event") == "iteration"]
      tc_all = [tc for r in iters for tc in r["tool_calls"]]
      tc_errored = [tc for tc in tc_all if tc.get("errored")]
      caps = sum(1 for d in decisions if d.get("cap_hit"))
      print(f"\n=== Audit summary ===")
      print(f"decisions:         {len(decisions)}")
      print(f"avg iterations:    "
            f"{sum(d['iterations_used'] for d in decisions) / max(len(decisions), 1):.2f}")
      print(f"cap-hit decisions: {caps}")
      print(f"total tool calls:  {len(tc_all)}")
      print(f"tool errors:       {len(tc_errored)} "
            f"({len(tc_errored) / max(len(tc_all), 1):.1%} hallucination rate)")


  def _run_full(env: VNTradingEnv, agent: SingleAgenticTrader, seed: int) -> BacktestResult:
      from src.baselines import run_backtest
      return run_backtest(env, agent, seed=seed)


  def _run_n(env: VNTradingEnv, agent: SingleAgenticTrader, seed: int, n: int) -> BacktestResult:
      obs, info = env.reset(seed=seed)
      records: list[dict] = [_snapshot(env, info)]
      total_r, steps = 0.0, 0
      while not env._terminated and steps < n:
          action = agent.decide(obs, info)
          obs, r, term, trunc, info = env.step(action)
          total_r += r
          steps += 1
          records.append(_snapshot(env, info))
      pv_df, h_df = _records_to_frames(records, agent.name)
      return BacktestResult(
          agent_name=agent.name,
          portfolio_curve=pv_df, holdings_curve=h_df,
          total_log_return=total_r,
          final_pv=float(info["portfolio_value"]),
          n_steps=steps, seed=seed,
      )


  def _write(result: BacktestResult) -> None:
      RESULTS_DIR.mkdir(parents=True, exist_ok=True)
      result.portfolio_curve.to_parquet(
          RESULTS_DIR / "portfolio_curve.parquet",
          engine="pyarrow", compression="snappy",
      )
      result.holdings_curve.to_parquet(
          RESULTS_DIR / "holdings.parquet",
          engine="pyarrow", compression="snappy",
      )


  if __name__ == "__main__":
      sys.exit(main())
  ```
- **PATTERN:** Mirror `scripts/run_zero_shot.py` 1:1 — only differences
  are agent class, results dir, audit summary block, `--max-iterations`
  flag, `--reset-audit` flag.
- **GOTCHA:** Audit log APPENDS across runs. Use `--reset-audit` before
  a fresh run, or downstream stats double-count.
- **VALIDATE:**
  ```bash
  unset OPENAI_API_KEY
  .venv/bin/python scripts/run_single_agentic.py --split test --n-sessions 1 2>&1 | head -5
  # Expected: RuntimeError "OPENAI_API_KEY not set"
  ```

### 5. REAL-CALL SMOKE (optional, gated)

- **IMPLEMENT:** Manual run after `.env` has valid `OPENAI_API_KEY`:
  ```bash
  .venv/bin/python scripts/run_single_agentic.py --split test --n-sessions 10 --reset-audit
  ```
- **PATTERN:** Don't add to pytest — costs real money. Capture output in
  PR description.
- **VALIDATE:** Output shows: 10 steps, ≥ 1 LLM call (first week), at
  least 1 tool dispatched, cost < $0.20, parse_success ≥ 1, audit log
  contains both iteration + decision records, no Python tracebacks.

---

## TESTING STRATEGY

### Unit Tests (~12 new in `tests/test_single_agentic.py`)

| # | Test | Verifies |
|---|------|----------|
| 1 | `test_protocol_runtime_check` | `isinstance(.., Agent)` + name |
| 2 | `test_zero_tool_calls_emits_weights_immediately` | LLM may skip tools entirely |
| 3 | `test_tool_loop_dispatches_and_continues` | wire shape + tool_call_id roundtrip |
| 4 | `test_iteration_cap_enforced` | hard cap ≤ max_iterations LLM calls |
| 5 | `test_tool_dispatch_error_fed_back_to_llm` | ValueError → error tool result, loop continues |
| 6 | `test_weekly_cache_skips_llm_within_same_week` | weekly cadence respected |
| 7 | `test_iso_week_change_triggers_new_decision` | new week → new call |
| 8 | `test_parse_failure_falls_back_to_hold_shares` | malformed text → hold-shares |
| 9 | `test_network_failure_falls_back_to_hold_shares` | RuntimeError → hold-shares + metric |
| 10 | `test_audit_log_contains_decision_summary` | JSONL has iteration + decision rows |
| 11 | `test_audit_log_can_be_disabled` | `audit_log_path=None` → no writes |
| 12 | `test_news_not_pre_injected_into_user_message` | LLM fetches news via tool |
| 13 | `test_weekly_rebalance_false_calls_llm_every_step` | ablation toggle |

Total after PKG-7: **126 (current) + 13 = 139 tests** (PKG-6 may have
added 1 more beyond plan; rerun count post-impl).

### Integration smoke (manual, in PR description)

`scripts/run_single_agentic.py --split test --n-sessions 10 --reset-audit`
with real `OPENAI_API_KEY`. Capture:

- LLM calls count (5–25 in 10-session smoke depending on tool use)
- Cost USD (< $0.20)
- parse_success / parse_failure
- Avg iterations per decision (1–5 expected for gpt-4o-mini)
- Hallucination rate (0% expected on smoke; real signal across full backtest)

### Edge Cases Explicitly Covered

| # | Edge case | Test |
|---|-----------|------|
| 1 | LLM responds with text on turn 0 (no tools used) | #2 |
| 2 | LLM keeps tooling forever | #4 |
| 3 | LLM hallucinates a tool name | #5 |
| 4 | LLM provides bad ticker enum (caught by `LookaheadSafeTools._ticker_idx`) | covered by #5's catch path |
| 5 | Mid-loop network failure (e.g., rate-limit after retries) | #9 |
| 6 | Empty news dataframe | implicit in `_build_user_message` (state_to_text handles) |
| 7 | Concurrent decide() within same week | #6 |
| 8 | Same agent across multiple ISO weeks | #7 |
| 9 | Audit log path missing parent dir | covered by `_write_audit` `mkdir(parents=True)` |
| 10 | Audit log disabled | #11 |

### Edge Cases NOT Covered (deferred)

- **Real OpenAI auto-cache hit rate across iterations** — verify in
  real-call smoke; structural growth of `messages` means only the prefix
  (system + first user) caches. Documented, not tested.
- **Cost ceiling enforcement** — PKG-10 may add hard cap; PKG-7 just
  surfaces snapshot.
- **Tool argument validation beyond enum** — OpenAI rejects most
  off-spec args before they reach us; `dispatch` is the second line.

---

## VALIDATION COMMANDS

### Level 1: Syntax & Style

```bash
.venv/bin/ruff check src/ tests/ scripts/
.venv/bin/ruff format --check src/llm/single_agentic.py tests/test_single_agentic.py scripts/run_single_agentic.py
```

### Level 2: Unit Tests

```bash
.venv/bin/pytest tests/test_single_agentic.py -v
# Expected: ~12-13 tests pass

.venv/bin/pytest tests/ -v
# Expected: ~139 tests pass overall (count both new + prior)
```

### Level 3: Regression (no PKG-6 zero-shot tests broken)

```bash
.venv/bin/pytest tests/test_zero_shot.py tests/test_llm_*.py tests/test_baselines.py tests/test_trading_env.py -v
# Expected: all prior tests pass; no shared mutable state leaks (especially
# the metrics singleton — reset only at start of each test that needs it).
```

### Level 4: CLI mocked smoke (no API key)

```bash
unset OPENAI_API_KEY
.venv/bin/python scripts/run_single_agentic.py --split test --n-sessions 1 2>&1 | head -5
# Expected: RuntimeError "OPENAI_API_KEY not set" from OpenAIClient init
```

### Level 5: Real-call smoke (gated, ~$0.05–$0.15)

```bash
.venv/bin/python scripts/run_single_agentic.py --split test --n-sessions 10 --reset-audit
# Expected: completes, prints LLM calls + cost + audit summary
cat results/single_agentic/tool_calls.jsonl | wc -l
# Expected: ≥ 3 lines (≥ 1 iteration + 1 decision per LLM week-trigger)
```

### Level 6: Audit-log invariant spot-check

```bash
.venv/bin/python <<'PY'
import json, pathlib
p = pathlib.Path("results/single_agentic/tool_calls.jsonl")
if not p.exists():
    print("SKIP — run smoke first")
else:
    recs = [json.loads(l) for l in p.read_text().splitlines()]
    decisions = [r for r in recs if r.get("event") == "decision"]
    # Issue #8 acceptance: no decision > 10 tool calls
    assert all(d["iterations_used"] <= 10 for d in decisions), \
        f"BUG: cap violated: {[d for d in decisions if d['iterations_used'] > 10]}"
    print(f"OK — {len(decisions)} decisions, max iters = "
          f"{max((d['iterations_used'] for d in decisions), default=0)}")
PY
```

---

## ACCEPTANCE CRITERIA

Mirrors GitHub Issue #8:

- [ ] **Audit log file `results/single_agentic/tool_calls.jsonl` ghi đủ
  mọi call** — verified by test #10 + Level 6 spot-check on real run
- [ ] **Iteration cap enforced — không decision nào > 10 tool calls** —
  verified by test #4 (cap=3) + Level 6 assertion on real run
- [ ] `SingleAgenticTrader` implements `Agent` Protocol (test #1)
- [ ] Weekly cadence preserved (tests #6, #7)
- [ ] Tool dispatch errors don't crash backtest (test #5)
- [ ] Parse / network failures fall back to hold-shares (tests #8, #9)
- [ ] All 12-13 new tests pass + 126 prior tests still pass; ruff clean
- [ ] PR description includes real-call smoke output (≤ 10 sessions) if
  `OPENAI_API_KEY` available locally
- [ ] CLI writes 2 parquets + 1 JSONL to `results/single_agentic/`

---

## COMPLETION CHECKLIST

- [ ] Spike A (ChatResult round-trip) executed; assistant-message shape
      verified before coding the loop
- [ ] Spike B (dispatch ValueError) executed; error path confirmed
- [ ] `src/llm/prompts/single_agentic.md` written (Vietnamese, ≥ 4000 chars)
- [ ] `src/llm/single_agentic.py` written; imports clean;
      `name == "single_agentic"`; Protocol satisfied
- [ ] `tests/test_single_agentic.py` ~12-13 tests pass
- [ ] `scripts/run_single_agentic.py` mocked smoke (no key) errors loud
- [ ] Real-call smoke captured (if `OPENAI_API_KEY` set)
- [ ] PR open with title `PKG-7: Single-LLM Agentic Trader`,
      body `Closes #8`
- [ ] PKG-8 unblocked (multi-agent will reuse `_assistant_message` +
      tool-dispatch error pattern)
- [ ] Issue #8 acceptance criteria checked off; CLAUDE.md commit
      attribution rules followed (no AI co-author trailer)

---

## NOTES

### Design decisions worth flagging in PR

1. **`_assistant_message` JSON-encodes `arguments`** — `ChatResult` exposes
   them as dicts (decoded by `_to_result`), but OpenAI wire format wants
   strings. Easy-to-miss; spike A locks the gotcha.
2. **Tool dispatch error → JSON error string, not exception** — lets LLM
   self-correct mid-decision. Single-most-important safety property for
   not crashing 248 sessions.
3. **Iteration cap = 10 (hard)**, terminated by structural check
   (`while iterations_used < self.max_iterations`), not by trusting LLM
   to `stop`. Cap fires `iteration_cap` metric + hold-shares fallback.
4. **News NOT pre-injected** (differs from PKG-6) — LLM uses `get_news`
   tool. Forces tool use, which is the point of the agent type.
5. **Audit log = JSONL** — append-only, crash-tolerant, easy to grep
   ("which decisions had cap_hit?").
6. **Re-export `_hold_shares_action` from parser** — same as PKG-6;
   acceptable same-package private import.
7. **No code shared between `zero_shot.py` and `single_agentic.py`** —
   intentional. The 30-line overlap (`_is_rebalance_day`, `_build_user_message`
   shell, fallback handling) is small enough that DRY would couple the
   two modules through a shared utility, blocking PKG-8 from copying
   either freely.

### Risks specific to PKG-7

| # | Risk | Mitigation |
|---|------|-----------|
| 1 | Mid-loop message shape bug → OpenAI 400 every call → full backtest fails | Spike A + test #3 verify wire shape on first call; mocked tests cover dispatch round-trip |
| 2 | LLM hallucinates tools every turn → cap fires often, no actual signal | Strong prompt with tool-usage guidance + explicit "AT MOST a handful of rounds"; audit log shows tool_name_counts so PKG-10 can flag |
| 3 | Cost blow-up (e.g. 15 iter/decision × 51 weeks × gpt-4o = $50+) | Default model gpt-4o-mini; cap = 10; cost ceiling visible in metrics snapshot; --reset-audit + smoke first |
| 4 | Audit log path on macOS/Windows path conflicts (project is WSL2-only but…) | `pathlib.Path` everywhere; `mkdir(parents=True, exist_ok=True)` |
| 5 | `messages` grows unbounded in pathological tool loops → token-cost spike | Cap = 10 bounds iterations; total prompt tokens grow ~linearly with iterations; auditable in `usage` per row |
| 6 | Real gpt-4o-mini refuses to make stock recommendations | Prompt explicitly frames as "academic backtest, not advice" (same disclaimer as PKG-6); if persistent, switch to gpt-4o for real run |
| 7 | Tests double-count `metrics` because they don't `reset()` | Documented in test gotchas; reset only where assertions depend on counters |

### Khi gặp blocker

- OpenAI 400 "tool_call_id mismatch" → check `_assistant_message`:
  IDs from `tc["id"]` must round-trip exactly; do not regenerate
- OpenAI 400 "expected string in arguments" → forgot to `json.dumps` the
  `arguments` dict back to string
- LLM keeps emitting tool_calls past iteration 5 in real run → tighten
  prompt section "Quy trình ra quyết định" to be more directive
- Audit log empty after smoke → check `audit_log_path` is set (default
  is `_DEFAULT_AUDIT_PATH`, not `None`); check write permissions on
  `results/`
- Test #4 passes locally but PR CI fails with "cap not enforced" → check
  for response-queue starvation: if `_FakeClient.responses` runs out
  before cap, you get RuntimeError instead of cap-hit. Queue ≥ cap
  responses in the test.
- Cost > $2 on full backtest → check avg iterations per decision in
  audit summary; if > 7, tighten prompt or lower cap to 7
- `parse_failure_rate > 5%` on real run → typically the LLM is wrapping
  weights in prose instead of pure JSON — strengthen the example block
  in prompt section "Định dạng phản hồi"

### Phase 2 status after PKG-7

| PKG | Status |
|-----|--------|
| PKG-5 LLM core | ✅ merged |
| PKG-6 zero-shot | ✅ merged |
| **PKG-7 single-agentic (this PR)** | 🟡 ready after impl |
| PKG-8 multi-agent | unblocked; can reuse `_assistant_message` + tool-error pattern |
| PKG-9 DDPG | unblocked, independent track |
| PKG-10 backtest engine | needs ≥ PKG-7 + PKG-9 to have agents to compare |

---

## Confidence Score

**7.5/10** for one-pass implementation.

Subtract:
- −0.5 OpenAI wire shape reconstruction is the riskiest piece;
  spike A covers it but the first real call will reveal any oversight
- −0.5 audit log shape may need iteration to be PKG-10-friendly
  (metrics aggregation might want different fields)
- −0.5 prompt iteration: forcing the LLM to use tools well takes 1-2
  prompt edits in practice
- −0.5 real-call cost variance: gpt-4o-mini sometimes loops more than
  expected on first prompts; may need cap tuning

Add back:
- +1.0 PKG-5 (`OpenAIClient`, `LookaheadSafeTools`, `parser`, `metrics`)
  is rock-solid foundation
- +0.5 PKG-6 weekly-cadence + fallback patterns transfer directly
- +0.5 Spikes A + B catch the two riskiest pieces before main code

PKG-7 is genuinely ½-day work given PKG-5/6 infrastructure. The hour-long
risk is the wire shape reconstruction; the rest is glue.
