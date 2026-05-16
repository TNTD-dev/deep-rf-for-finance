# Feature: PKG-4 — Baselines + random-agent end-to-end validation

> Last gate of Phase 1. Wires PKG-1/2/3 together cho lần đầu, đặt **Agent
> protocol** mà DDPG/PPO/LLM/multi-agent sẽ implement. Nếu PKG-4 fail, có
> nghĩa là một trong PKG-1/2/3 broken — chứ không phải PKG-4.

## Feature Description

Hai baseline đơn giản + 1 random agent + 1 mini backtest runner + 1 CLI để
sanity-check end-to-end PKG-1/2/3 stack:

- **BuyAndHold:** session đầu tiên allocate equal-weight; sau đó hold (cached
  weights, env không trade vì target == current).
- **EqualWeightRebalance:** rebalance về 1/n_tickers vào first-trading-day mỗi
  tháng calendar; ngày khác hold.
- **RandomAgent:** sample từ `env.action_space` mỗi step — sanity stress test.
- **Agent protocol:** `decide(obs, info) -> action` — single interface mà
  PKG-6/7/8/9 sẽ implement giống hệt.
- **Mini backtest runner:** `run_backtest(env, agent, seed) -> BacktestResult`
  — versions thu nhỏ của PKG-10's full runner; cho phép test baselines mà
  không phụ thuộc PKG-10.

Artifact output: `results/baselines/{agent}/portfolio_curve.parquet` +
`holdings.parquet`. PKG-10 sẽ đọc các artifact này tính metrics; PKG-13
frontend sẽ render chart.

## User Story

As a **người verify (Person 2)**
I want to **chạy 1 lệnh `python scripts/run_baselines.py`** mà cả 3 agent
đều produce portfolio curve hợp lệ và print cumulative return
So that **biết PKG-1/2/3 stack hoạt động đúng before Phase 2 train DDPG**.

As a **PKG-6/7/8/9 implementer (Duc trong tuần sau)**
I want to **một `Agent` Protocol đã land** để mỗi agent mới chỉ cần
implement `decide()` và work ngay với env + backtest runner
So that **không phải refactor interface 4 lần khi mỗi LLM agent ra mắt**.

## Problem Statement

3 vấn đề độc lập:

1. **End-to-end stack chưa được verify** — PKG-1/2/3 đã test riêng từng module,
   nhưng chưa có agent thực tế chạy step → step → step → terminate trên test
   period. Bug ẩn ở seam (e.g. obs có NaN làm agent crash) chưa lộ.
2. **Agent interface chưa lock** — mỗi LLM agent sau sẽ implement theo cách
   riêng nếu không có Protocol chung. Tránh refactor 4 lần.
3. **Baselines là benchmark bắt buộc cho report** — Person 1 cần BuyAndHold +
   EqualWeight numbers để so sánh DDPG/LLM trong Phase 2-4. Phải có sớm.

## Solution Statement

1 module `baselines.py` chứa 3 agent class + 1 Protocol; 1 mini runner;
1 CLI; tests dùng synthetic MarketData từ PKG-3 fixture pattern.

Key design decisions LOCK trước khi code (xem §"DESIGN DECISIONS" dưới):

- D1. Agent base = `Protocol` trong **`src/agent_base.py`** (file mới, không
  đụng `src/agents/__init__.py` — TASKS marked PKG-S serialized).
- D2. `decide(obs, info) -> np.ndarray` — pass cả gym obs và env info dict.
  LLM agents ignore obs, parse `info["date"]` cho weekly schedule.
- D3. Monthly rebalance = **first-trading-day mỗi tháng calendar**, detect
  bằng `pd.Timestamp(info["date"]).month != self._last_rebalance_month`.
- D4. Equal-weight target = **0.19 mỗi ticker** (5 × 0.19 = 0.95, để 5% cash
  buffer hấp thụ fee + lot-100 drift). Document rationale.
- D5. Portfolio curve schema: long parquet `(date, agent, portfolio_value,
  cash, w_VCB, w_FPT, w_HPG, w_VIC, w_VNM)`. PKG-10/13 consume.
- D6. RandomAgent dùng env's `np_random` (NOT a separate RNG) — same seed →
  same trajectory; matches `test_same_seed_same_trajectory` invariant from PKG-3.
- D7. Mini backtest runner = pure function `run_backtest(env, agent, seed)`,
  không là class. Return `BacktestResult` dataclass (frozen).

## Feature Metadata

- **Feature Type:** New Capability + Foundation (Agent protocol lock)
- **Estimated Complexity:** **Low-Medium** — patterns established, glue code,
  but Agent protocol lock có long-term impact
- **Primary Systems Affected:** `src/baselines.py`, `src/agent_base.py`,
  `scripts/run_baselines.py`, `tests/test_baselines.py`,
  `results/baselines/*` output artifacts
- **Dependencies:** Tất cả đã có ở pyproject từ PKG-0: `gymnasium`, `numpy`,
  `pandas`, `pyarrow`. Không cần thêm dep mới.

---

## CONTEXT REFERENCES

### Relevant Codebase Files — ĐỌC TRƯỚC KHI IMPLEMENT

**Reuse bắt buộc (không re-implement):**
- `src/trading_env.py` (toàn bộ, ~210 dòng) — VNTradingEnv contract:
  - Action space `Box(-1, 1, (5,), float32)` (line 81)
  - `info` dict keys: `date, t, cash, holdings, portfolio_value, pv_before,
    pv_after, fill_t` (lines 113-118, 196-205)
  - Negative action clamped to 0 + sum > 1 renormalized (lines 122-128)
  - `_terminated` exposed cho external loop (line 117)
- `src/env_data_loader.py` (toàn bộ) — `load_market_data(split)`,
  `MarketData` dataclass (frozen). Baselines test fixture nên dùng
  `_synthetic_market_data` từ `tests/test_trading_env.py`.
- `src/config.py` (line 47): `TICKERS = ["VCB","FPT","HPG","VIC","VNM"]`
  — column order LOCKED cho portfolio_curve parquet.

**Pattern bắt buộc mirror:**
- `tests/test_trading_env.py:31-58` (`_synthetic_market_data`) — fixture
  builder cho test baselines. Mirror, không re-implement. Có thể move
  helper sang `tests/conftest.py` nếu test_baselines.py cần dùng.
- `src/data_pipeline/news_align.py:1-19` — module docstring shape.
- `scripts/fetch_data.py:1-12` + `scripts/fetch_news.py:1-13` — CLI script
  docstring + argparse layout pattern.

**Read-only context:**
- `CLAUDE.md` §"Patterns" §"Pluggable agent interface": every agent implements
  `decide(state) -> action`. Env doesn't know if agent is RL or LLM.
- `CLAUDE.md` §"Patterns" §"Decision layer ≠ execution layer": agents output
  continuous `[-1, 1]` target weights; env handles fee + lot rounding.
- `.agent/PRD.md` §4 "✅ 2 baselines: buy-and-hold, equal-weight rebalance monthly"
- `.agent/PRD.md` §15 locked params, especially `TICKERS` and decision
  frequency policy ("DDPG daily; LLM/agentic weekly").

**Don't touch (file ownership):**
- `src/agents/__init__.py` — **PKG-S SERIALIZED**. Đây là registry mà PKG-S
  merge cuối cùng. Tạo `src/agent_base.py` riêng thay vì.
- `src/eval/*` — PKG-10 owns backtest engine + metrics. Mini runner trong
  PKG-4 chỉ local, không export cho ai dùng.
- `src/trading_env.py`, `src/env_data_loader.py` — PKG-3 owns.
- `src/data_pipeline/*` — PKG-1/2 owns.

### New Files to Create

```
src/
├── agent_base.py          # Agent Protocol — interface contract
└── baselines.py           # BuyAndHold, EqualWeightRebalance, RandomAgent,
                           # BacktestResult dataclass, run_backtest()
scripts/
└── run_baselines.py       # CLI: load test split → run 3 agents → write parquet
tests/
├── conftest.py            # shared fixture: _synthetic_market_data (moved from test_trading_env.py)
└── test_baselines.py      # 10 tests
results/baselines/
├── buy_and_hold/
│   ├── portfolio_curve.parquet
│   └── holdings.parquet
├── equal_weight/
│   └── ...
└── random/
    └── ...
```

### Relevant Documentation — ĐỌC TRƯỚC KHI IMPLEMENT

- **`typing.Protocol`:** https://docs.python.org/3/library/typing.html#typing.Protocol
  — structural subtyping cho duck-typed agent interface. Không inheritance.
- **Gymnasium env loop pattern:** https://gymnasium.farama.org/introduction/basic_usage/
  — `while not terminated and not truncated: action = ...; obs, r, term, trunc, info = env.step(action)`
- **pandas to_parquet partitioned write:** không cần partitioning ở scale này
  (~250 rows × 3 agents = 750 rows), single file đủ.

### Pre-implementation spike (1 lệnh check trước khi code)

```bash
# Verify env + load_market_data có sẵn từ PKG-3 và step loop chạy 248 ngày
.venv/bin/python <<'PY'
import numpy as np
from src.env_data_loader import load_market_data
from src.trading_env import VNTradingEnv
env = VNTradingEnv(load_market_data("test"))
obs, info = env.reset(seed=42)
# Equal-weight 0.19 buy & hold
weights = np.array([0.19]*5, dtype=np.float32)
total_r, steps = 0.0, 0
while not env._terminated:
    obs, r, term, trunc, info = env.step(weights)  # cached weights = hold
    total_r += r
    steps += 1
print(f"Hold-after-equal-weight: {steps} steps, log-r={total_r:.4f}, final pv={info['portfolio_value']:.0f}")
PY
```

Expected: ~247 steps, total log-r in range [-0.3, +0.3] (depends on VN30
performance trong test period), pv in range [700M, 1.4B]. If this works,
PKG-4 just needs glue code around the same loop pattern.

### Patterns to Follow (từ codebase đã land)

**Module docstring (mirror `src/trading_env.py:1-25`):**

```python
"""One-paragraph mô tả contract + invariants + lookahead semantics.

Locked constants stated upfront. Reference PRD/CLAUDE.md sections that
this module preserves.
"""
```

**Frozen dataclass (mirror `src/env_data_loader.py:25-35`):**

```python
@dataclass(frozen=True)
class BacktestResult:
    agent_name: str
    portfolio_curve: pd.DataFrame   # columns: date, portfolio_value, cash, w_*
    holdings_curve: pd.DataFrame    # columns: date, h_VCB, h_FPT, ...
    total_log_return: float
    final_pv: float
    n_steps: int
    seed: int
```

**Test docstring (mirror `tests/test_trading_env.py:97-101`):**

```python
def test_<invariant>() -> None:
    """Encode WHY. Reference PRD section or design decision (D1-D7)."""
```

---

## DESIGN DECISIONS — LOCK BEFORE IMPLEMENT

### D1. Agent base lives in `src/agent_base.py`, NOT `src/agents/__init__.py`

Reason: `.agent/TASKS.md` PKG-S explicitly marks `src/agents/__init__.py` as
SERIALIZED — multiple packages touch it for registry, merged last. Putting
Protocol in `agent_base.py` keeps PKG-4 atomic; PKG-S later imports the
Protocol from `agent_base` and adds registry entries.

```python
# src/agent_base.py
from typing import Protocol, runtime_checkable
import numpy as np

@runtime_checkable
class Agent(Protocol):
    name: str  # for logging + filesystem path

    def decide(self, obs: np.ndarray, info: dict) -> np.ndarray:
        """Map (obs, info) → action in env.action_space.

        info contains 'date' (ISO string), 't' (int session index),
        'portfolio_value', 'cash', 'holdings'. Agents may consume any
        subset; RL agents typically use obs, LLM agents use info['date']
        for schedule + parse obs/info as needed.
        """
        ...
```

`runtime_checkable` enables `isinstance(obj, Agent)` for sanity checks.

### D2. Pass both `obs` and `info` to `decide()`

- RL agents (DDPG/PPO): use only `obs` (56-dim float32 vector)
- LLM agents: parse `info["date"]` for weekly schedule, use `info["holdings"]`
  and `info["cash"]` to know portfolio state, ignore `obs`
- Baselines: use `info["date"]` for rebalance scheduling

Alternative considered: pass higher-level `State` dataclass with parsed fields.
Rejected because it duplicates `info` dict + adds layer with no benefit for
the agents we have.

### D3. Monthly rebalance trigger

```python
def _is_rebalance_day(self, info: dict) -> bool:
    month = pd.Timestamp(info["date"]).month
    if month != self._last_rebalance_month:
        self._last_rebalance_month = month
        return True
    return False
```

First call: `_last_rebalance_month = None`, so any month != None → True
(triggers initial allocation on first step). Subsequent same-month calls →
False (hold). Month change → True (rebalance).

Edge case: month change đụng ngày nghỉ → next trading day is automatically
the rebalance day (env only steps on trading days). Correct by construction.

### D4. Equal-weight target = 0.19 per ticker (not 0.20)

5 × 0.20 = 1.00 nominal → due to lot-100 floor + buy fee 0.15%, env can't
quite reach 1.00 invested without going negative cash and triggering buy
fallback. Setting 0.19 gives 5% cash buffer that absorbs:
- Buy fee: ≤ 0.95 × 0.0015 = 0.14% NAV
- Lot-100 drift: ≤ 100 × max_price × 5 ≈ 0.1% NAV at 1B initial
- Total drag ≈ 0.25% NAV, comfortably inside 5% buffer

Document trong module docstring + test verifies cash stays positive.

### D5. Output schema — Parquet long format

`results/baselines/{agent_name}/portfolio_curve.parquet`:
```
columns: [date, agent_name, portfolio_value, cash, w_VCB, w_FPT, w_HPG, w_VIC, w_VNM]
dtypes:  date=datetime64[ns], agent_name=str, *=float64
rows:    n_test_sessions (e.g. 248)
```

`results/baselines/{agent_name}/holdings.parquet`:
```
columns: [date, agent_name, h_VCB, h_FPT, h_HPG, h_VIC, h_VNM]
dtypes:  date=datetime64[ns], agent_name=str, h_*=int64
rows:    n_test_sessions
```

Schema rationale: long format matches PKG-1 prices.parquet convention.
PKG-10 metric runner reads these, computes Sharpe/MDD/turnover. PKG-13
frontend renders chart by `agent_name` series.

Ticker order in column names = `config.TICKERS` order. Locked.

### D6. RandomAgent uses env's `np_random` (NOT a separate RNG)

For reproducibility (PKG-3 invariant). `env.np_random` is seeded by
`env.reset(seed)`. Agent stores reference to env's RNG at construction:

```python
class RandomAgent:
    name = "random"
    def __init__(self, env: VNTradingEnv):
        self._rng = env.np_random
    def decide(self, obs, info):
        return self._rng.uniform(-1, 1, 5).astype(np.float32)
```

This matches `test_same_seed_same_trajectory` in PKG-3 — env owns the RNG,
agent borrows. Avoids dual-RNG sync issues.

Alternative `env.action_space.sample()` rejected: that uses
`action_space._np_random` which is seeded independently, not by
`env.reset(seed)`. Would break repro.

### D7. Mini backtest runner = function, not class

```python
def run_backtest(env: VNTradingEnv, agent: Agent, seed: int = 42) -> BacktestResult:
    """Standard step-until-terminate loop. Returns BacktestResult.
    PKG-10 ships fuller runner with metrics; this is the minimal core."""
    ...
```

Pure function, no state — same env + same agent + same seed → same result.

---

## IMPLEMENTATION PLAN

### Phase 1: Agent protocol + base utilities

**Goal:** Lock the interface that PKG-6/7/8/9 implement.

**Tasks:**
- `src/agent_base.py`: `Agent` Protocol (runtime_checkable), `BacktestResult`
  dataclass (frozen)

### Phase 2: Baselines + runner

**Goal:** Production-ready agents + step-loop function.

**Tasks:**
- `src/baselines.py`: `BuyAndHold`, `EqualWeightRebalance`, `RandomAgent`,
  `run_backtest`
- Each agent implements `name` attribute + `decide(obs, info)` signature

### Phase 3: Test suite

**Goal:** 10 tests covering Protocol + 3 agents + runner.

**Tasks:**
- `tests/conftest.py`: shared fixture `_synthetic_market_data` (moved from
  test_trading_env.py — or just imported)
- `tests/test_baselines.py`: 10 tests

### Phase 4: CLI + real-data E2E

**Goal:** 1-command run on test split, save artifacts.

**Tasks:**
- `scripts/run_baselines.py`: argparse + load_market_data + run 3 agents +
  write parquets + print summary table
- Run on real test data, capture output for PR

---

## STEP-BY-STEP TASKS

### 1. CREATE `src/agent_base.py`

- **IMPLEMENT:**
  ```python
  """Agent Protocol + BacktestResult dataclass — interface contract.

  Every agent in this project (BuyAndHold, EqualWeightRebalance, RandomAgent,
  DDPG via sb3 wrapper, LLM zero-shot, single-agentic, multi-agent) implements
  the `decide(obs, info) -> action` signature.

  Protocol is runtime_checkable so `isinstance(obj, Agent)` works for sanity
  asserts. Not enforced — duck-typing is fine if obj has `.name` and `.decide()`.
  """
  from __future__ import annotations
  from dataclasses import dataclass
  from typing import Protocol, runtime_checkable
  import numpy as np
  import pandas as pd


  @runtime_checkable
  class Agent(Protocol):
      """Pluggable agent interface (CLAUDE.md §"Patterns")."""
      name: str  # short identifier, used in filesystem paths

      def decide(self, obs: np.ndarray, info: dict) -> np.ndarray:
          """Return action in env.action_space = Box(-1, 1, (n_tickers,)).

          Args:
              obs: 56-dim float32 obs from VNTradingEnv (see trading_env.py).
              info: env info dict with keys date, t, cash, holdings,
                  portfolio_value. Agents may consume any subset.
          """
          ...


  @dataclass(frozen=True)
  class BacktestResult:
      """Output of run_backtest. Immutable so downstream metric code can't
      accidentally mutate trajectory mid-analysis."""
      agent_name: str
      portfolio_curve: pd.DataFrame   # date, portfolio_value, cash, w_*
      holdings_curve: pd.DataFrame    # date, h_*
      total_log_return: float
      final_pv: float
      n_steps: int
      seed: int
  ```
- **PATTERN:** Mirror `src/env_data_loader.py:25-35` frozen dataclass pattern.
- **IMPORTS:** `typing.Protocol, runtime_checkable`, `dataclasses.dataclass`,
  `numpy`, `pandas`.
- **GOTCHA:** `Protocol` cannot have non-default class variables in older
  pyright versions — `name: str` as class attribute annotation is fine in
  3.11+, leave it as is.
- **VALIDATE:** `.venv/bin/python -c "from src.agent_base import Agent, BacktestResult; print(Agent, BacktestResult)"`

### 2. CREATE `tests/conftest.py`

- **IMPLEMENT:**
  ```python
  """Shared pytest fixtures. Centralizing synthetic MarketData avoids
  duplicating the 60-session fixture across multiple test files."""
  from __future__ import annotations
  import numpy as np
  import pandas as pd
  import pytest
  from src import config
  from src.env_data_loader import MarketData


  @pytest.fixture
  def synthetic_market_data() -> MarketData:
      """60-session × 5-ticker fixture with deterministic uptrend.

      Prices start at [50, 60, 70, 80, 90] and drift +0.1% per session.
      Indicators are random z-scored. Use this anywhere an env needs to
      step without depending on PKG-1 parquet output.
      """
      return _build(n_sessions=60)


  def _build(n_sessions: int = 60) -> MarketData:
      rng = np.random.default_rng(seed=0)
      base = np.array([50.0, 60.0, 70.0, 80.0, 90.0], dtype=np.float32)
      n_tickers = len(base)
      close = np.zeros((n_sessions, n_tickers), dtype=np.float32)
      close[0] = base
      for t in range(1, n_sessions):
          close[t] = close[t - 1] * 1.001
      high = close * 1.01
      low = close * 0.99
      open_ = close * (1.0 + rng.normal(0, 0.001, close.shape).astype(np.float32))
      ind = rng.normal(0, 1, (n_sessions, n_tickers, 9)).astype(np.float32)
      dates = pd.date_range("2025-01-02", periods=n_sessions, freq="B")
      return MarketData(
          dates=pd.DatetimeIndex(dates),
          tickers=tuple(config.TICKERS),
          close=close, open=open_, high=high, low=low,
          indicators_norm=ind, warmup_offset=0,
      )
  ```
- **PATTERN:** Mirror existing fixture in `tests/test_trading_env.py:31-58`.
  Eventually consider deduping by importing from conftest in test_trading_env;
  not required in PKG-4 (don't touch other tests).
- **GOTCHA:** `conftest.py` fixtures auto-discovered by pytest; no import in
  test files needed.
- **VALIDATE:** `.venv/bin/pytest tests/test_trading_env.py -v` (no regression
  since we don't touch that file).

### 3. CREATE `src/baselines.py`

- **IMPLEMENT:**
  ```python
  """Buy-and-hold + equal-weight monthly rebalance + random + mini backtest runner.

  Equal-weight target is 0.19 per ticker (5 × 0.19 = 0.95) to leave 5% cash
  buffer that absorbs buy fee (≤ 0.14% NAV) + lot-100 rounding drift
  (≤ 0.1% NAV). Without the buffer, env's "can't afford" fallback would
  trigger and silently under-allocate.

  Monthly rebalance triggers on first-trading-day of each calendar month,
  detected by month-changed-since-last-rebalance.
  """
  from __future__ import annotations
  from typing import Optional
  import numpy as np
  import pandas as pd
  from src import config
  from src.agent_base import Agent, BacktestResult
  from src.trading_env import N_TICKERS, VNTradingEnv

  EQUAL_WEIGHT_TARGET: float = 0.19  # see module docstring rationale


  class BuyAndHold:
      """First call allocates equal-weight 0.19 each; subsequent calls hold."""
      name: str = "buy_and_hold"

      def __init__(self) -> None:
          self._initialized: bool = False
          self._weights: np.ndarray = np.zeros(N_TICKERS, dtype=np.float32)

      def decide(self, obs: np.ndarray, info: dict) -> np.ndarray:
          if not self._initialized:
              self._weights = np.full(N_TICKERS, EQUAL_WEIGHT_TARGET, dtype=np.float32)
              self._initialized = True
          return self._weights.copy()


  class EqualWeightRebalance:
      """Rebalance to equal-weight on first trading day of each calendar month."""
      name: str = "equal_weight"

      def __init__(self) -> None:
          self._last_month: Optional[int] = None
          self._weights: np.ndarray = np.zeros(N_TICKERS, dtype=np.float32)

      def decide(self, obs: np.ndarray, info: dict) -> np.ndarray:
          month = pd.Timestamp(info["date"]).month
          if month != self._last_month:
              self._weights = np.full(N_TICKERS, EQUAL_WEIGHT_TARGET, dtype=np.float32)
              self._last_month = month
          return self._weights.copy()


  class RandomAgent:
      """Uniform sample from action_space using env's seeded RNG (reproducible)."""
      name: str = "random"

      def __init__(self, env: VNTradingEnv) -> None:
          self._rng = env.np_random

      def decide(self, obs: np.ndarray, info: dict) -> np.ndarray:
          return self._rng.uniform(-1, 1, N_TICKERS).astype(np.float32)


  def run_backtest(
      env: VNTradingEnv, agent: Agent, seed: int = 42
  ) -> BacktestResult:
      """Step-until-terminate loop. Records (date, pv, cash, weights, holdings)."""
      obs, info = env.reset(seed=seed)
      records = [_snapshot(env, info)]
      total_log_r = 0.0
      n_steps = 0
      while not env._terminated:
          action = agent.decide(obs, info)
          obs, r, term, trunc, info = env.step(action)
          total_log_r += r
          n_steps += 1
          records.append(_snapshot(env, info))
      pv_df, h_df = _records_to_frames(records, agent.name)
      return BacktestResult(
          agent_name=agent.name,
          portfolio_curve=pv_df,
          holdings_curve=h_df,
          total_log_return=total_log_r,
          final_pv=float(info["portfolio_value"]),
          n_steps=n_steps,
          seed=seed,
      )


  def _snapshot(env: VNTradingEnv, info: dict) -> dict:
      pv = float(info["portfolio_value"])
      holdings = np.asarray(info["holdings"], dtype=np.int64)
      t = min(env._t, len(env.md.dates) - 1)
      prices = env.md.close[t]
      weights = (holdings * prices) / max(pv, 1e-8)
      return {
          "date": info["date"],
          "portfolio_value": pv,
          "cash": float(info["cash"]),
          **{f"w_{tkr}": float(weights[i]) for i, tkr in enumerate(config.TICKERS)},
          **{f"h_{tkr}": int(holdings[i]) for i, tkr in enumerate(config.TICKERS)},
      }


  def _records_to_frames(
      records: list[dict], agent_name: str
  ) -> tuple[pd.DataFrame, pd.DataFrame]:
      df = pd.DataFrame(records)
      df["date"] = pd.to_datetime(df["date"])
      df["agent_name"] = agent_name
      w_cols = [f"w_{t}" for t in config.TICKERS]
      h_cols = [f"h_{t}" for t in config.TICKERS]
      pv_df = df[["date", "agent_name", "portfolio_value", "cash", *w_cols]].copy()
      h_df = df[["date", "agent_name", *h_cols]].copy()
      return pv_df, h_df
  ```
- **PATTERN:** Mirror `src/trading_env.py` module docstring + import shape;
  mirror `src/env_data_loader.py` for dataclass-style helpers.
- **GOTCHA #1:** `.copy()` on returned weights — agents share array reference
  with env otherwise, and env mutates `_holdings` next step.
- **GOTCHA #2:** `_records_to_frames` long format avoids `pivot` step
  downstream; PKG-10/13 consumers concat across agents.
- **GOTCHA #3:** `_snapshot` accesses `env.md.close[t]` directly — using
  current session's close because env always fills at close. Documented.
- **GOTCHA #4:** `env._t` may equal `len(dates)` after terminal step;
  `min(env._t, len(env.md.dates) - 1)` clamps for safe indexing.
- **VALIDATE:** `.venv/bin/python -c "
  from src.env_data_loader import load_market_data
  from src.trading_env import VNTradingEnv
  from src.baselines import BuyAndHold, EqualWeightRebalance, RandomAgent, run_backtest
  env = VNTradingEnv(load_market_data('test'))
  r = run_backtest(env, BuyAndHold(), seed=42)
  print(r.agent_name, r.n_steps, r.total_log_return, r.final_pv)
  print(r.portfolio_curve.head(3))
  "`

### 4. CREATE `tests/test_baselines.py`

- **IMPLEMENT:** 10 tests
  - `test_agent_protocol_runtime_check` — all 3 agents satisfy `isinstance(_, Agent)`
  - `test_buy_and_hold_emits_constant_weights_after_first_call` — second `decide` returns same array
  - `test_buy_and_hold_holdings_constant_after_first_step` — holdings don't change after step 1 (modulo lot-100 noise on day 1 only)
  - `test_equal_weight_rebalances_on_month_change` — different month → re-emit; same month → use cached
  - `test_equal_weight_first_call_initializes` — `_last_month=None` → triggers
  - `test_random_agent_uses_env_rng` — same env seed → identical action sequences
  - `test_run_backtest_returns_correct_shape` — n_steps + 1 records (initial + per-step)
  - `test_run_backtest_portfolio_curve_schema` — columns match D5 spec
  - `test_run_backtest_reproducible_same_seed` — 2 runs same seed → identical final_pv
  - `test_buy_and_hold_full_episode_no_crash` — 60-step synthetic; pv > 0 throughout; final cash + holdings sensible
- **PATTERN:** Mirror `tests/test_trading_env.py` for fixture usage + docstring
  style. Use `synthetic_market_data` fixture from `conftest.py`.
- **GOTCHA:** When testing "holdings constant after first step," account for
  ONE step of trade activity (day 1 = initial allocation). Compare day 2 vs
  day 3, not day 1 vs day 2.
- **VALIDATE:** `.venv/bin/pytest tests/test_baselines.py -v`

### 5. CREATE `scripts/run_baselines.py`

- **IMPLEMENT:**
  ```python
  """CLI: run 3 baseline agents (buy-and-hold, equal-weight, random) on test
  split, save portfolio curves + holdings to results/baselines/, print summary.

  Usage:
      .venv/bin/python scripts/run_baselines.py
      .venv/bin/python scripts/run_baselines.py --split val --seed 0
  """
  from __future__ import annotations
  import argparse
  import logging
  import sys
  from pathlib import Path
  import pandas as pd
  from src import config
  from src.baselines import (
      BuyAndHold, EqualWeightRebalance, RandomAgent, run_backtest,
  )
  from src.env_data_loader import load_market_data
  from src.trading_env import VNTradingEnv

  RESULTS_DIR = config.PROJECT_ROOT / "results" / "baselines"


  def main() -> int:
      logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
      p = argparse.ArgumentParser()
      p.add_argument("--split", default="test", choices=["train", "val", "test", "full"])
      p.add_argument("--seed", type=int, default=42)
      args = p.parse_args()

      md = load_market_data(args.split)
      summary_rows = []
      for ctor in (BuyAndHold, EqualWeightRebalance, _make_random):
          env = VNTradingEnv(md)
          agent = ctor(env) if ctor is _make_random else ctor()
          result = run_backtest(env, agent, seed=args.seed)
          _write(result)
          summary_rows.append({
              "agent": result.agent_name,
              "n_steps": result.n_steps,
              "total_log_r": round(result.total_log_return, 4),
              "final_pv": int(result.final_pv),
              "cumulative_return": round(
                  result.final_pv / float(config.INITIAL_CAPITAL) - 1, 4
              ),
          })

      print(f"\n=== Baselines on split={args.split} seed={args.seed} ===")
      print(pd.DataFrame(summary_rows).to_string(index=False))
      print(f"\nArtifacts: {RESULTS_DIR}/")
      return 0


  def _make_random(env: VNTradingEnv) -> RandomAgent:
      return RandomAgent(env)


  def _write(result) -> None:
      d = RESULTS_DIR / result.agent_name
      d.mkdir(parents=True, exist_ok=True)
      result.portfolio_curve.to_parquet(d / "portfolio_curve.parquet", engine="pyarrow", compression="snappy")
      result.holdings_curve.to_parquet(d / "holdings.parquet", engine="pyarrow", compression="snappy")
      print(f"wrote {result.agent_name}: {result.n_steps} steps, log-r={result.total_log_return:.4f}, pv={result.final_pv:.0f}")


  if __name__ == "__main__":
      sys.exit(main())
  ```
- **PATTERN:** Mirror `scripts/fetch_data.py` + `scripts/fetch_news.py`
  argparse + logging shape.
- **GOTCHA:** `_make_random` factory because RandomAgent needs env at
  construction (D6). The other 2 baselines take no args. Don't try to
  unify the constructor signatures.
- **VALIDATE:** `.venv/bin/python scripts/run_baselines.py --split test`
  → exit 0, prints 3-row summary, writes 6 parquets (3 agents × 2 files).

---

## TESTING STRATEGY

### Unit Tests (10 new)

`tests/test_baselines.py` — Protocol + 3 agents + runner. Uses
`synthetic_market_data` fixture from `conftest.py` so tests are
network-free + parquet-free.

Total after PKG-4: 68 (PKG-0/1/2/3) + 10 = **78 tests**.

### Integration Test (manual, in PR description)

Real `test` split (248 sessions, 5 VN30 tickers):
- BuyAndHold: hold equal-weight from session 1 → final pv reflects VN30
  test-period market return
- EqualWeightRebalance: ~12 rebalance days (1 per calendar month) → small
  fee drag vs BuyAndHold
- RandomAgent: ~248 trades × ~0.4% round-trip fee ≈ -32% drag (matches
  PKG-3 smoke test number)

PR description quotes summary table + cumulative_return per agent.

### Edge Cases Explicitly Covered

| # | Edge case | Test |
|---|-----------|------|
| 1 | Month-change rebalance fires correctly | `test_equal_weight_rebalances_on_month_change` |
| 2 | First step (last_month=None) initializes | `test_equal_weight_first_call_initializes` |
| 3 | RandomAgent reproducibility via env RNG | `test_random_agent_uses_env_rng` |
| 4 | BuyAndHold holdings don't change after step 1 | `test_buy_and_hold_holdings_constant_after_first_step` |
| 5 | Schema of portfolio_curve frame | `test_run_backtest_portfolio_curve_schema` |
| 6 | run_backtest reproducibility same seed | `test_run_backtest_reproducible_same_seed` |
| 7 | Full episode no NaN/crash | `test_buy_and_hold_full_episode_no_crash` |
| 8 | Agent satisfies Protocol | `test_agent_protocol_runtime_check` |

### Edge Cases NOT Covered (deferred)

- **Metrics computation** (Sharpe, MDD, turnover) — PKG-10 owns.
- **VN-Index benchmark plot** — PKG-13 frontend owns; PKG-4 just prints
  cumulative_return text.
- **Multi-seed variance study** — PRD §4 ❌ nice-to-have.
- **Equal-weight target > 0.20 explorations** — locked at 0.19 per D4.

---

## VALIDATION COMMANDS

### Level 1: Syntax & Style

```bash
.venv/bin/ruff check src/ tests/ scripts/
```

### Level 2: Unit Tests

```bash
.venv/bin/pytest tests/ -v
# Expected: 78 passed (68 existing + 10 new)
```

### Level 3: Real-data E2E

```bash
.venv/bin/python scripts/run_baselines.py --split test --seed 42
# Expected: exit 0, summary table printed, 6 parquet files under results/baselines/
ls -la results/baselines/*/
```

### Level 4: Schema sanity

```bash
.venv/bin/python <<'PY'
import pandas as pd
for agent in ("buy_and_hold", "equal_weight", "random"):
    pv = pd.read_parquet(f"results/baselines/{agent}/portfolio_curve.parquet")
    h = pd.read_parquet(f"results/baselines/{agent}/holdings.parquet")
    assert list(pv.columns) == ["date","agent_name","portfolio_value","cash","w_VCB","w_FPT","w_HPG","w_VIC","w_VNM"], pv.columns
    assert list(h.columns) == ["date","agent_name","h_VCB","h_FPT","h_HPG","h_VIC","h_VNM"], h.columns
    print(f"{agent}: pv={pv.shape}, holdings={h.shape}, final_pv={pv['portfolio_value'].iloc[-1]:.0f}")
PY
```

### Level 5: Regression

```bash
.venv/bin/pytest tests/test_trading_env.py tests/test_env_data_loader.py -v
# 23 prior env tests still pass
```

---

## ACCEPTANCE CRITERIA

Mirrors GitHub Issue #5:

- [ ] Cả 3 agent (buy_and_hold, equal_weight, random) chạy hết test period 248 sessions không crash
- [ ] Portfolio curve parquet đúng schema (D5)
- [ ] ≥ 1 holding luôn > 0 trong BuyAndHold + EqualWeight (sanity)
- [ ] Cumulative return mỗi agent in ra console
- [ ] 10 tests pass; 78 total; ruff clean
- [ ] PR description chứa summary table 3 agents
- [ ] Người 2 verify: spot-check 1 rebalance day cho EqualWeight (month-1 → month-2 transition trong test period)

---

## COMPLETION CHECKLIST

- [ ] Pre-implementation spike chạy thành công, output paste vào PR
- [ ] `src/agent_base.py` + `src/baselines.py` + `tests/conftest.py` + `tests/test_baselines.py` + `scripts/run_baselines.py` đã write
- [ ] 10 tests pass; ruff clean
- [ ] `scripts/run_baselines.py --split test` exits 0
- [ ] 6 parquet files under `results/baselines/` (gitignored)
- [ ] PR mở với title `PKG-4: Baselines + random-agent E2E (Phase 1 complete)`, body `Closes #5`
- [ ] Phase 1 milestone announced — Phase 2 packages (PKG-5 LLM core, PKG-9 DDPG) unblocked

---

## NOTES

### Design decisions worth flagging in PR

1. **`src/agent_base.py` separate from `src/agents/__init__.py`** — latter
   is PKG-S serialized; PKG-4 stays atomic by keeping Protocol in own file.
2. **Equal-weight target 0.19, not 0.20** — 5% cash buffer absorbs fee +
   lot-100 drift. Document trong module docstring.
3. **RandomAgent uses env's np_random** — single RNG source matches PKG-3
   reproducibility invariant. Avoids dual-RNG sync bug class.
4. **Mini backtest runner stays local to baselines.py** — PKG-10 will ship
   fuller version. Avoid premature abstraction; copy when (if) PKG-10 needs
   a starting point.
5. **conftest.py introduced** — gradually deduplicate fixture code; current
   PKG-4 only depends on synthetic_market_data, but PKG-5+/PKG-9+ tests will
   reuse it.
6. **Parquet output schema locked** — column names use `w_<TICKER>` and
   `h_<TICKER>` with config.TICKERS order. PKG-10 metric runner + PKG-13
   frontend depend on this.

### Risks specific to PKG-4

| # | Risk | Likelihood | Mitigation |
|---|------|-----------|------------|
| 1 | Agent protocol changes after PKG-6+ ships | M | Keep Protocol minimal — only `name` + `decide(obs, info)`. Easier to extend than shrink. |
| 2 | Equal-weight cash buffer too tight | L | Target 0.19 gives 5% buffer; PKG-3 fee asymmetry test verified 0.4% round-trip drag |
| 3 | conftest.py change breaks existing test_trading_env.py | M | Move fixture cautiously: add to conftest.py FIRST without removing from test_trading_env.py; verify both pass; then deduplicate in a follow-up. **For PKG-4 PR: leave test_trading_env.py untouched**, just add to conftest. |
| 4 | results/baselines/ paths conflict with PKG-10 | L | PKG-10 plan should consume same paths; document in PR. |
| 5 | EqualWeightRebalance fires twice on month-change boundary | L | `_last_month` check prevents — explicit test guards. |

### Khi gặp blocker

- Pre-implementation spike fail → bug in PKG-3 env, not PKG-4. Halt + open
  issue against PKG-3.
- BuyAndHold holdings drift sau ngày 1 → env's `_execute_with_vn_rules` re-runs
  the lot-100 floor mỗi step; same target_weights → same target_shares → delta
  = 0 → no trade. If trades happen, check `_clean_action` clamp/normalize path.
- EqualWeightRebalance rebalance vào sai ngày → calendar month detection issue;
  verify `pd.Timestamp(info["date"]).month` matches expected.
- RandomAgent reproducibility fail → env.np_random not seeded before agent
  constructed; constructor must run AFTER `env.reset(seed=...)`.

### Agent protocol stability

D1-D2 locks `decide(obs: np.ndarray, info: dict) -> np.ndarray`. Any future
package can ADD optional kwargs (e.g. `**kwargs` for backwards-compat) but
cannot REMOVE existing positional args. This contract survives until PKG-S.

### Phase 1 completion

Sau PKG-4 merged:
- Phase 1 (data + env + baselines) DONE — 5/18 packages
- Phase 2 (agents + backtest) starts; PKG-5 (LLM core) + PKG-9 (DDPG) +
  PKG-6/7 (zero-shot, single-agentic) chạy song song có thể
- Person 1 có baselines numbers cho report draft
- Person 2 có full stack để verify lookahead bias trên 1 PR thực

---

## Confidence Score

**8.0/10** for one-pass implementation.

Subtract:
- −1.0 conftest.py fixture move có thể impact existing test_trading_env.py
  nếu naming collision (mitigated by D3 strategy: ADD only, don't remove)
- −0.5 RandomAgent + env.np_random ordering nhạy cảm; nếu agent constructed
  trước env.reset, sees uninitialized RNG
- −0.5 schema lock decisions D5 phải match PKG-10/13 future consumers; nếu
  conflict, retroactive rename trên parquet column names

Add back:
- +1.0 PKG-3 patterns established rất rõ; PKG-4 chủ yếu glue code
- +0.5 baseline logic đơn giản (cached weights, monthly month-detect)
- +0.5 fixture đã có sẵn trong tests/test_trading_env.py, chỉ cần move

PKG-4 chỉ đáng ½ ngày như TASKS.md estimated.
