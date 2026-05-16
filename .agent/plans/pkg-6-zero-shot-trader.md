# Feature: PKG-6 — LLM Zero-shot Trader

> First LLM agent actually calling OpenAI. Wires every PKG-5 piece (client,
> serialize, parser, metrics) into a single ``decide()``. Simple glue —
> patterns dày dạn từ PKG-1..5; nhưng đây cũng là lần đầu cost thật của
> backtest thực sự thấy được.

## Feature Description

`ZeroShotTrader` implements the Agent Protocol (`src/agent_base.py`). On a
weekly cadence (first trading day per ISO week), it:

1. Builds a markdown state snapshot via `serialize.state_to_text(info, market_data, news_data)`
2. Calls `OpenAIClient.chat(model='gpt-4o-mini', messages=[system_prompt, state_text])`
3. Parses JSON weights via `parse_weights_json(response.text, info)`
4. Caches weights; returns them
5. Non-rebalance days: returns cached weights (no LLM call → cheap)

Failure modes are tolerated quietly: parser failure → hold-shares fallback
(via parser.py); network failure after retries → caller catches, hold-shares.
Cost target ~$0.25 per 248-session backtest with gpt-4o-mini.

## User Story

As a **PKG-10 backtest runner**
I want to **construct `ZeroShotTrader(market_data, news_data, model='gpt-4o-mini')`
and pass it to `run_backtest`** without knowing anything about prompt
engineering or OpenAI internals
So that **I can compare zero-shot vs DDPG vs multi-agent on the same env**.

As a **người viết report (Person 1)**
I want to **see cost + parse_failure_rate + cumulative_return cho zero-shot
sau 1 backtest**
So that **bảng so sánh agent chi tiết hơn baselines**.

## Problem Statement

3 vấn đề:

1. **Weekly cadence** — PRD §15 says "LLM/agentic weekly". Env steps daily.
   Without caching, naive impl calls LLM 248×, costing ~$1.25 (5× budget) on
   gpt-4o-mini and ~$25 on gpt-4o (200× budget). Solution: ISO-week-change
   detection caches weights across same-week steps.
2. **Reproducibility vs randomness** — PRD §15 §5 "same seed → same trajectory".
   OpenAI temp=0 is *mostly* deterministic but not guaranteed; rerunning a
   backtest may differ on 1-2% of decisions. Document as known constraint;
   don't promise bit-exact reproducibility.
3. **Failure tolerance** — A single bad LLM response must not crash a
   248-session backtest. PKG-5 parser already falls back to hold-shares;
   network failure (after 5 retries) needs catch + hold-shares too.

## Solution Statement

7 design decisions LOCK trước khi code (§"DESIGN DECISIONS"):

- D1. **Weekly trigger = ISO week change.** `pd.Timestamp(date).isocalendar().week`
  different from `self._last_week`. First call always fires (week=None).
- D2. **System prompt locked in `src/llm/prompts/zero_shot.md`**, loaded
  at module import. Pad to ≥ 1024 tokens to trigger OpenAI auto cache.
- D3. **Tools = None** (zero-shot by definition). Single chat call per decision.
- D4. **Model default = `gpt-4o-mini`.** Cheap (~$0.005/call); upgrade
  reserved for multi-agent debate (PKG-8).
- D5. **Temperature = 0**, no `seed` param (not yet stable in SDK 2.x).
  Document residual non-determinism (~1-2% drift) as known constraint.
- D6. **Network failure after retries → hold-shares** (wrap client call in
  try/except). Mirror parser fallback semantics.
- D7. **News filtered to visible-at-asof + universe-tickers before prompt** —
  zero-shot has no `LookaheadSafeTools.get_news`; we hand-filter so the
  agent sees only news it would be allowed to consume.

## Feature Metadata

- **Feature Type:** New Capability (first LLM agent end-to-end)
- **Estimated Complexity:** **Low-Medium** — patterns established, mostly
  glue; one moderate-risk piece (prompt engineering for stable JSON output)
- **Primary Systems Affected:** `src/llm/zero_shot.py`,
  `src/llm/prompts/zero_shot.md`, `tests/test_zero_shot.py`,
  `scripts/run_zero_shot.py`, `results/zero_shot/`
- **Dependencies:** All in PKG-5; no new external deps.

---

## CONTEXT REFERENCES

### Relevant Codebase Files — ĐỌC TRƯỚC KHI IMPLEMENT

**Reuse bắt buộc:**
- `src/agent_base.py` (toàn bộ, ~50 dòng) — `Agent` Protocol contract;
  `BacktestResult` dataclass
- `src/llm/client.py` — `OpenAIClient.chat(model, messages, ...)` →
  `ChatResult`; `ChatResult.text`, `.usage`, `.finish_reason`
- `src/llm/serialize.py` — `state_to_text(info, market_data, news_df,
  session_idx?, total_sessions?)` returning markdown bullets
- `src/llm/parser.py` — `parse_weights_json(text, info, ticker_order?)` →
  `(action_ndarray, success_bool)`; on failure auto-emits hold-shares
- `src/llm/metrics.py` — `record_llm_call`, `get_snapshot()`; client already
  records, agent does not double-count
- `src/data_pipeline/news_align.py` — `visible_news_at(news_df, asof)` for
  filtering news visible to decision

**Pattern bắt buộc mirror:**
- `src/baselines.py:30-50` (`BuyAndHold`) — name attr + decide signature +
  cached weights pattern (post-init hold)
- `src/baselines.py:53-71` (`EqualWeightRebalance`) — month-change trigger;
  PKG-6 mirrors with ISO-week instead
- `tests/test_baselines.py:60-95` — Protocol runtime check + decide invariants
- `tests/test_llm_client.py:75-100` — `_FakeOpenAI` monkeypatch shape for
  mock client construction
- `scripts/run_baselines.py:30-95` — CLI orchestrator pattern (load split,
  construct agent, run_backtest, write parquet)

**Read-only context (don't modify):**
- `CLAUDE.md` §"Domain-Specific Rules" §2 (model lock — handled by client)
- `CLAUDE.md` §"Patterns" — Pluggable agent interface
- `CLAUDE.md` §"Error handling" — LLM parse failure → fallback hold + log
- `.agent/PRD.md` §7 Feature 4 (Zero-shot Trader description)
- `.agent/PRD.md` §15 (decision frequency, reproducibility)

**Don't touch (file ownership):**
- `src/llm/{client,tools,serialize,parser,metrics}.py` — PKG-5
- `src/llm/single_agentic.py` — PKG-7
- `src/llm/multi_agent/*` — PKG-8
- `src/baselines.py` — PKG-4
- `src/agents/__init__.py` — PKG-S serialized

### New Files to Create

```
src/llm/
├── zero_shot.py                # ZeroShotTrader class
└── prompts/
    └── zero_shot.md            # System prompt (Vietnamese, locked text)
scripts/
└── run_zero_shot.py            # CLI: backtest zero-shot on a split
tests/
└── test_zero_shot.py           # 8 tests
results/zero_shot/               # output artifacts (gitignored)
```

### Relevant Documentation — ĐỌC TRƯỚC KHI IMPLEMENT

- **OpenAI Chat Completions message format:**
  https://platform.openai.com/docs/api-reference/chat/create
  - `messages = [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]`
  - `temperature=0` for most-deterministic output
- **ISO week semantics:** https://en.wikipedia.org/wiki/ISO_week_date
  - `pd.Timestamp("2025-05-05").isocalendar()` → `(year=2025, week=19, weekday=1)`
  - Monday = weekday 1; trading sessions don't always fall on Monday
  - Detection: `week != self._last_week` (first trading day of new ISO week)
- **OpenAI auto prompt caching:**
  https://platform.openai.com/docs/guides/prompt-caching
  - Triggers automatically when prompt ≥ 1024 tokens
  - System prompt SHOULD be ≥ 1024 tokens of stable content

### Pre-implementation spike (1 lệnh check trước khi code)

```bash
# Spike A: verify ISO week detection across the test period
.venv/bin/python <<'PY'
import pandas as pd
from src.env_data_loader import load_market_data
md = load_market_data("test")
weeks_seen = set()
rebalance_dates = []
for d in md.dates:
    wk = pd.Timestamp(d).isocalendar().week
    yr = pd.Timestamp(d).isocalendar().year
    key = (yr, wk)
    if key not in weeks_seen:
        weeks_seen.add(key)
        rebalance_dates.append(d.date())
print(f"Total sessions: {len(md.dates)}")
print(f"ISO weeks (= rebalance count): {len(rebalance_dates)}")
print(f"First 5 rebalance dates: {rebalance_dates[:5]}")
print(f"Last 5 rebalance dates: {rebalance_dates[-5:]}")
# Expect ~52 weeks for 248-session ~ 12-month test split
PY
```

Expected: ~52 rebalance dates over 248 sessions. **This is the LLM call
budget** — confirm before committing.

### Patterns to Follow (from codebase đã land)

**Class with state + decide (mirror `src/baselines.py:53-71`):**

```python
class EqualWeightRebalance:
    name: str = "equal_weight"

    def __init__(self) -> None:
        self._last_month: int | None = None
        self._weights: np.ndarray = np.zeros(N_TICKERS, dtype=np.float32)

    def decide(self, obs, info) -> np.ndarray:
        month = pd.Timestamp(info["date"]).month
        if month != self._last_month:
            self._weights = np.full(...)
            self._last_month = month
        return self._weights.copy()
```

**Mock OpenAI in tests (mirror `tests/test_llm_client.py:_FakeOpenAI`):**

```python
# Or: instead of mocking OpenAI, mock the OpenAIClient.chat method directly
# — simpler than full SDK shape.
def test_x(monkeypatch):
    def _fake_chat(self, model, messages, **kw):
        return ChatResult(text='{"VCB": 0.2, ...}', tool_calls=[], usage={...},
                          model=model, finish_reason="stop")
    monkeypatch.setattr(OpenAIClient, "chat", _fake_chat)
```

**Error handling (CLAUDE.md):**
- LLM call exception → log + fallback hold-shares; never crash backtest
- Parser failure → already handled by parser.py
- Defensive cache copy on return: `self._weights.copy()`

---

## DESIGN DECISIONS — LOCK BEFORE IMPLEMENT

### D1. Weekly trigger = ISO week change

```python
def _is_rebalance_day(self, info: dict) -> bool:
    ts = pd.Timestamp(info["date"])
    week_key = (ts.isocalendar().year, ts.isocalendar().week)
    if week_key != self._last_week:
        self._last_week = week_key
        return True
    return False
```

ISO week = Monday-Sunday. First trading day of each week triggers; if Monday
is holiday, Tuesday triggers (first session where week_key changed). Robust
to Vietnam-specific holiday weeks.

Edge case: first call (`_last_week = None`) — any int week ≠ None → True →
initial decision fires. Same logic as `EqualWeightRebalance._last_month`.

### D2. System prompt locked in `prompts/zero_shot.md`, loaded at import

```python
# src/llm/zero_shot.py
PROMPT_PATH = Path(__file__).parent / "prompts" / "zero_shot.md"
SYSTEM_PROMPT: str = PROMPT_PATH.read_text(encoding="utf-8")
```

Static load at import — fail loud if prompt file missing. Content must be
≥ 1024 tokens (≈ 4000 chars) to trigger OpenAI auto-cache. Include:

- Role definition (Vietnamese stock trader)
- Universe spec (5 VN30 tickers)
- HOSE rules summary (±7%, lot-100, fees) so LLM understands env semantics
- News visibility rule (D+2 lag) so LLM doesn't ask for future news
- Output schema with strict JSON example
- Long disclaimer/style guidance to pad token count

### D3. Tools = None (zero-shot is text-only)

Don't pass `tools=` to `client.chat()`. LLM responds with text only. If LLM
emits a tool_call by mistake, `ChatResult.text` is None → parser sees None
→ falls back to hold-shares + records `EmptyText` parse failure.

### D4. Default model = `gpt-4o-mini`

```python
def __init__(
    self,
    market_data: MarketData,
    news_data: pd.DataFrame,
    model: str = "gpt-4o-mini",
    client: OpenAIClient | None = None,
    weekly_rebalance: bool = True,
) -> None:
    ...
```

Cost: 248 sessions × 1 LLM call/week × ~$0.005/call ≈ $0.25 per backtest.
gpt-4o would cost ~$3-5 per backtest — reserved for PKG-8 multi-agent
debate where quality matters more.

User can override: `ZeroShotTrader(..., model="gpt-4o")`. Whitelist enforced
upstream in client.

### D5. Temperature = 0, no seed

```python
result = self._client.chat(
    model=self.model,
    messages=[
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_text},
    ],
    temperature=0.0,
)
```

OpenAI temp=0 is *near-deterministic* but not bit-exact across runs.
Document trong report: "Identical seed produces ≥ 98% of decisions
identical; remaining drift from OpenAI sampling residual non-determinism".

PKG-S may add prompt-response cache (`results/llm_cache/<date>_<prompt_hash>.json`)
for true reproducibility; out of scope for PKG-6.

### D6. Network failure → hold-shares

```python
try:
    result = self._client.chat(model=self.model, messages=...)
except RuntimeError as e:
    log.warning("LLM call failed after retries: %s — falling back to hold", e)
    metrics.record_parse_failure(reason=f"network_{type(e).__name__}")
    return _hold_shares_action(info, list(self.market_data.tickers))
```

Wraps `client.chat`. Client itself already retries 5× with exp backoff; this
catch handles the final RuntimeError after all retries exhausted.

Reuse `parser._hold_shares_action` if exposed, else inline the same math
(mirror parser logic with half-lot precision buffer).

### D7. News filtered to visible + universe BEFORE prompt

```python
asof = pd.Timestamp(info["date"]).normalize()
visible = visible_news_at(self.news_data, asof)
# Universe filter: row.tickers intersects config.TICKERS
universe = set(self.market_data.tickers)
visible = visible[visible["tickers"].apply(lambda lst: bool(set(lst) & universe))]
# Trim to most recent 10 by published_at
recent = visible.sort_values("published_at_utc", ascending=False).head(10)
```

Then pass `recent` to `state_to_text` for serialization. This is where
lookahead invariant is enforced for zero-shot (no `LookaheadSafeTools.get_news`
because no tool layer).

---

## IMPLEMENTATION PLAN

### Phase 1: System prompt + module skeleton

**Goal:** Lock prompt content; load at import; define class skeleton.

**Tasks:**
- `src/llm/prompts/zero_shot.md` — Vietnamese system prompt (≥ 1024 tokens)
- `src/llm/zero_shot.py` — module docstring, imports, SYSTEM_PROMPT load,
  `ZeroShotTrader` class with `__init__` + name attr + state fields

### Phase 2: decide() flow

**Goal:** Weekly trigger → state serialize → LLM call → parse → cache.

**Tasks:**
- `_is_rebalance_day` helper using ISO week
- `decide` wires `state_to_text`, `client.chat`, `parse_weights_json`
- Network/parse failure fallback to hold-shares

### Phase 3: Tests

**Goal:** 8 mocked tests + 1 real-call smoke (gated).

**Tasks:**
- `tests/test_zero_shot.py` — mock client, weekly trigger, fallback,
  protocol conformance, prompt content sanity

### Phase 4: CLI + real smoke

**Goal:** 1-command run on test split; if OPENAI_API_KEY set, real-call
verifies end-to-end on 5 sessions; otherwise skip.

**Tasks:**
- `scripts/run_zero_shot.py` — mirror `run_baselines.py` shape, writes
  `results/zero_shot/{portfolio_curve,holdings}.parquet`
- Run smoke locally (5 sessions or 1 month subset to save cost)

---

## STEP-BY-STEP TASKS

### 1. CREATE `src/llm/prompts/zero_shot.md`

- **IMPLEMENT:** Vietnamese system prompt with these sections:
  ```markdown
  # Vai trò
  Bạn là một trader cổ phiếu chuyên nghiệp giao dịch trên thị trường
  chứng khoán Việt Nam (HOSE)...

  # Vũ trụ đầu tư
  Bạn chỉ giao dịch 5 mã VN30: VCB, FPT, HPG, VIC, VNM.

  # Quy tắc thị trường
  - Biên độ giá ±7% mỗi phiên (HOSE)
  - Lô tròn 100 cổ phiếu
  - Phí mua 0.15%, phí bán 0.25% (bao gồm thuế chuyển nhượng 0.1%)
  - Chỉ mua (long-only)

  # Quy tắc thông tin
  - Tin tức công bố ngày D chỉ khả dụng từ phiên D+1 close
  - Không suy đoán về tương lai vượt quá ngày quyết định

  # Định dạng phản hồi
  Trả về DUY NHẤT một khối JSON với weights, ví dụ:
  ```json
  {"VCB": 0.20, "FPT": 0.25, "HPG": 0.15, "VIC": 0.20, "VNM": 0.10}
  ```
  - Weights là tỷ trọng mục tiêu của mỗi mã (0.0 đến 1.0)
  - Tổng weights ≤ 1.0; phần còn lại là tiền mặt
  - Không thêm bình luận ngoài khối JSON

  # Hướng dẫn chiến lược
  ...stable disclaimer text...
  ```
- **PATTERN:** Pad to ≥ 4000 chars (~ 1024 tokens) for auto cache.
- **GOTCHA:** Vietnamese diacritics — save UTF-8 encoded. Test for byte
  count: `wc -c src/llm/prompts/zero_shot.md` ≥ 4000.
- **VALIDATE:** `wc -c src/llm/prompts/zero_shot.md` returns ≥ 4000

### 2. CREATE `src/llm/zero_shot.py`

- **IMPLEMENT:**
  ```python
  """Zero-shot LLM trader — one OpenAI chat call per ISO week.

  Reads state via PKG-5 serialize, sends single prompt, parses JSON weights.
  No tools. Cost ~$0.25/backtest with gpt-4o-mini default.

  Weekly cadence (D1 in plan): ISO week change triggers re-decide; same week
  returns cached weights so 248-session env loop fires ~52 LLM calls, not 248.
  """
  from __future__ import annotations
  import logging
  from pathlib import Path
  from typing import Optional
  import numpy as np
  import pandas as pd

  from src import config
  from src.data_pipeline.news_align import visible_news_at
  from src.env_data_loader import MarketData
  from src.llm import metrics
  from src.llm.client import OpenAIClient
  from src.llm.parser import _hold_shares_action, parse_weights_json
  from src.llm.serialize import state_to_text

  log = logging.getLogger(__name__)
  _PROMPT_PATH = Path(__file__).parent / "prompts" / "zero_shot.md"
  SYSTEM_PROMPT: str = _PROMPT_PATH.read_text(encoding="utf-8")
  _MAX_NEWS_ITEMS: int = 10


  class ZeroShotTrader:
      name: str = "zero_shot"

      def __init__(
          self,
          market_data: MarketData,
          news_data: pd.DataFrame,
          model: str = "gpt-4o-mini",
          client: Optional[OpenAIClient] = None,
          weekly_rebalance: bool = True,
      ) -> None:
          self.market_data = market_data
          self.news_data = news_data
          self.model = model
          self._client = client or OpenAIClient()
          self.weekly_rebalance = weekly_rebalance
          self._last_week: tuple[int, int] | None = None
          self._cached: np.ndarray | None = None

      def decide(self, obs: np.ndarray, info: dict) -> np.ndarray:
          if self.weekly_rebalance and not self._is_rebalance_day(info):
              if self._cached is not None:
                  return self._cached.copy()
          # Build prompt
          user_text = self._build_user_message(info)
          try:
              result = self._client.chat(
                  model=self.model,
                  messages=[
                      {"role": "system", "content": SYSTEM_PROMPT},
                      {"role": "user", "content": user_text},
                  ],
                  temperature=0.0,
              )
              action, _ok = parse_weights_json(
                  result.text, info, ticker_order=list(self.market_data.tickers)
              )
          except RuntimeError as e:
              log.warning("LLM call failed for %s: %s — hold-shares fallback", self.name, e)
              metrics.record_parse_failure(reason=f"network_{type(e).__name__}")
              action = _hold_shares_action(info, list(self.market_data.tickers))
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
          asof = pd.Timestamp(info["date"]).normalize()
          visible = visible_news_at(self.news_data, asof)
          universe = set(self.market_data.tickers)
          if not visible.empty:
              mask = visible["tickers"].apply(lambda lst: bool(set(lst) & universe))
              visible = visible.loc[mask].sort_values(
                  "published_at_utc", ascending=False
              ).head(_MAX_NEWS_ITEMS)
          state_text = state_to_text(info, self.market_data, news_df=visible)
          return (
              state_text
              + "\n\n## Yêu cầu\nDựa trên thông tin trên, trả về DUY NHẤT một khối JSON "
                "với weights cho 5 mã (VCB, FPT, HPG, VIC, VNM)."
          )
  ```
- **PATTERN:** Mirror `src/baselines.py` for class shape + `decide` signature.
- **GOTCHA #1:** `parser._hold_shares_action` is private — re-export via
  `from src.llm.parser import _hold_shares_action` (acceptable for same-package
  internal reuse) OR duplicate the 4-line math. Pick re-export, comment why.
- **GOTCHA #2:** `result.text` may be `None` if LLM emits only tool_calls (we
  passed no tools, but defensive). `parse_weights_json` already handles None.
- **GOTCHA #3:** Don't double-record metrics; client.chat records llm_call,
  parser records parse_*. The agent does NOT call `metrics.record_*` directly
  except in the network-failure catch.
- **VALIDATE:** `.venv/bin/python -c "from src.llm.zero_shot import ZeroShotTrader; print(ZeroShotTrader.name)"`

### 3. CREATE `tests/test_zero_shot.py`

- **IMPLEMENT:** 8 tests
  - `test_protocol_runtime_check` — `isinstance(ZeroShotTrader(...), Agent)`
  - `test_first_call_fires_llm_and_caches_weights` — fake client returns valid JSON; verify weights extracted; second call same week returns CACHED (no extra LLM call)
  - `test_iso_week_change_fires_new_llm_call` — same agent, two info dicts
    in different ISO weeks → 2 LLM calls
  - `test_parse_failure_falls_back_to_hold_shares` — fake client returns
    "I refuse"; verify action ≈ holdings × close / pv (hold-shares)
  - `test_network_failure_falls_back_to_hold_shares` — fake client raises
    RuntimeError; verify hold-shares + metric recorded
  - `test_weekly_rebalance_false_calls_every_step` — disable weekly cache;
    every decide() calls LLM
  - `test_news_filtered_to_universe_before_prompt` — feed news with VCS
    ticker only (off-universe); verify user message does NOT contain VCS
  - `test_decide_uses_temperature_zero` — capture client.chat kwargs;
    assert temperature==0
- **PATTERN:** Monkeypatch `OpenAIClient.chat` to return crafted ChatResult;
  inject the patched client via `client=` parameter, NOT global monkeypatch
  (cleaner, test-local).
- **VALIDATE:** `.venv/bin/pytest tests/test_zero_shot.py -v`

### 4. CREATE `scripts/run_zero_shot.py`

- **IMPLEMENT:**
  ```python
  """CLI: run ZeroShotTrader backtest on a split.

  Writes results/zero_shot/{portfolio_curve,holdings}.parquet plus prints
  metrics snapshot (cost, parse_failure_rate, llm_calls).
  """
  from __future__ import annotations
  import argparse, logging, sys
  import pandas as pd
  from src import config
  from src.baselines import run_backtest
  from src.env_data_loader import load_market_data
  from src.llm import metrics
  from src.llm.zero_shot import ZeroShotTrader
  from src.trading_env import VNTradingEnv

  RESULTS_DIR = config.PROJECT_ROOT / "results" / "zero_shot"
  NEWS_PATH = config.PROJECT_ROOT / "data" / "processed" / "news.parquet"


  def main() -> int:
      logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
      p = argparse.ArgumentParser()
      p.add_argument("--split", default="test", choices=["train", "val", "test", "full"])
      p.add_argument("--model", default="gpt-4o-mini",
                     choices=list(config.LLM_ALLOWED_MODELS))
      p.add_argument("--seed", type=int, default=42)
      p.add_argument("--n-sessions", type=int, default=None,
                     help="Limit to first N sessions (smoke test); default = full split")
      args = p.parse_args()

      md = load_market_data(args.split)
      news = pd.read_parquet(NEWS_PATH) if NEWS_PATH.exists() else pd.DataFrame()
      print(f"split={args.split}, sessions={len(md.dates)}, news_rows={len(news)}, model={args.model}")

      metrics.reset()
      env = VNTradingEnv(md)
      agent = ZeroShotTrader(market_data=md, news_data=news, model=args.model)
      if args.n_sessions:
          # Smoke mode: override env to terminate early
          # Quick hack: monkeypatch _terminated check; or just count steps
          result = _run_n(env, agent, args.seed, args.n_sessions)
      else:
          result = run_backtest(env, agent, seed=args.seed)
      _write(result)

      snap = metrics.get_snapshot()
      print(f"\n=== Backtest summary ===")
      print(f"agent: {result.agent_name}  steps: {result.n_steps}")
      print(f"final_pv: {result.final_pv:,.0f}  cum_return: {result.final_pv/float(config.INITIAL_CAPITAL)-1:+.2%}")
      print(f"LLM calls: {snap['llm_calls']}, cost ~${snap['estimated_cost_usd']:.4f}")
      print(f"parse_success: {snap['parse_success']}, parse_failure: {snap['parse_failure']}, rate: {snap['parse_failure_rate']:.1%}")
      print(f"parse_failure_reasons: {snap['parse_failure_reasons']}")
      return 0


  def _run_n(env: VNTradingEnv, agent: ZeroShotTrader, seed: int, n: int):
      """Smoke runner: run N steps then return whatever BacktestResult-equivalent."""
      from src.agent_base import BacktestResult
      obs, info = env.reset(seed=seed)
      records = []
      from src.baselines import _snapshot, _records_to_frames
      records.append(_snapshot(env, info))
      total_r, steps = 0.0, 0
      while not env._terminated and steps < n:
          action = agent.decide(obs, info)
          obs, r, term, trunc, info = env.step(action)
          total_r += r; steps += 1
          records.append(_snapshot(env, info))
      pv_df, h_df = _records_to_frames(records, agent.name)
      return BacktestResult(agent_name=agent.name, portfolio_curve=pv_df,
                            holdings_curve=h_df, total_log_return=total_r,
                            final_pv=float(info["portfolio_value"]),
                            n_steps=steps, seed=seed)


  def _write(result) -> None:
      d = RESULTS_DIR
      d.mkdir(parents=True, exist_ok=True)
      result.portfolio_curve.to_parquet(d / "portfolio_curve.parquet",
                                        engine="pyarrow", compression="snappy")
      result.holdings_curve.to_parquet(d / "holdings.parquet",
                                       engine="pyarrow", compression="snappy")
      print(f"wrote {result.agent_name}: {result.n_steps} steps, pv={result.final_pv:,.0f}")


  if __name__ == "__main__":
      sys.exit(main())
  ```
- **PATTERN:** Mirror `scripts/run_baselines.py`. Reuse `_snapshot` +
  `_records_to_frames` from `baselines.py` (acceptable private import).
- **GOTCHA:** `--n-sessions` smoke mode for testing without spending full
  $0.25; default = full backtest.
- **VALIDATE:** `.venv/bin/python scripts/run_zero_shot.py --split test --n-sessions 10`

### 5. REAL-CALL SMOKE (optional, gated)

- **IMPLEMENT:** Manual run after `.env` has valid `OPENAI_API_KEY`:
  ```bash
  .venv/bin/python scripts/run_zero_shot.py --split test --n-sessions 10
  ```
- **PATTERN:** Don't add to pytest — costs real money + needs key. Document
  in PR description with captured output.
- **VALIDATE:** Output shows: 10 steps, ≥ 1 LLM call (first week), cost < $0.05,
  parse_success ≥ 1, no errors.

---

## TESTING STRATEGY

### Unit Tests (8 new)

| Test | Verifies |
|------|----------|
| `test_protocol_runtime_check` | `isinstance(.., Agent)` |
| `test_first_call_fires_llm_and_caches_weights` | first decide → LLM call + cache |
| `test_iso_week_change_fires_new_llm_call` | week transition triggers re-call |
| `test_parse_failure_falls_back_to_hold_shares` | bad JSON → hold weights |
| `test_network_failure_falls_back_to_hold_shares` | RuntimeError → hold weights |
| `test_weekly_rebalance_false_calls_every_step` | flag disables cache |
| `test_news_filtered_to_universe_before_prompt` | off-universe tickers dropped |
| `test_decide_uses_temperature_zero` | temp=0 passed to client |

Total after PKG-6: 117 (prior) + 8 = **125 tests**.

### Integration smoke (manual, in PR description)

`scripts/run_zero_shot.py --split test --n-sessions 10` with real
`OPENAI_API_KEY`. Capture:
- LLM calls count (1-2 in 10-session smoke)
- Cost USD (< $0.05)
- parse_success / parse_failure
- Final pv / cumulative_return (informational, not asserted)

### Edge Cases Explicitly Covered

| # | Edge case | Test |
|---|-----------|------|
| 1 | ISO week boundary at year-end (week 52 → week 1) | covered via `_is_rebalance_day` logic — Spike A traces all 52 weeks |
| 2 | First call (last_week = None) always triggers | `test_first_call_fires_llm_and_caches_weights` |
| 3 | LLM returns text with no JSON | `test_parse_failure_falls_back_to_hold_shares` via parser |
| 4 | Network fails after all retries | `test_network_failure_falls_back_to_hold_shares` |
| 5 | News dataframe empty (no news for date) | covered by `visible_news_at` returning empty → serialize handles |
| 6 | LLM hallucinates off-universe ticker (e.g. "AAPL": 0.5) | parser.py only picks `config.TICKERS` keys; missing tickers default to 0 |
| 7 | LLM emits weights summing > 1 | parser.py renormalizes |
| 8 | weekly_rebalance=False bypasses cache | `test_weekly_rebalance_false_calls_every_step` |

### Edge Cases NOT Covered (deferred)

- **Real OpenAI prompt cache hit rate** — verify only via real-call smoke
  with cached_tokens > 0; can't mock truthfully
- **gpt-4o vs gpt-4o-mini quality difference** — out of scope, PKG-8 explores
- **Cost ceiling enforcement** — PKG-10 may add hard cap; PKG-6 just surfaces

---

## VALIDATION COMMANDS

### Level 1: Syntax & Style

```bash
.venv/bin/ruff check src/ tests/ scripts/
```

### Level 2: Unit Tests

```bash
.venv/bin/pytest tests/ -v
# Expected: 125 passed (117 prior + 8 new)
```

### Level 3: CLI mocked smoke

```bash
# Without OPENAI_API_KEY: should fail loud on OpenAIClient construction
unset OPENAI_API_KEY
.venv/bin/python scripts/run_zero_shot.py --split test --n-sessions 1 2>&1 | head -5
# Expected: RuntimeError "OPENAI_API_KEY not set"
```

### Level 4: Real-call smoke (gated, ~$0.02)

```bash
# Set key first
.venv/bin/python scripts/run_zero_shot.py --split test --n-sessions 10
# Expected: completes, prints LLM calls + cost + parse rates
```

### Level 5: Regression

```bash
.venv/bin/pytest tests/test_baselines.py tests/test_trading_env.py tests/test_llm_*.py -v
# All 117 prior tests still pass.
```

---

## ACCEPTANCE CRITERIA

Mirrors GitHub Issue #7:

- [ ] Mock backtest 1 quarter (62 sessions) emits valid weights ≥ 95% of LLM
  responses (parse_failure_rate < 5%)
- [ ] Weekly cadence — non-rebalance day does NOT call LLM (verified via
  `test_first_call_fires_llm_and_caches_weights`)
- [ ] All 8 tests pass; 125 total; ruff clean
- [ ] PR description includes real-call smoke output (≤ 10 sessions) if
  OPENAI_API_KEY available locally
- [ ] CLI script writes 2 parquets to `results/zero_shot/`

---

## COMPLETION CHECKLIST

- [ ] Spike A ISO-week count verified ≈ 52
- [ ] `src/llm/prompts/zero_shot.md` written (Vietnamese, ≥ 4000 chars)
- [ ] `src/llm/zero_shot.py` written; imports clean; `name = "zero_shot"`
- [ ] `tests/test_zero_shot.py` with 8 tests pass
- [ ] `scripts/run_zero_shot.py` runs in mocked mode
- [ ] Real-call smoke captured (if OPENAI_API_KEY set)
- [ ] PR mở với title `PKG-6: LLM Zero-shot Trader`, body `Closes #7`
- [ ] PKG-7/8 unblocked (zero-shot is reference impl for both)

---

## NOTES

### Design decisions worth flagging in PR

1. **ISO week trigger** — `pd.Timestamp.isocalendar()` is robust against
   year-boundary edge cases (week 52 → week 1 across Dec 31 / Jan 1).
2. **Default model gpt-4o-mini** — cost $0.25/backtest; user can override
   `--model gpt-4o` for more capable reasoning.
3. **Reproducibility caveat** — temp=0 only ≈98% deterministic; cache
   responses (PKG-S) for full repro.
4. **Network failure → hold-shares** — wraps RuntimeError after client's
   5 retries; mirrors parser fallback semantics.
5. **News pre-filtered before prompt** — universe + visibility filters
   applied in agent, not in serialize, because serialize is generic.
6. **Re-export `_hold_shares_action` from parser** — same-package private
   reuse acceptable; alternative is duplication.

### Risks specific to PKG-6

| # | Risk | Mitigation |
|---|------|-----------|
| 1 | LLM consistently emits malformed JSON → high parse_failure_rate | Strong prompt with explicit JSON-only instruction + 2 examples; PKG-10 alerts if rate > 5% |
| 2 | Cost overrun if weekly cadence bugged | Spike A counts ISO weeks (~52) before merge; PR includes count |
| 3 | LLM hallucinates off-universe tickers | parser filters by `ticker_order` (only config.TICKERS read) — silent drop, not error |
| 4 | Real-call smoke costs $$$ on dev machine | `--n-sessions 10` cap; default off in CI; expected < $0.05 per smoke |
| 5 | gpt-4o-mini quality insufficient for any signal | Acceptable — zero-shot is a BASELINE; if it loses to random, that's the result we report |
| 6 | Prompt cache miss because system prompt < 1024 tokens | `wc -c` ≥ 4000 verified; cached_tokens > 0 in smoke |

### Khi gặp blocker

- Spike A reveals < 52 weeks → check `isocalendar` edge cases at year boundaries
- All 8 tests pass but real-call returns "I cannot help with financial advice" → loosen prompt wording; emphasize this is a research backtest, not advice
- parse_failure_rate > 5% on real run → tighten prompt JSON example, add 2-3 few-shot examples
- Cost > $0.50 on full backtest → check cadence: are we calling LLM 248× (daily) instead of ~52× (weekly)?
- Real-call returns invalid weights consistently → log full text response; LLM may be wrapping JSON in extra prose

### Phase 2 status after PKG-6

| PKG | Status |
|-----|--------|
| PKG-5 LLM core | ✅ merged |
| **PKG-6 zero-shot (this PR)** | 🟡 ready after impl |
| PKG-7 single-agentic | unblocked; can copy patterns from PKG-6 |
| PKG-8 multi-agent | unblocked; can copy patterns from PKG-6 |
| PKG-9 DDPG | unblocked, independent track |
| PKG-10 backtest engine | needs PKG-6/9 first to have agents to run |

---

## Confidence Score

**8.0/10** for one-pass implementation.

Subtract:
- −0.5 prompt engineering (Vietnamese JSON output) — first real LLM
  interaction, may need 1-2 wording iterations
- −0.5 real-call smoke costs $$; can't test in CI

Add back:
- +1.0 PKG-5 building blocks established with strong tests
- +0.5 patterns from PKG-4 baselines transfer directly (class+decide+cache)
- +0.5 weekly trigger logic is straightforward (mirror EqualWeightRebalance)

PKG-6 is genuinely 0.5-day work given PKG-5 infrastructure. The hour-long
risk is prompt iteration.
