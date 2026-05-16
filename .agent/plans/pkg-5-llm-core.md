# Feature: PKG-5 — LLM core (client + tools + serialize + parser + fundamentals)

> Foundation cho 3 LLM agents (PKG-6 zero-shot, PKG-7 single-agentic, PKG-8
> multi-agent). Phải lock contract trước khi 3 PKG kia chạy song song.
> Bake **model whitelist** + **lookahead invariant** ở layer này — nếu sai,
> mọi LLM agent sai theo.

## Feature Description

5 module Python tạo lớp shared cho mọi LLM agent:

1. **`src/llm/client.py`** — wrapper OpenAI SDK 2.x: `chat.completions.create()`
   với model whitelist (raise on non-whitelisted), exp backoff retry, return
   `(text, usage)` tuple, structured tool-use support.
2. **`src/llm/tools.py`** — `LookaheadSafeTools` class với 4 methods (`get_price_history`,
   `get_indicators`, `get_news`, `get_fundamentals`) + static helper to emit
   OpenAI tool-spec JSON. Class injects `(market_data, news_data, asof_session)`
   tại construction; lookahead bake qua `window_until` / `visible_news_at`.
3. **`src/llm/serialize.py`** — `state_to_text(env_info)`, `news_to_bullets(news_df)`,
   `holdings_to_text(holdings, prices)` — markdown bullet output cho zero-shot.
4. **`src/llm/parser.py`** — `parse_weights_json(text, info, ticker_order) ->
   np.ndarray`, robust JSON extraction từ LLM markdown response, fallback
   "hold-shares" khi malformed (không panic-sell), log to metrics.
5. **`src/llm/metrics.py`** — module-level counter cho parse_failure_rate,
   llm_call_count, total_tokens, cost_estimate. PKG-10 aggregate.
6. **`src/data_pipeline/vnstock_fundamentals.py`** — moved from PKG-1 per scope
   shift. `fetch_fundamentals(ticker)` returns 4-quarter snapshot (income +
   balance + ratio merged), file-cached 7-day TTL.

## User Story

As a **PKG-6 zero-shot trader** / **PKG-7 single-agentic trader** /
**PKG-8 multi-agent role**
I want to **call `client.chat(messages, model)` mà không cần biết model whitelist
hay retry** + **dùng `tools.get_news(D, ticker)` mà không lo lookahead leak**
+ **parse weights từ LLM output mà không crash khi LLM trả markdown text**
So that **focus vào prompt design + agent logic, lớp dưới đã enforce invariants**.

As a **Person 2 (verifier)**
I want to **kiểm tra duy nhất 1 module `tools.py`** để verify "không LLM agent
nào leak future data"
So that **không phải audit từng prompt × từng tool call trong PKG-6/7/8**.

## Problem Statement

3 vấn đề độc lập:

1. **OpenAI SDK 2.x API surface lớn** (Chat Completions, Responses API,
   tool-use, streaming, structured output). Không lock primary path → mỗi
   LLM agent reinvent wheel.
2. **Lookahead leak qua tool call là silent killer**. LLM tự gọi
   `get_news("2025-08-04", "VCB")` — nếu tool trả news từ 2025-08-04 cùng ngày
   (chưa qua D+1 close), agent leak future. PKG-2 đã bake `available_for_session`,
   PKG-5 phải route 100% tool access qua đó.
3. **Model lock mong manh** — dev có thể accidentally pass `model="gpt-5"` để
   "test xem nhanh hơn không" → leak future knowledge (cutoff sau Oct 2023).
   Whitelist phải là `ValueError`, không log warning.

## Solution Statement

7 design decisions LOCK trước khi code (xem §"DESIGN DECISIONS"):

- D1. OpenAI **Chat Completions** API (`client.chat.completions.create`), không
  Responses API.
- D2. **Auto prompt caching** — OpenAI cache prompts > 1024 tokens automatic;
  put system prompt FIRST + keep stable. Không cần `cache_control` (đó là
  Anthropic).
- D3. **`LookaheadSafeTools` class** với context injected at construction.
  4 instance methods + 1 classmethod `tool_specs()` returning OpenAI JSON specs.
- D4. **Fundamentals = file cache 7-day TTL**, CLI `--refresh` force.
- D5. **Parser fallback = current portfolio weights** (hold-shares) using
  `info["holdings"] × info["close_t"] / pv`. Avoids panic-sell on parse fail.
- D6. **State serialization = markdown bullets** (compact, LLM-friendly).
- D7. **Metrics = module-level singleton counter** in `src/llm/metrics.py`,
  exposed via `get_snapshot()` and `reset()`.

## Feature Metadata

- **Feature Type:** New Capability (foundation cho 3 LLM agents)
- **Estimated Complexity:** **High** — 6 files, OpenAI SDK + vnstock both
  external, lookahead invariant bake, parser robustness, fundamentals scope
  shift integration
- **Primary Systems Affected:** `src/llm/{client,tools,serialize,parser,metrics}.py`,
  `src/data_pipeline/vnstock_fundamentals.py`, `tests/test_llm_*.py`,
  `data/raw/fundamentals_cache/` (gitignored)
- **Dependencies:** `openai>=1.30` (installed v2.36.0), `vnstock>=4.0` (installed),
  `pandas`. Không cần thêm dep mới.

---

## CONTEXT REFERENCES

### Relevant Codebase Files — ĐỌC TRƯỚC KHI IMPLEMENT

**Reuse bắt buộc (không re-implement):**
- `src/config.py` (line 65-68): `LLM_MODEL_PRIMARY="gpt-4o"`,
  `LLM_MODEL_MINI="gpt-4o-mini"`, `LLM_ALLOWED_MODELS=frozenset(...)`,
  `OPENAI_API_KEY=os.getenv(...)`. Whitelist source of truth.
- `src/data_pipeline/calendar.py` — `window_until(df, asof, date_col)` strict `<`.
  Mọi tool data-window slicing routes qua đây.
- `src/data_pipeline/news_align.py` — `visible_news_at(news_df, asof_session)`
  `<=` semantics (already accounts for D+2 lag). `NEWS_SCHEMA` constant.
- `src/env_data_loader.py` — `MarketData` frozen dataclass shape (dates,
  tickers, close, indicators_norm, warmup_offset). Tools accept this.
- `src/data_pipeline/indicators.py` — `INDICATOR_COLS` tuple cho tool output
  schema.

**Pattern bắt buộc mirror:**
- `src/data_pipeline/vnstock_prices.py:1-15` (module docstring shape +
  deprecation notes)
- `src/data_pipeline/vnstock_prices.py:30-49` (KBS→VCI fallback chain pattern,
  reuse cho fundamentals API call)
- `src/data_pipeline/news_fetch.py:1-13` (fundamentals will mirror this — VCI
  source, no fallback because KBS broken for finance)
- `tests/test_news_fetch.py` (monkeypatch external library Class pattern)
- `tests/test_news_align.py:60-70` (timezone math invariant test pattern)

**Read-only context (don't modify):**
- `CLAUDE.md` §"Domain-Specific Rules" §2 (LLM model lock — `ValueError` if
  bypass attempt)
- `CLAUDE.md` §"Domain-Specific Rules" §1 (lookahead invariant, news D
  visible from D+1 close)
- `CLAUDE.md` §"Error handling" — LLM parse failure → fallback hold + log,
  never crash backtest
- `.agent/PRD.md` §7 Feature 4-6 (LLM agent shapes)
- `.agent/PRD.md` §8 LLM SDK row (model whitelist)
- `.agent/TASKS.md` PKG-5 + scope shift note (fundamentals moved from PKG-1)

**Don't touch (file ownership):**
- `src/llm/zero_shot.py` — PKG-6
- `src/llm/single_agentic.py` — PKG-7
- `src/llm/multi_agent/*` — PKG-8
- `src/agents/__init__.py` — PKG-S serialized
- `src/data_pipeline/{news_*,vnstock_prices,indicators,calendar}.py` — PKG-1/2

### New Files to Create

```
src/llm/
├── client.py          # OpenAIClient wrapper with whitelist + retry
├── tools.py           # LookaheadSafeTools class + tool_specs() JSON
├── serialize.py       # state_to_text, news_to_bullets, holdings_to_text
├── parser.py          # parse_weights_json + hold-shares fallback
└── metrics.py         # module-level counter singleton
src/data_pipeline/
└── vnstock_fundamentals.py   # moved from PKG-1 scope
tests/
├── test_llm_client.py
├── test_llm_tools.py
├── test_llm_serialize.py
├── test_llm_parser.py
├── test_llm_metrics.py
└── test_vnstock_fundamentals.py
data/raw/fundamentals_cache/   # gitignored (already covered by data/raw/* glob)
```

### Relevant Documentation — ĐỌC TRƯỚC KHI IMPLEMENT

- **OpenAI Python SDK Chat Completions:** https://platform.openai.com/docs/api-reference/chat/create
  - `client.chat.completions.create(model, messages, tools=[...], tool_choice="auto"|"required"|{...})`
  - Returns `ChatCompletion` object with `.choices[0].message.{content, tool_calls}`,
    `.usage.{prompt_tokens, completion_tokens, total_tokens, prompt_tokens_details.cached_tokens}`
- **OpenAI prompt caching (auto):** https://platform.openai.com/docs/guides/prompt-caching
  - Triggered automatically for prompts > 1024 tokens
  - Cache hit shown via `usage.prompt_tokens_details.cached_tokens`
  - Best practice: stable system prompt FIRST, dynamic content LAST
- **OpenAI tool-use (function calling):** https://platform.openai.com/docs/guides/function-calling
  - Tool spec: `{"type": "function", "function": {"name": str, "description": str, "parameters": {JSONSchema}}}`
  - Tool call response: `message.tool_calls[i].{id, function.{name, arguments}}` (arguments is JSON string!)
- **OpenAI rate limiting + retry:** SDK handles retry by default via `max_retries=2`.
  We bump to 5 with our own exp backoff for 429/500 explicitly.
- **vnstock Finance API (verified earlier):** `Finance(source="vci", symbol=t,
  period="quarter", get_all=True).{income_statement, balance_sheet, cash_flow,
  ratio}()` → 4-quarter wide format `[item, item_en, item_id, Q1, Q2, Q3, Q4]`.

### Pre-implementation spikes (chạy 3 lệnh trước khi code)

```bash
# Spike A: verify openai SDK signatures
.venv/bin/python -c "
from openai import OpenAI
import inspect
print('OpenAI:', OpenAI)
print('chat.completions.create:', inspect.signature(OpenAI.__init__))
"

# Spike B: end-to-end Finance fetch shape (1 ticker, 4 statement types)
.venv/bin/python <<'PY'
from vnstock.api.financial import Finance
f = Finance(source="vci", symbol="VCB", period="quarter", get_all=True)
inc = f.income_statement()
bs = f.balance_sheet()
cf = f.cash_flow()
print("income:", inc.shape, inc.columns.tolist()[:7])
print("balance:", bs.shape, bs.columns.tolist()[:7])
print("cash_flow:", cf.shape, cf.columns.tolist()[:7])
print("\nQuarter columns sample:")
print([c for c in inc.columns if "-Q" in c])
PY

# Spike C: parse a representative LLM-style markdown response
.venv/bin/python <<'PY'
import json, re
sample = """
Based on my analysis, here's my recommendation:

```json
{"VCB": 0.20, "FPT": 0.25, "HPG": 0.15, "VIC": 0.20, "VNM": 0.10}
```

Cash buffer: 10%
"""
# Extract first ```json ... ``` block then parse
m = re.search(r"```json\s*(\{[^`]+?\})\s*```", sample, re.DOTALL)
print("matched:", m.group(1) if m else None)
print("parsed:", json.loads(m.group(1)) if m else None)
PY
```

### Patterns to Follow (từ codebase đã land)

**Module docstring (mirror `src/trading_env.py:1-25`):**

```python
"""One-paragraph mô tả contract + invariants + external API gotchas.

Locked constants stated upfront. Reference PRD/CLAUDE.md sections + any
external SDK deprecation notes.
"""
```

**External-API wrapper with retry (mirror `src/data_pipeline/vnstock_prices.py:30-49`):**

```python
last_err: Exception | None = None
for attempt in range(max_attempts):
    try:
        result = call(...)
        return _normalize(result)
    except Exception as e:  # noqa: BLE001 — fallback chain
        log.warning("attempt %d failed: %s", attempt, e)
        last_err = e
        time.sleep(2 ** attempt)
raise RuntimeError(f"all attempts failed: {last_err}")
```

**Test invariant via monkeypatch (mirror `tests/test_news_fetch.py:74-82`):**

```python
def test_<invariant>(monkeypatch) -> None:
    """Encode WHY. Reference PRD/CLAUDE.md."""
    class _FakeOpenAI: ...
    monkeypatch.setattr("src.llm.client.OpenAI", _FakeOpenAI)
    ...
```

---

## DESIGN DECISIONS — LOCK BEFORE IMPLEMENT

### D1. OpenAI Chat Completions API, not Responses API

OpenAI SDK 2.x has both `chat.completions` (mature) and `responses` (newer,
agent-oriented). Lock **Chat Completions** because:

- 99% of OpenAI tutorials/docs use this API
- Tool-use semantics identical between the two; no benefit to switch
- Responses API has stateful conversations we don't need (we re-prompt per
  decision)

```python
# src/llm/client.py
from openai import OpenAI

class OpenAIClient:
    def __init__(self, api_key: str | None = None) -> None:
        self._client = OpenAI(api_key=api_key or config.OPENAI_API_KEY)

    def chat(
        self, model: str, messages: list[dict],
        tools: list[dict] | None = None, tool_choice: str | dict = "auto",
        max_retries: int = 5,
    ) -> ChatResult:
        if model not in config.LLM_ALLOWED_MODELS:
            raise ValueError(f"model {model!r} not in whitelist {sorted(config.LLM_ALLOWED_MODELS)}")
        # ... retry loop with exp backoff
```

### D2. Auto prompt caching (OpenAI built-in, > 1024 tokens)

OpenAI's prompt caching kicks in automatically when prompt ≥ 1024 tokens.
Cache hit shown in `response.usage.prompt_tokens_details.cached_tokens`.

Our prompt structure (LOCK in serialize.py):

```
[SYSTEM]   <stable system prompt — same for all decisions, ~600 tokens>
[USER]     <stable preamble — task description, output schema, ~200 tokens>
           <dynamic state — date, holdings, indicators, news — variable>
```

System + preamble = ~800 tokens stable per call. Add 200 tokens of base news
context (e.g. recent macro headlines) to push over 1024 → cache hit. Document
in PR.

NO `cache_control` parameter — that's Anthropic-only. OpenAI auto.

### D3. `LookaheadSafeTools` class with injected context

PKG-6/7/8 each construct their own instance per decision:

```python
# src/llm/tools.py
class LookaheadSafeTools:
    def __init__(
        self,
        market_data: MarketData,
        news_data: pd.DataFrame,
        asof_session: pd.Timestamp,
    ) -> None:
        self._md = market_data
        self._news = news_data
        self._asof = pd.Timestamp(asof_session).normalize()

    def get_price_history(self, ticker: str, days: int = 30) -> dict: ...
    def get_indicators(self, ticker: str) -> dict: ...
    def get_news(self, date: str | None = None, ticker: str | None = None) -> list[dict]: ...
    def get_fundamentals(self, ticker: str) -> dict: ...

    @classmethod
    def tool_specs(cls) -> list[dict]:
        """Return OpenAI tool-spec JSON for all 4 methods."""
        return [...]

    def dispatch(self, name: str, arguments: dict) -> dict | list:
        """Map tool-call name + JSON arguments → instance-method call.
        Used by single-agentic + multi-agent agent loops."""
        ...
```

Lookahead bake:
- `get_price_history`: `window_until(prices_long_for_ticker, self._asof)`,
  take last `days` rows
- `get_indicators`: indicators row at `self._asof - 1` (previous trading
  session — current session's indicators not yet computed at open of T)
- `get_news`: `visible_news_at(self._news, self._asof)` filter by ticker
- `get_fundamentals`: load from cache; filter quarters with `report_date < self._asof - lag`
  where `lag = 30 days` (typical reporting lag for VN listed companies)

Alternative considered: stateless functions with `(market_data, news, asof, ...)`
as args. Rejected because OpenAI tool-call dispatch can't easily inject context
— wrapping in class is cleaner.

### D4. Fundamentals file-cache 7-day TTL + `--refresh` flag

```
data/raw/fundamentals_cache/{ticker}.parquet
  schema: [period, item, item_en, item_id, value, statement]
  long format unified across income/balance/cashflow/ratio
```

```python
# src/data_pipeline/vnstock_fundamentals.py
CACHE_TTL_DAYS = 7

def fetch_fundamentals(ticker: str, refresh: bool = False) -> pd.DataFrame:
    cache_path = CACHE_DIR / f"{ticker}.parquet"
    if not refresh and cache_path.exists():
        age_days = (time.time() - cache_path.stat().st_mtime) / 86400
        if age_days < CACHE_TTL_DAYS:
            return pd.read_parquet(cache_path)
    # Fetch + normalize + write cache
    ...
```

Cache rationale:
- Fundamentals only refresh quarterly anyway
- Backtest reruns 5 tickers × 1 fetch = 5 API calls otherwise; cache reduces to 0
- 7-day TTL forgiving — if latest quarter publishes mid-week, max 7-day staleness

### D5. Parser fallback = current portfolio weights (hold-shares), not zero

When LLM output unparseable:
- Bad: `np.zeros(5)` → env interprets as "sell everything" → massive sell fees
- Good: emit weights matching current `info["holdings"]` × `info["close_t"] / pv`
  → env sees `delta_shares = 0` → no trade

Mirrors `BuyAndHold.decide` post-init logic from PKG-4. Same precision-buffer
needed (half-lot value bumped).

```python
# src/llm/parser.py
def parse_weights_json(
    text: str, info: dict, ticker_order: list[str],
) -> tuple[np.ndarray, bool]:
    """Returns (action_weights, parse_succeeded). On failure, action = hold-shares."""
    try:
        json_blob = _extract_json(text)
        weights_dict = json.loads(json_blob)
        action = np.array([weights_dict.get(t, 0.0) for t in ticker_order], dtype=np.float32)
        record_parse_success()
        return action, True
    except (json.JSONDecodeError, ValueError, KeyError) as e:
        record_parse_failure(reason=type(e).__name__)
        return _hold_shares_action(info, ticker_order), False
```

### D6. State serialization = markdown bullets

Compact, LLM-friendly, easy to validate in tests. Example output:

```markdown
## Decision date: 2025-08-04 (Monday, session 65 of 248)

## Portfolio
- Total value: 1,025,000,000 VND
- Cash: 102,500,000 VND (10.0%)
- Holdings:
  - VCB: 320,000 shares × 53.2 VND = 17,024,000 VND (16.6%)
  - FPT: 180,000 shares × 92.1 VND = 16,578,000 VND (16.2%)
  - ...

## Recent indicators (latest session close)
| Ticker | Close | RSI(14) | MACD | SMA20 | BB_upper | BB_lower |
| VCB    | 53.2  | 58.3    | 0.42 | 52.8  | 54.1     | 51.5     |
| ...

## Recent news (last 7 days, visible to today's open decision)
- [2025-08-01 14:30] VCB: Vietcombank công bố lợi nhuận quý 2 ...
- [2025-07-30 09:00] FPT: FPT Retail chốt ngày phát hành cổ tức ...
```

JSON considered + rejected: more tokens for same content, harder for LLM to
ingest cleanly.

### D7. Metrics = module-level counter singleton

```python
# src/llm/metrics.py
_state = {
    "llm_calls": 0,
    "total_prompt_tokens": 0,
    "total_completion_tokens": 0,
    "total_cached_tokens": 0,
    "estimated_cost_usd": 0.0,
    "parse_success": 0,
    "parse_failure": 0,
    "parse_failure_reasons": collections.Counter(),
}

def record_llm_call(model, usage): ...
def record_parse_success(): ...
def record_parse_failure(reason: str): ...
def get_snapshot() -> dict: ...
def reset() -> None: ...
```

PKG-10 calls `reset()` before each backtest run, `get_snapshot()` after.
Module-level singleton acceptable for our single-process backtest workflow;
never used in concurrent setting.

Cost model: gpt-4o $2.50/1M input, $10/1M output, 50% off cached. gpt-4o-mini
$0.15/1M input, $0.60/1M output. Hardcode in metrics; document if pricing changes.

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation — client + metrics + serialize

**Goal:** OpenAI wrapper enforces model whitelist; metrics counter ready;
state serializer produces stable markdown.

**Tasks:**
- `src/llm/client.py` — `OpenAIClient.chat()` with whitelist + retry
- `src/llm/metrics.py` — counter singleton
- `src/llm/serialize.py` — markdown formatters
- `tests/test_llm_client.py`, `test_llm_metrics.py`, `test_llm_serialize.py`

### Phase 2: Tools + parser

**Goal:** LookaheadSafeTools class wraps every data access; parser robust to
LLM markdown malformations.

**Tasks:**
- `src/llm/tools.py` — class + 4 methods + `tool_specs()` + `dispatch()`
- `src/llm/parser.py` — `parse_weights_json` with hold-shares fallback
- `tests/test_llm_tools.py`, `test_llm_parser.py`

### Phase 3: Fundamentals (PKG-1 scope shift)

**Goal:** vnstock Finance API wrapper with file cache.

**Tasks:**
- `src/data_pipeline/vnstock_fundamentals.py` — fetch + normalize + cache
- `tests/test_vnstock_fundamentals.py`
- Wire into `LookaheadSafeTools.get_fundamentals()`

### Phase 4: Integration smoke

**Goal:** End-to-end smoke with mocked OpenAI; verify chat → parse → action
roundtrip works without network.

**Tasks:**
- Add to `test_llm_parser.py`: full mock-LLM-call → parser → hold-shares
  fallback test scenario

---

## STEP-BY-STEP TASKS

### 1. CREATE `src/llm/metrics.py`

- **IMPLEMENT:**
  ```python
  """LLM call + parser metrics. Module-level singleton.

  PKG-10 calls reset() before backtest, get_snapshot() after, attaches to
  backtest result. Acceptable as singleton because we run sequentially
  (1 backtest at a time, no concurrent agents in same process).
  """
  from __future__ import annotations
  import collections
  from typing import Any

  # gpt-4o $2.50/1M input + $10/1M output; cached 50% off input
  # gpt-4o-mini $0.15/1M input + $0.60/1M output; cached 50% off input
  _PRICING = {
      "gpt-4o":       {"in": 2.50e-6, "out": 10.0e-6, "cached_in": 1.25e-6},
      "gpt-4o-mini":  {"in": 0.15e-6, "out": 0.60e-6, "cached_in": 0.075e-6},
  }

  _state: dict[str, Any] = {}

  def reset() -> None:
      _state.clear()
      _state.update({
          "llm_calls": 0, "by_model": collections.Counter(),
          "total_prompt_tokens": 0, "total_completion_tokens": 0,
          "total_cached_tokens": 0, "estimated_cost_usd": 0.0,
          "parse_success": 0, "parse_failure": 0,
          "parse_failure_reasons": collections.Counter(),
      })

  def record_llm_call(model: str, usage: dict) -> None:
      _state["llm_calls"] += 1
      _state["by_model"][model] += 1
      pt = int(usage.get("prompt_tokens", 0))
      ct = int(usage.get("completion_tokens", 0))
      cached = int(usage.get("cached_tokens", 0))
      _state["total_prompt_tokens"] += pt
      _state["total_completion_tokens"] += ct
      _state["total_cached_tokens"] += cached
      if model in _PRICING:
          p = _PRICING[model]
          billable_in = max(0, pt - cached)
          _state["estimated_cost_usd"] += (
              billable_in * p["in"] + cached * p["cached_in"] + ct * p["out"]
          )

  def record_parse_success() -> None:
      _state["parse_success"] = _state.get("parse_success", 0) + 1

  def record_parse_failure(reason: str) -> None:
      _state["parse_failure"] = _state.get("parse_failure", 0) + 1
      _state["parse_failure_reasons"][reason] += 1

  def get_snapshot() -> dict:
      total = _state.get("parse_success", 0) + _state.get("parse_failure", 0)
      rate = _state.get("parse_failure", 0) / total if total else 0.0
      snap = dict(_state)
      snap["parse_failure_rate"] = rate
      snap["by_model"] = dict(_state.get("by_model", {}))
      snap["parse_failure_reasons"] = dict(_state.get("parse_failure_reasons", {}))
      return snap

  reset()  # initialize at import
  ```
- **PATTERN:** Single-file singleton. Mirror `src/config.py` module-level state.
- **GOTCHA:** Fresh module import resets state — but Python caches imports, so
  repeated imports during a backtest see the same singleton. `reset()` explicit
  to clear between runs.
- **VALIDATE:** `.venv/bin/python -c "from src.llm.metrics import record_llm_call, get_snapshot, reset; reset(); record_llm_call('gpt-4o-mini', {'prompt_tokens': 1500, 'completion_tokens': 200, 'cached_tokens': 1000}); print(get_snapshot())"`

### 2. CREATE `src/llm/client.py`

- **IMPLEMENT:**
  ```python
  """OpenAI Chat Completions wrapper with model whitelist + exp backoff retry.

  Model whitelist is enforced via ValueError — never log a warning, never
  fallback to the default. PRD §14 Risk #3: gpt-4o cutoff Oct-2023 keeps
  test period (2025-05 → 2026-04) out-of-distribution; any non-whitelisted
  model would leak future knowledge.

  Auto prompt caching kicks in for prompts > 1024 tokens. We don't pass
  cache_control (Anthropic-only); we just structure prompts so stable
  content comes first.
  """
  from __future__ import annotations
  import logging
  import time
  from dataclasses import dataclass
  from typing import Any
  from openai import OpenAI, APIError, RateLimitError, APITimeoutError
  from src import config
  from src.llm import metrics

  log = logging.getLogger(__name__)

  @dataclass(frozen=True)
  class ChatResult:
      text: str | None  # None when the response was a tool call
      tool_calls: list[dict]  # each: {id, name, arguments(parsed dict)}
      usage: dict  # prompt_tokens, completion_tokens, cached_tokens, total_tokens
      model: str
      finish_reason: str

  class OpenAIClient:
      def __init__(self, api_key: str | None = None) -> None:
          key = api_key or config.OPENAI_API_KEY
          if not key:
              raise RuntimeError(
                  "OPENAI_API_KEY not set; populate .env from .env.example"
              )
          self._client = OpenAI(api_key=key)

      def chat(
          self,
          model: str,
          messages: list[dict],
          tools: list[dict] | None = None,
          tool_choice: str | dict = "auto",
          max_retries: int = 5,
          temperature: float = 0.0,
      ) -> ChatResult:
          if model not in config.LLM_ALLOWED_MODELS:
              raise ValueError(
                  f"model {model!r} not in whitelist "
                  f"{sorted(config.LLM_ALLOWED_MODELS)} — see CLAUDE.md §2"
              )
          last_err: Exception | None = None
          for attempt in range(max_retries):
              try:
                  kwargs: dict = {"model": model, "messages": messages, "temperature": temperature}
                  if tools:
                      kwargs["tools"] = tools
                      kwargs["tool_choice"] = tool_choice
                  resp = self._client.chat.completions.create(**kwargs)
                  return self._to_result(resp, model)
              except (RateLimitError, APITimeoutError) as e:
                  wait = 2 ** attempt + 1
                  log.warning("OpenAI rate limit/timeout (attempt %d), sleeping %ds: %s", attempt, wait, e)
                  time.sleep(wait)
                  last_err = e
              except APIError as e:
                  if 500 <= getattr(e, "status_code", 0) < 600:
                      wait = 2 ** attempt
                      log.warning("OpenAI 5xx (attempt %d), retrying in %ds: %s", attempt, wait, e)
                      time.sleep(wait)
                      last_err = e
                  else:
                      raise
          raise RuntimeError(f"OpenAI call failed after {max_retries} retries: {last_err}")

      def _to_result(self, resp: Any, model: str) -> ChatResult:
          choice = resp.choices[0]
          msg = choice.message
          tool_calls = []
          for tc in (msg.tool_calls or []):
              import json as _json
              try:
                  args = _json.loads(tc.function.arguments)
              except _json.JSONDecodeError:
                  args = {"_raw": tc.function.arguments}
              tool_calls.append({"id": tc.id, "name": tc.function.name, "arguments": args})
          usage = self._extract_usage(resp.usage)
          metrics.record_llm_call(model, usage)
          return ChatResult(
              text=msg.content, tool_calls=tool_calls, usage=usage,
              model=model, finish_reason=choice.finish_reason or "",
          )

      @staticmethod
      def _extract_usage(usage: Any) -> dict:
          if usage is None:
              return {"prompt_tokens": 0, "completion_tokens": 0, "cached_tokens": 0, "total_tokens": 0}
          cached = 0
          ptd = getattr(usage, "prompt_tokens_details", None)
          if ptd is not None:
              cached = int(getattr(ptd, "cached_tokens", 0) or 0)
          return {
              "prompt_tokens": int(usage.prompt_tokens or 0),
              "completion_tokens": int(usage.completion_tokens or 0),
              "cached_tokens": cached,
              "total_tokens": int(usage.total_tokens or 0),
          }
  ```
- **PATTERN:** Mirror `src/data_pipeline/vnstock_prices.py` for retry + raise pattern.
- **GOTCHA #1:** `tool_calls` field on ChatCompletionMessage may be `None` — use `or []`.
- **GOTCHA #2:** `function.arguments` is a JSON STRING, not dict. Parse defensively.
- **GOTCHA #3:** `usage.prompt_tokens_details` may not be present in all SDK versions; getattr defensively.
- **GOTCHA #4:** Don't pass `tools` kwarg when None — some models reject empty list. Conditional add.
- **VALIDATE:** `.venv/bin/python -c "from src.llm.client import OpenAIClient; OpenAIClient.__doc__"` (just import sanity)

### 3. CREATE `tests/test_llm_client.py`

- **IMPLEMENT:** 6 tests
  - `test_model_whitelist_rejects_gpt5` — pass `model="gpt-5"` → ValueError
  - `test_model_whitelist_rejects_gpt35` — pass `model="gpt-3.5-turbo"` → ValueError
  - `test_model_whitelist_accepts_gpt4o` — happy path with mocked client
  - `test_chat_extracts_tool_calls_with_parsed_args` — mock returns tool_calls JSON string, verify parsed dict
  - `test_chat_records_usage_to_metrics` — verify record_llm_call called with prompt+completion+cached
  - `test_chat_retries_on_rate_limit_then_succeeds` — first call raises RateLimitError, second succeeds
- **PATTERN:** Monkeypatch `src.llm.client.OpenAI` with FakeClient class. Mirror
  `tests/test_news_fetch.py:74-82` style.
- **VALIDATE:** `.venv/bin/pytest tests/test_llm_client.py -v`

### 4. CREATE `src/llm/serialize.py`

- **IMPLEMENT:**
  ```python
  """Convert env state + holdings + news → markdown bullets for LLM consumption.

  Markdown format chosen over JSON: more compact, LLM parses cleanly without
  needing to escape, human-readable in transcripts.

  Stable layout — system prompt + state preamble exceed 1024 tokens to trigger
  OpenAI auto prompt cache.
  """
  from __future__ import annotations
  import pandas as pd
  from src import config
  from src.data_pipeline.indicators import INDICATOR_COLS
  from src.env_data_loader import MarketData

  def state_to_text(
      info: dict,
      market_data: MarketData,
      news_df: pd.DataFrame | None = None,
      session_idx: int | None = None,
      total_sessions: int | None = None,
  ) -> str:
      """Top-level serializer: combines portfolio + indicators + news sections."""
      parts = [
          _header(info, session_idx, total_sessions),
          holdings_to_text(info, market_data),
          indicators_to_text(info, market_data),
      ]
      if news_df is not None and not news_df.empty:
          parts.append(news_to_bullets(news_df))
      return "\n\n".join(parts)

  def _header(info, session_idx, total_sessions) -> str: ...
  def holdings_to_text(info: dict, market_data: MarketData) -> str: ...
  def indicators_to_text(info: dict, market_data: MarketData) -> str: ...
  def news_to_bullets(news_df: pd.DataFrame, max_items: int = 10) -> str: ...
  ```
  Markdown layout: see D6 example.
- **GOTCHA #1:** `news_to_bullets` must filter to `tickers` overlapping
  `config.TICKERS` (news may be tagged with multiple tickers).
- **GOTCHA #2:** Indicator table layout — pipe-separated, one row per ticker;
  LLM tokenizers handle pipe tables well.
- **VALIDATE:** Snapshot test: feed fixture state → output string → assert
  contains key sections (`## Portfolio`, `## Recent indicators`).

### 5. CREATE `tests/test_llm_serialize.py`

- **IMPLEMENT:** 4 tests
  - `test_state_to_text_contains_portfolio_section`
  - `test_state_to_text_contains_indicator_table_with_5_tickers`
  - `test_news_to_bullets_filters_max_items`
  - `test_news_to_bullets_only_includes_universe_tickers`
- **VALIDATE:** `.venv/bin/pytest tests/test_llm_serialize.py -v`

### 6. CREATE `src/data_pipeline/vnstock_fundamentals.py`

- **IMPLEMENT:**
  ```python
  """Fetch quarterly fundamentals from vnstock Finance API; file-cache 7-day TTL.

  Moved here from PKG-1 scope after Spike 2 confirmed vnstock community caps
  Finance to 4 most-recent quarters. Lookahead enforcement happens at the
  LookaheadSafeTools layer (filter quarters with report_date < asof - lag).

  Cached layout: data/raw/fundamentals_cache/{ticker}.parquet, long format
  unified across income/balance/cashflow/ratio statements.
  """
  from __future__ import annotations
  import logging, time
  from pathlib import Path
  import pandas as pd
  from vnstock.api.financial import Finance
  from src import config

  log = logging.getLogger(__name__)
  CACHE_DIR: Path = config.PROJECT_ROOT / "data" / "raw" / "fundamentals_cache"
  CACHE_TTL_DAYS: int = 7
  STATEMENTS = ("income_statement", "balance_sheet", "cash_flow", "ratio")
  _UNIFIED_SCHEMA: list[str] = [
      "ticker", "statement", "period", "item", "item_en", "item_id", "value",
  ]

  def fetch_fundamentals(ticker: str, refresh: bool = False) -> pd.DataFrame:
      """Returns long-format DataFrame _UNIFIED_SCHEMA. ~26 income + 86 balance
      + … rows × 4 quarters per ticker = ~1000 rows."""
      cache_path = CACHE_DIR / f"{ticker}.parquet"
      if not refresh and _cache_fresh(cache_path):
          return pd.read_parquet(cache_path)
      df = _fetch_live(ticker)
      CACHE_DIR.mkdir(parents=True, exist_ok=True)
      df.to_parquet(cache_path, engine="pyarrow", compression="snappy")
      return df

  def _cache_fresh(path: Path) -> bool:
      if not path.exists():
          return False
      age_days = (time.time() - path.stat().st_mtime) / 86400
      return age_days < CACHE_TTL_DAYS

  def _fetch_live(ticker: str) -> pd.DataFrame:
      fin = Finance(source="vci", symbol=ticker, period="quarter", get_all=True)
      chunks: list[pd.DataFrame] = []
      for stmt in STATEMENTS:
          method = getattr(fin, stmt)
          try:
              raw = method()
          except Exception as e:  # noqa: BLE001 — vnstock can raise diverse types
              log.warning("Finance.%s for %s failed: %s", stmt, ticker, e)
              continue
          chunks.append(_melt(raw, ticker, stmt))
      if not chunks:
          raise RuntimeError(f"all 4 statements failed for {ticker}")
      return pd.concat(chunks, ignore_index=True)[list(_UNIFIED_SCHEMA)]

  def _melt(raw: pd.DataFrame, ticker: str, statement: str) -> pd.DataFrame:
      """vnstock returns wide [item, item_en, item_id, Q1, Q2, Q3, Q4]; melt to long."""
      meta_cols = [c for c in ("item", "item_en", "item_id") if c in raw.columns]
      period_cols = [c for c in raw.columns if "-Q" in str(c)]
      if not period_cols:
          raise ValueError(f"no period columns in {statement} for {ticker}: {raw.columns.tolist()[:10]}")
      melted = raw.melt(id_vars=meta_cols, value_vars=period_cols,
                        var_name="period", value_name="value")
      melted["ticker"] = ticker
      melted["statement"] = statement
      for c in ("item", "item_en", "item_id"):
          if c not in melted.columns:
              melted[c] = pd.NA
      return melted
  ```
- **PATTERN:** Mirror `src/data_pipeline/vnstock_prices.py` schema validation
  + raise-loud-on-drift.
- **GOTCHA #1:** vnstock prints deprecation banner — accept; use `show_log=False`
  on Finance constructor if available (probably no effect on the noisy banner).
- **GOTCHA #2:** Some statement methods may fail per ticker (e.g. cash_flow
  for banks behaves oddly). Skip + warn; require ≥ 1 successful statement.
- **GOTCHA #3:** Banner won't go away — pytest captures it in test output;
  acceptable noise.
- **VALIDATE:** `.venv/bin/python -c "from src.data_pipeline.vnstock_fundamentals import fetch_fundamentals; df = fetch_fundamentals('VCB'); print(df.shape); print(df.head())"`

### 7. CREATE `tests/test_vnstock_fundamentals.py`

- **IMPLEMENT:** 4 tests (mock Finance via monkeypatch)
  - `test_unified_schema` — output cols match `_UNIFIED_SCHEMA`
  - `test_melt_handles_4_quarter_columns` — wide → long correctly
  - `test_cache_hit_skips_live_fetch` — write a stub cache file; verify Finance never called
  - `test_cache_refresh_force_calls_live` — `refresh=True` → calls Finance even if cache fresh
- **VALIDATE:** `.venv/bin/pytest tests/test_vnstock_fundamentals.py -v`

### 8. CREATE `src/llm/tools.py`

- **IMPLEMENT:**
  ```python
  """LookaheadSafeTools: 4 OpenAI-compatible tools that all consume data via
  PKG-1/2 lookahead helpers (window_until, visible_news_at).

  Single source of truth for "what info can the LLM see at decision time T".
  PKG-6/7/8 instantiate per decision with current asof_session; never bypass.
  """
  from __future__ import annotations
  from dataclasses import dataclass
  from typing import Any
  import pandas as pd
  from src import config
  from src.data_pipeline.calendar import window_until
  from src.data_pipeline.news_align import visible_news_at
  from src.data_pipeline.indicators import INDICATOR_COLS
  from src.data_pipeline.vnstock_fundamentals import fetch_fundamentals
  from src.env_data_loader import MarketData

  FUNDAMENTAL_REPORT_LAG_DAYS: int = 30  # typical VN listed-co reporting lag

  @dataclass
  class LookaheadSafeTools:
      market_data: MarketData
      news_data: pd.DataFrame
      asof_session: pd.Timestamp

      def get_price_history(self, ticker: str, days: int = 30) -> dict:
          if ticker not in self.market_data.tickers:
              raise ValueError(f"unknown ticker {ticker!r}")
          col = self.market_data.tickers.index(ticker)
          # Filter dates < asof; take last `days`
          mask = self.market_data.dates < self.asof_session
          if not mask.any():
              return {"ticker": ticker, "rows": []}
          dates = self.market_data.dates[mask][-days:]
          close = self.market_data.close[mask][-days:, col]
          high = self.market_data.high[mask][-days:, col]
          low = self.market_data.low[mask][-days:, col]
          return {
              "ticker": ticker,
              "rows": [
                  {"date": d.isoformat()[:10], "close": float(c), "high": float(h), "low": float(l)}
                  for d, c, h, l in zip(dates, close, high, low)
              ],
          }

      def get_indicators(self, ticker: str) -> dict:
          if ticker not in self.market_data.tickers:
              raise ValueError(f"unknown ticker {ticker!r}")
          col = self.market_data.tickers.index(ticker)
          mask = self.market_data.dates < self.asof_session
          if not mask.any():
              return {"ticker": ticker, "indicators": {}}
          last_idx = int(mask.cumsum()[-1] - 1)
          row = self.market_data.indicators_norm[last_idx, col, :]
          return {
              "ticker": ticker,
              "as_of_date": self.market_data.dates[last_idx].isoformat()[:10],
              "indicators": dict(zip(INDICATOR_COLS, [float(v) for v in row])),
          }

      def get_news(self, date: str | None = None, ticker: str | None = None) -> list[dict]:
          asof = pd.Timestamp(date).normalize() if date else self.asof_session
          visible = visible_news_at(self.news_data, asof)
          if ticker is not None:
              visible = visible[visible["tickers"].apply(lambda lst: ticker in lst)]
          return [
              {
                  "published_at": str(r.published_at_utc),
                  "title": r.title,
                  "tickers": list(r.tickers),
                  "url": r.url,
              }
              for r in visible.itertuples()
          ][:20]  # cap at 20 most-recent

      def get_fundamentals(self, ticker: str) -> dict:
          df = fetch_fundamentals(ticker)
          # Filter to quarters whose report_date is "visible" — approximated via
          # FUNDAMENTAL_REPORT_LAG_DAYS lag from quarter end.
          # Quarter "2025-Q2" ends 2025-06-30; visible from 2025-07-30+
          import re
          def quarter_visible(period_str: str) -> bool:
              m = re.match(r"(\d{4})-Q(\d)", str(period_str))
              if not m:
                  return False
              year, q = int(m.group(1)), int(m.group(2))
              q_end_month = q * 3
              q_end = pd.Timestamp(year=year, month=q_end_month, day=1) + pd.offsets.MonthEnd(0)
              visible_from = q_end + pd.Timedelta(days=FUNDAMENTAL_REPORT_LAG_DAYS)
              return visible_from <= self.asof_session
          visible = df[df["period"].apply(quarter_visible)]
          return {
              "ticker": ticker,
              "quarters_available": sorted(visible["period"].unique().tolist()),
              "items": [
                  {"statement": r.statement, "period": r.period, "item": r.item, "value": float(r.value) if pd.notna(r.value) else None}
                  for r in visible.itertuples()
              ][:50],  # cap at 50 most-recent items
          }

      @classmethod
      def tool_specs(cls) -> list[dict]:
          return [
              {"type": "function", "function": {
                  "name": "get_price_history",
                  "description": "Last N days of OHLC close/high/low for a ticker. Returns rows with date, close, high, low.",
                  "parameters": {"type": "object", "properties": {
                      "ticker": {"type": "string", "enum": list(config.TICKERS)},
                      "days": {"type": "integer", "minimum": 1, "maximum": 252, "default": 30},
                  }, "required": ["ticker"]},
              }},
              # ... 3 more tool specs (get_indicators, get_news, get_fundamentals)
          ]

      def dispatch(self, name: str, arguments: dict) -> dict | list:
          method = getattr(self, name, None)
          if method is None or not callable(method):
              raise ValueError(f"unknown tool {name!r}")
          return method(**arguments)
  ```
- **GOTCHA #1:** `pd.DatetimeIndex < timestamp` returns boolean array; mask.any() guard.
- **GOTCHA #2:** `visible_news_at` semantics: `<=` (already includes asof). `get_news` does NOT add another lag — that's news_align's job.
- **GOTCHA #3:** Quarter-visible date math: Q2 ends June 30, +30 days = July 30. Decision on August 1 sees Q2; on July 25 doesn't.
- **GOTCHA #4:** `dispatch` must reject unknown methods explicitly — LLM may hallucinate a tool name like `get_market_news`.
- **VALIDATE:** `.venv/bin/python -c "from src.llm.tools import LookaheadSafeTools; print(LookaheadSafeTools.tool_specs())"` (4 specs, valid JSON shape)

### 9. CREATE `tests/test_llm_tools.py`

- **IMPLEMENT:** 8 tests
  - `test_get_price_history_respects_asof` — asof = day 50; rows all have date < asof
  - `test_get_indicators_uses_last_pre_asof_session` — indicators row date < asof
  - `test_get_news_filters_by_visible_for_session` — news from D not visible at D, visible at D+2
  - `test_get_news_filters_by_ticker` — only items with `ticker in row.tickers`
  - `test_get_fundamentals_quarter_visibility_lag` — Q2 not visible on July 25; visible August 1
  - `test_dispatch_routes_to_method` — dispatch("get_price_history", {...}) calls method
  - `test_dispatch_rejects_unknown_tool` — dispatch("get_market_cap", {}) raises
  - `test_tool_specs_returns_4_valid_function_dicts` — JSON shape OK
- **PATTERN:** Use `synthetic_market_data` fixture from conftest + small synthetic news DataFrame.
- **VALIDATE:** `.venv/bin/pytest tests/test_llm_tools.py -v`

### 10. CREATE `src/llm/parser.py`

- **IMPLEMENT:**
  ```python
  """Parse LLM JSON output into action ndarray. Robust to markdown wrapping +
  malformed responses. Fallback = hold-shares (current portfolio weights),
  not zero (which would trigger panic-sell).
  """
  from __future__ import annotations
  import json
  import re
  import numpy as np
  from src import config
  from src.llm import metrics

  _JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{[^`]+?\})\s*```", re.DOTALL)
  _BARE_OBJECT_RE = re.compile(r"\{[^{}]*\}", re.DOTALL)

  def parse_weights_json(
      text: str | None,
      info: dict,
      ticker_order: list[str] | None = None,
  ) -> tuple[np.ndarray, bool]:
      """Returns (action, success). On parse failure, action = hold-shares.
      Records metric for both outcomes."""
      tickers = ticker_order or list(config.TICKERS)
      try:
          weights = _extract_weights(text, tickers)
          metrics.record_parse_success()
          return weights.astype(np.float32), True
      except (ValueError, json.JSONDecodeError, KeyError, TypeError) as e:
          metrics.record_parse_failure(reason=type(e).__name__)
          return _hold_shares_action(info, tickers), False

  def _extract_weights(text: str | None, tickers: list[str]) -> np.ndarray:
      if not text:
          raise ValueError("empty text")
      m = _JSON_BLOCK_RE.search(text)
      if m:
          obj = json.loads(m.group(1))
      else:
          # Fall back to first bare {...}
          m2 = _BARE_OBJECT_RE.search(text)
          if not m2:
              raise ValueError("no JSON object found")
          obj = json.loads(m2.group(0))
      if not isinstance(obj, dict):
          raise ValueError(f"not a dict: {obj!r}")
      weights = np.zeros(len(tickers), dtype=np.float64)
      for i, t in enumerate(tickers):
          v = obj.get(t, 0.0)
          if not isinstance(v, (int, float)):
              raise ValueError(f"weight for {t} not numeric: {v!r}")
          weights[i] = float(v)
      # Long-only clip (env will also clip, but we sanity-check here)
      weights = np.clip(weights, 0.0, 1.0)
      total = weights.sum()
      if total > 1.0:
          weights = weights / total
      return weights

  def _hold_shares_action(info: dict, tickers: list[str]) -> np.ndarray:
      """Mirror BuyAndHold post-init logic: emit weights matching current
      holdings so env sees delta_shares = 0."""
      holdings = np.asarray(info.get("holdings", [0]*len(tickers)), dtype=np.float64)
      close_t = np.asarray(info.get("close_t", [1.0]*len(tickers)), dtype=np.float64)
      pv = max(float(info.get("portfolio_value", 1.0)), 1e-8)
      buffer_shares = config.LOT_SIZE / 2.0  # absorb float32 quantization
      return (((holdings + buffer_shares) * close_t) / pv).astype(np.float32)
  ```
- **GOTCHA #1:** `text` may be `None` (when LLM responded with tool_call only). Treat as parse failure → hold.
- **GOTCHA #2:** `_BARE_OBJECT_RE` doesn't handle nested objects (no `{...}` inside). Acceptable — our schema is flat `{ticker: weight}`.
- **GOTCHA #3:** If LLM emits weights summing > 1.0, normalize (env would also do this; defensive).
- **VALIDATE:** `.venv/bin/python -c "from src.llm.parser import parse_weights_json; import numpy as np; info={'holdings':[100,200,0,0,0],'close_t':[50,60,70,80,90],'portfolio_value':1e9}; print(parse_weights_json('{\"VCB\": 0.2, \"FPT\": 0.3}', info))"`

### 11. CREATE `tests/test_llm_parser.py`

- **IMPLEMENT:** 7 tests
  - `test_parse_happy_path_json_block` — text with ```json {...}``` → correct array
  - `test_parse_happy_path_bare_object` — text with bare `{...}` → correct array
  - `test_parse_partial_dict_fills_missing_with_zero`
  - `test_parse_renormalizes_when_sum_exceeds_one`
  - `test_parse_clips_negative_weights_to_zero`
  - `test_parse_failure_returns_hold_shares` — malformed JSON → hold-shares fallback
  - `test_parse_failure_records_metric` — call → check `metrics.get_snapshot()['parse_failure']` incremented
- **VALIDATE:** `.venv/bin/pytest tests/test_llm_parser.py -v`

### 12. CREATE `tests/test_llm_metrics.py`

- **IMPLEMENT:** 4 tests
  - `test_reset_clears_state`
  - `test_record_llm_call_accumulates_tokens_and_cost`
  - `test_record_parse_failure_increments_counter_and_reasons`
  - `test_get_snapshot_computes_parse_failure_rate`
- **VALIDATE:** `.venv/bin/pytest tests/test_llm_metrics.py -v`

---

## TESTING STRATEGY

### Unit Tests (~30 new total)

| File | Tests |
|------|-------|
| `test_llm_client.py` | 6 (whitelist, retry, tool_calls, usage) |
| `test_llm_serialize.py` | 4 (sections present, ticker filter) |
| `test_llm_tools.py` | 8 (lookahead invariants, dispatch) |
| `test_llm_parser.py` | 7 (happy + 5 malformed + fallback shape) |
| `test_llm_metrics.py` | 4 (reset, accumulate, snapshot) |
| `test_vnstock_fundamentals.py` | 4 (schema, melt, cache hit/refresh) |

Total after PKG-5: 78 (PKG-0..4) + 33 = **111 tests**.

### Integration smoke (manual, in PR description)

End-to-end mocked: build LookaheadSafeTools → call `tool_specs()` → simulate
LLM tool_call → dispatch → returns sane data. NO real OpenAI call in PR
(would burn $$ and need env key). Real-call smoke deferred to PKG-6 PR
(zero-shot agent will exercise client end-to-end against gpt-4o-mini).

### Edge Cases Explicitly Covered

| # | Edge case | Test |
|---|-----------|------|
| 1 | Pass `gpt-3.5-turbo` → ValueError | `test_model_whitelist_rejects_gpt35` |
| 2 | Pass `gpt-5` (future model) → ValueError | `test_model_whitelist_rejects_gpt5` |
| 3 | Tool call args is JSON string, parse to dict | `test_chat_extracts_tool_calls_with_parsed_args` |
| 4 | Rate limit then succeed on retry | `test_chat_retries_on_rate_limit_then_succeeds` |
| 5 | Q2 fundamentals not visible until 30-day lag | `test_get_fundamentals_quarter_visibility_lag` |
| 6 | News D not visible at D, visible at D+2 | `test_get_news_filters_by_visible_for_session` |
| 7 | Malformed JSON → hold-shares fallback | `test_parse_failure_returns_hold_shares` |
| 8 | Cache hit skips network | `test_cache_hit_skips_live_fetch` |
| 9 | Unknown tool name → ValueError | `test_dispatch_rejects_unknown_tool` |
| 10 | Empty LLM text → hold-shares | covered by `test_parse_failure_returns_hold_shares` |

### Edge Cases NOT Covered (deferred)

- **Real OpenAI integration** — needs OPENAI_API_KEY + costs; deferred to PKG-6.
- **Multi-turn agent loop** — PKG-7 (single-agentic) handles iteration.
- **Streaming responses** — out of scope; sync only for backtest.
- **Cost ceiling enforcement** — metrics surface estimate; PKG-10 may add hard cap.

---

## VALIDATION COMMANDS

### Level 1: Syntax & Style

```bash
.venv/bin/ruff check src/ tests/ scripts/
.venv/bin/ruff format --check src/ tests/ scripts/
```

### Level 2: Unit Tests

```bash
.venv/bin/pytest tests/ -v
# Expected: 111 passed (78 prior + 33 new)
```

### Level 3: Smoke (no real OpenAI call)

```bash
.venv/bin/python -c "
from src.llm.client import OpenAIClient   # import succeeds
from src.llm.tools import LookaheadSafeTools
print('tool_specs count:', len(LookaheadSafeTools.tool_specs()))
"
```

### Level 4: Real fundamentals fetch (one-time per PR)

```bash
.venv/bin/python -c "
from src.data_pipeline.vnstock_fundamentals import fetch_fundamentals
df = fetch_fundamentals('VCB')
print('shape:', df.shape, 'cols:', df.columns.tolist())
print('quarters:', sorted(df['period'].unique()))
print('statements:', sorted(df['statement'].unique()))
"
ls -la data/raw/fundamentals_cache/
```

### Level 5: Regression

```bash
.venv/bin/pytest tests/test_config.py tests/test_baselines.py tests/test_trading_env.py -v
```

---

## ACCEPTANCE CRITERIA

Mirrors GitHub Issue #6 + scope shift PKG-1:

- [ ] `OpenAIClient.chat(model="gpt-3.5-turbo", ...)` → `ValueError`
- [ ] `OpenAIClient.chat(model="gpt-4o", ...)` runs (mocked) without error
- [ ] All 4 `LookaheadSafeTools` methods return data only with timestamp < asof (or via `visible_news_at`)
- [ ] `parse_weights_json` returns hold-shares ndarray on malformed input + records metric
- [ ] `fetch_fundamentals` writes 5-ticker cache files on first call, reads from cache on second
- [ ] 33 new tests pass; 111 total; ruff clean
- [ ] PR description includes Spike A-C output + 1 manual fundamentals fetch result

---

## COMPLETION CHECKLIST

- [ ] Spikes A-C run, output paste vào PR
- [ ] 6 modules trong `src/llm/` + `src/data_pipeline/vnstock_fundamentals.py` written
- [ ] 6 test files với 33 tests pass
- [ ] `ruff check` clean
- [ ] Real fundamentals fetch for 5 tickers writes cache files
- [ ] PR mở với title `PKG-5: LLM core (client + tools + parser + fundamentals)`, body `Closes #6`
- [ ] PKG-6/7/8/9 unblocked (Phase 2 parallel kickoff)

---

## NOTES

### Design decisions worth flagging in PR

1. **Chat Completions API, not Responses API** — mature, widely-documented,
   tool-use semantics identical. Won't switch unless we need stateful conversations.
2. **Auto prompt caching via OpenAI** — system prompt + preamble structured to
   exceed 1024 tokens; cache hit visible via `usage.cached_tokens`.
3. **`LookaheadSafeTools` class with injected context** — single audit point
   for Person 2; alternative stateless functions made dispatch awkward.
4. **Fundamentals 7-day file cache** — mostly stable; backtest reruns cheap.
5. **Parser fallback = hold-shares, not zero** — avoids panic-sell on parse
   fail. Mirrors BuyAndHold post-init pattern from PKG-4.
6. **Markdown bullet serialization** — token-efficient, LLM-friendly.
7. **Module-level singleton metrics** — acceptable for sequential backtest;
   PKG-10 calls `reset()` per run.

### Risks specific to PKG-5

| # | Risk | Mitigation |
|---|------|-----------|
| 1 | OpenAI SDK 2.x API surface change | Pin upper version `<3` in pyproject; mock all client tests |
| 2 | LookaheadSafeTools accidentally bypasses lookahead | Test `test_get_news_filters_by_visible_for_session` + Person 2 audit |
| 3 | Parse fallback masks LLM bug as "hold" | Metrics surface parse_failure_rate; PKG-10 alert if > 5% |
| 4 | Fundamentals cache stale during demo | `--refresh` flag in fetch script + 7-day TTL alert |
| 5 | Real OpenAI cost overrun in PKG-6+ | Estimate logged via metrics; PKG-10 surfaces total cost |
| 6 | Tool dispatch typo silently no-ops | Explicit `ValueError` on unknown tool names |
| 7 | gpt-4o tokenizer change between SDK versions | Re-verify with mock + cost calibration when SDK upgrades |

### Khi gặp blocker

- Spike B fails (Finance returns < 4 quarters) → likely ticker-specific; re-run
  for all 5 tickers; document if any below 4 quarters.
- Real fundamentals fetch (Level 4) writes corrupt parquet → check `_melt`
  schema validation; raise loud, don't cache empty.
- Test mock for OpenAI SDK doesn't satisfy ChatCompletion shape → use real
  `from openai.types.chat import ChatCompletion` for type-safe fakes.
- Prompt caching not triggered (cached_tokens=0) → prompt < 1024 tokens; pad
  system prompt with stable disclaimer text.

---

## Confidence Score

**6.5/10** for one-pass implementation.

Subtract:
- −1.5 OpenAI SDK 2.x API surface large; cache_tokens path may differ between minor versions
- −1.0 fundamentals long-format `_melt` is the second wrinkle (vnstock schema is unstable across versions)
- −0.5 lookahead math in `get_fundamentals` (quarter visibility lag) is off-by-one prone
- −0.5 markdown serializer easy to drift from LLM expectation; only verifiable when PKG-6 hits real model

Add back:
- +1.0 patterns from PKG-1/2/3/4 are well-established
- +0.5 tests cover both the whitelist + lookahead paths explicitly
- +0.5 parser hold-shares fallback uses the same pattern as PKG-4 BuyAndHold (proven)

PKG-5 is a 1-day estimate but with high coordination overhead. Recommend:
- Start with metrics (smallest) → client → serialize (simple) → tools (complex)
  → parser (depends on metrics) → fundamentals (independent)
- Fundamentals can be parallelized but file ownership is clean.
