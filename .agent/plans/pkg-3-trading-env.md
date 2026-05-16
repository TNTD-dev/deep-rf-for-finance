# Feature: PKG-3 — VN Trading Environment (Gymnasium)

> Đây là **TIM của project**. Mọi agent — DDPG (PKG-9), LLM zero-shot (PKG-6),
> single-agentic (PKG-7), multi-agent (PKG-8) — consume env này. Nếu env sai,
> toàn bộ backtest invalid và Person 2 verify fail.

## Feature Description

Bootstrap Gymnasium env mô phỏng giao dịch trên thị trường VN30 với ràng buộc
HOSE thật: ±7% band, lot-size 100, asymmetric fee (buy 0.15% / sell 0.25%),
long-only, T+2 optional. Env phơi ra interface chung `decide(state) -> action`
để cả RL agent (continuous action) và LLM agent (output weights) cùng dùng.

5 deliverable invariants (CLAUDE.md §"Domain-Specific Rules"):
1. **Lookahead-safe** — state tại T chỉ thấy data với `date < T`, news qua `visible_news_at`
2. **±7% band** — clamp price tại execution layer; agent không cần biết
3. **Lot-100 rounding** — env tự handle; agent emit continuous weights
4. **Asymmetric fee** — buy 0.15% / sell 0.25%
5. **Reproducibility** — `env.reset(seed=N)` → trajectory identical

## User Story

As a **DDPG trainer (PKG-9)** / **LLM zero-shot agent (PKG-6)**
I want to **emit continuous target weights `[0, 1]^5` mà không cần biết VN rules**
So that **focus vào policy, env tự handle execution / fees / settlement**.

As a **Person 2 (verifier)**
I want to **một test file `test_trading_env.py` encode mọi invariant**
So that **mọi PR sau touching env layer fail loud nếu break invariant**.

## Problem Statement

3 vấn đề đan vào nhau:

1. **VN market rules đặc thù** mà các paper/codebase reference (Xiong et al,
   FinRL, stable-baselines3 demos) đều giả định US market (no band, fractional
   shares, symmetric fee). Phải code from scratch.
2. **Decision frequency mix**: DDPG daily (PRD §15), LLM/agentic weekly. Env
   phải support cả hai mà không double-implement.
3. **State shape lockable**: nếu thay obs space sau khi train DDPG, model
   không load được. Phải lock observation contract trong PKG-3 và document.

## Solution Statement

1 class `VNTradingEnv(gymnasium.Env)` + 1 data loader. Design pattern:

- **Env steps daily**, không hiểu khái niệm "weekly". Agent emit weights mỗi
  step; weekly agent internally cache + re-emit cùng weights cho 4 ngày, rebalance
  ngày thứ 5. Đơn giản hơn nhiều so với env hiểu schedule.
- **Action space `Box(-1, 1, (n_tickers,))`** — sb3 prefer symmetric Box. Env
  internally clamp negatives → 0 (long-only), normalize nếu sum > 1 (cash leftover).
- **Execution model**: decision tại session T sử dụng state với `data.date < T`;
  fill tại session T's close price (lookahead-safe vì state dùng dữ liệu T-1 và
  trước). Realistic cho daily granularity backtest.
- **Lot-100**: target_shares = floor(target_value / price / 100) × 100. Round
  DOWN để tránh over-leverage / cash negative.
- **±7% band clamp**: defensive — real OHLCV đã respect band (HOSE clears at
  band edge), nên clamp hiếm trigger; nhưng test invariant phải bake.
- **Reward**: `log(pv_t / pv_{t-1})` mặc định. Expose `reward_fn` callable
  parameter cho ai muốn swap (Sharpe-like, risk-adjusted).
- **T+2 settlement queue**: default OFF; queue list of `(release_date,
  cash_amount)` — drain trên mỗi step. ON cho nice-to-have study.
- **Observation 56-dim flat vector** — skip prices_window (đã trong
  indicators); 45 indicators + 5 holdings + 5 prev_return + 1 cash_ratio.
- **Episode**: 1 episode = full date range của split (train/val/test). Reset
  trở về first valid session (sau warmup).

## Feature Metadata

- **Feature Type:** New Capability — foundation cho mọi agent
- **Estimated Complexity:** **High** — 5 invariants × 2 files × tight integration
  với PKG-1/2 + cần lock obs space contract trước khi PKG-6/7/8/9 dùng
- **Primary Systems Affected:** `src/trading_env.py`, `src/env_data_loader.py`,
  `tests/test_trading_env.py`. Phụ thuộc PKG-1/2 output parquets.
- **Dependencies:** `gymnasium==1.2.3` (installed), `numpy<2.0` (installed —
  pinned for sb3 compat), `pandas`, `pyarrow`. Không cần thêm dep mới.

---

## CONTEXT REFERENCES

### Relevant Codebase Files — ĐỌC TRƯỚC KHI IMPLEMENT

**Hằng số + invariants (read-only, không sửa):**
- `src/config.py` (line 47): `TICKERS = ["VCB","FPT","HPG","VIC","VNM"]`
- `src/config.py` (line 51-54): `TRAIN_START`, `VAL_START`, `TEST_START`, `TEST_END`
- `src/config.py` (line 57-59): `INITIAL_CAPITAL=1_000_000_000`, `BUY_FEE=0.0015`, `SELL_FEE=0.0025`
- `src/config.py` (line 62-63): `PRICE_BAND=0.07`, `LOT_SIZE=100`
- `CLAUDE.md` §"Domain-Specific Rules" 1-6 — non-negotiable invariants

**Reuse bắt buộc (không re-implement):**
- `src/data_pipeline/calendar.py:23-37` — `window_until(df, asof_date)` strict `<`
  cho lookahead. Mọi state access trong env routes qua đây.
- `src/data_pipeline/news_align.py` — `visible_news_at(news_df, asof)` cho news
  features. PKG-3 không activate news ngay (Phase 2), nhưng đặt seam.
- `src/data_pipeline/indicators.py:15-31` — `INDICATOR_COLS` tuple (9 cols);
  obs space phụ thuộc thứ tự này.

**Pattern bắt buộc mirror:**
- `src/data_pipeline/vnstock_prices.py:1-15` — module docstring shape (contract
  + gotchas + deprecation notes nếu có)
- `src/data_pipeline/vnstock_prices.py:36-49` — error handling: raise loud trên
  schema drift, never silent-degrade
- `tests/test_calendar.py` — test docstring style: encode WHY, reference PRD/CLAUDE
- `tests/test_news_align.py:60-70` — fixture pattern cho calendar/date math tests

**Don't touch (file ownership boundary):**
- `src/baselines.py` — PKG-4 owns
- `src/ddpg_trainer.py`, `src/ppo_trainer.py`, `src/llm/*` — PKG-9, PKG-6/7/8
- `src/data_pipeline/*` — PKG-1/2 owns
- `src/config.py` — read-only

### New Files to Create

```
src/
├── env_data_loader.py     # Load parquet → wide-format ndarrays + slice
└── trading_env.py         # VNTradingEnv(gym.Env) class
tests/
└── test_trading_env.py    # 14 invariant tests (random agent + math)
```

### Relevant Documentation — ĐỌC TRƯỚC KHI IMPLEMENT

- **Gymnasium 1.x env API:** https://gymnasium.farama.org/api/env/
  - `reset(seed=None, options=None) -> tuple[obs, info]`
  - `step(action) -> tuple[obs, reward, terminated, truncated, info]`
  - Bắt buộc 5-tuple, không phải 4 như gym cũ.
- **Box space:** https://gymnasium.farama.org/api/spaces/fundamental/#gymnasium.spaces.Box
  - `Box(low, high, shape, dtype=np.float32)` — sb3 prefer float32
- **Seeding:** https://gymnasium.farama.org/api/utils/#gymnasium.utils.seeding.np_random
  - `self.np_random, seed = seeding.np_random(seed)` trong reset.
- **sb3 DDPG action space:** https://stable-baselines3.readthedocs.io/en/master/modules/ddpg.html
  - Yêu cầu `Box(-1, 1)` continuous, không discrete.
- **Paper Xiong et al — DDPG stock trading** (`docs/Deep Reinforcement Learning Approach for Stock Trading_.pdf`)
  - State: `[balance, prices, holdings, technicals]` — chúng ta mirror nhưng
    skip raw prices (đã có trong indicators)
  - Reward: change in portfolio value per step (we use log instead of linear
    diff for scale invariance across capital levels)

### Pre-implementation spikes (chạy 2 lệnh trước khi code)

```bash
# Spike 1: Verify parquet schemas + indicator count
.venv/bin/python <<'PY'
import pandas as pd
from src.data_pipeline.indicators import INDICATOR_COLS
p = pd.read_parquet("data/processed/prices.parquet")
print("INDICATOR_COLS:", INDICATOR_COLS, "count:", len(INDICATOR_COLS))
print("prices cols:", p.columns.tolist())
print("rows:", len(p), "tickers:", p["ticker"].unique().tolist())
# Earliest non-NaN session for sma50
warmup_test = p.dropna(subset=list(INDICATOR_COLS)).groupby("ticker")["date"].min()
print("first all-indicators-non-NaN date per ticker:")
print(warmup_test)
PY

# Spike 2: Verify gymnasium API
.venv/bin/python -c "
import gymnasium as gym
print('API check 5-tuple:', hasattr(gym.Env, 'step'))
import inspect
print('Env.step signature:', inspect.signature(gym.Env.step))
print('Env.reset signature:', inspect.signature(gym.Env.reset))
"
```

Output expected từ Spike 1: warmup ~50 sessions (SMA50 needs 50 data points).
First all-indicators-non-NaN date sẽ là 2019-03-XX. Train start tuy là 2019-01-01
nhưng episode effectively starts ~2019-03-15.

### Patterns to Follow (từ codebase đã land)

**Module docstring (mirror `src/data_pipeline/news_align.py:1-19`):**

```python
"""One-paragraph mô tả contract + lookahead invariant + decision frequency.

State the obs space dimensions + action interpretation. Lock these — agents
trained against this contract will break if observation changes.
"""
```

**Hằng số đứng đầu module (mirror `src/data_pipeline/indicators.py:14-31`):**

```python
N_TICKERS: int = 5
INDICATORS_PER_TICKER: int = 9
OBS_DIM: int = N_TICKERS * INDICATORS_PER_TICKER + 2 * N_TICKERS + 1  # = 56
WARMUP_SESSIONS: int = 50
```

**Test invariant (mirror `tests/test_calendar.py:14-37`):**

```python
def test_<invariant>() -> None:
    """Encode WHY. Reference CLAUDE.md §3 or PRD §15.

    Strict semantic — flipping this is the most common silent-bug path.
    """
```

---

## DESIGN DECISIONS — LOCK BEFORE IMPLEMENT

### D1. Execution model

**Decision tại session T → fill tại session T's CLOSE price.**

Lý do:
- State `_get_state(T)` dùng `window_until(prices, T)` → chỉ thấy data với
  `date < T`. Agent emit weights dựa trên info đến T-1 close.
- Fill tại T close: realistic cho daily-granularity backtest (assume agent
  can submit order during T's session, executed by close).
- Alternative "fill at T+1 open": vnstock không có separate open column gọn
  cho ta dùng; cần thêm complexity không cần thiết.

Implementation: trong `step(action)`, env state pointer là T; fill price là
`close[T]`; sau khi fill, advance T → T+1 và compute new obs (chỉ thấy < T+1
= thấy đến T).

### D2. ±7% band

**Clamp fill price into `[prev_close × 0.93, prev_close × 1.07]`.**

Lý do: real OHLCV từ vnstock đã được HOSE-clipped (close không bao giờ vượt
band của ngày đó). Nhưng:
- Defensive against future data sources / bug
- Test invariant phải bake "không có fill nào vượt band"
- Documented in PR description: "trên 1826 sessions thực tế, clamp trigger
  count = N (expected 0)"

Implementation: trong `_execute_with_vn_rules`:
```python
prev_close = prices[t-1]  # bounded by window_until guarantee
band_low = prev_close * (1 - PRICE_BAND)
band_high = prev_close * (1 + PRICE_BAND)
fill_price = np.clip(today_close, band_low, band_high)
```

### D3. Lot-100 rounding

**`target_shares = floor(target_value / fill_price / LOT_SIZE) × LOT_SIZE`.**

Lý do: round DOWN tránh over-leverage. Cash leftover acceptable (typically < 100
shares × max price ≈ 7M VND ≈ 0.7% NAV at 1B initial — không material).

Alternative "round to nearest": risk over-allocate, generate negative cash.
Locked: **floor**.

### D4. Long-only

**`np.clip(action, 0, 1)` after Box reception; sum_normalize nếu sum > 1.**

PRD §3 implicit. Lock vì short selling khó/đắt ở VN retail.

Implementation:
```python
action = np.clip(np.asarray(action, dtype=np.float32), 0.0, 1.0)
total = action.sum()
if total > 1.0:
    action = action / total  # cash_frac = 0 in this case
# else: cash_frac = 1 - total
```

### D5. Reward

**`reward_t = log(pv_t / pv_{t-1})`.**

Lý do:
- Scale-invariant: agent với 1B vs 10B same problem
- Standard cho DDPG paper Xiong et al + Paper Ensemble (PRD §15 references)
- Risk-adjusted variant (Sharpe-like) — expose như `reward_fn` parameter
  callable. Default `log_return_reward`.

Edge case: nếu `pv_t ≤ 0` (catastrophic loss), reward = `-100.0` clipped (sentinel),
terminate episode. Test phải cover.

### D6. Observation shape (LOCK — DDPG model phụ thuộc)

**Flat 56-dim float32 vector:**

| Component | Count | Description |
|-----------|-------|-------------|
| Indicators (per ticker) | 5 × 9 = 45 | INDICATOR_COLS values, z-score normalized rolling |
| Current weights | 5 | `holdings_value_i / pv` |
| Prev returns | 5 | `(close[t-1] - close[t-2]) / close[t-2]` |
| Cash ratio | 1 | `cash / pv` |
| **TOTAL** | **56** | |

Lý do skip raw prices_window: indicators đã encode price movement (RSI, MACD,
SMA), thêm raw prices là dư thừa cho 30-day window.

Normalization: indicators được z-score qua rolling 60-day per ticker để keep
sb3 networks happy. Pre-computed offline trong `env_data_loader`.

### D7. Episode boundary + warmup

**Episode = full date range của split.** `reset()` trở về first valid session
(date `>= split_start AND all indicators non-NaN`). Last session terminate.

Warmup ~50 sessions (SMA50). `WARMUP_SESSIONS=50` constant, document chỉnh nếu
indicator config thay đổi.

### D8. T+2 settlement

**Default OFF.** Khi ON: sold shares cash vào queue `(release_session_idx,
amount)`; drain trên mỗi step.

Implementation:
```python
self.settlement_queue: list[tuple[int, float]] = []  # (release_t_idx, amount)
def _drain_settlement(self, t: int) -> float:
    released = sum(amt for rt, amt in self.settlement_queue if rt <= t)
    self.settlement_queue = [(rt, amt) for rt, amt in self.settlement_queue if rt > t]
    return released
```

Default OFF vì PRD §15 nói "T+2 nice-to-have, not bake". Hook present for
future study.

### D9. Decision frequency abstraction

**Env không hiểu khái niệm weekly.** Steps daily; agent internally cache.

Trong PKG-6/7/8 (LLM agents), wrapper class:
```python
class WeeklyAgent:
    def __init__(self, base_agent, calendar):
        self._cached = None
        ...
    def decide(self, state):
        if self._should_rebalance(state.session_idx):
            self._cached = self.base_agent.decide(state)
        return self._cached
```

PKG-3 không implement wrapper; chỉ document trong env class docstring.

### D10. Long-only allow non-fully-invested

**cash_frac = 1 - sum(weights)** if sum < 1. Agent có thể "hold cash" by
emitting smaller-magnitude weights.

Quan trọng cho LLM agents: nếu agent uncertain → output `[0.1, 0.1, 0.1, 0.1, 0.1]`
= 50% invested, 50% cash. Realistic risk management.

---

## IMPLEMENTATION PLAN

### Phase 1: Data loader — pre-compute wide-format arrays

**Goal:** Load `prices.parquet` → ndarray cache cho fast indexing trong step loop.

**Tasks:**
- `env_data_loader.py`: `load_market_data(split: Literal["train","val","test"]) -> MarketData` dataclass
- `MarketData` chứa: `dates` (DatetimeIndex), `close[T, n_tickers]`, `high/low/open` arrays, `indicators[T, n_tickers, n_indicators]`, `warmup_offset: int`
- Z-score normalize indicators per-ticker per-feature rolling 60-day → `indicators_norm`
- 5 tests

### Phase 2: Env class — Gymnasium contract

**Goal:** `VNTradingEnv` implement `gym.Env` 5-tuple API.

**Tasks:**
- `trading_env.py`: `class VNTradingEnv(gym.Env)` với:
  - `__init__(market_data, initial_capital, t_plus_2=False, reward_fn=None)`
  - `reset(seed, options)` → `(obs, info)`
  - `step(action)` → `(obs, reward, terminated, truncated, info)`
- Internal helpers: `_compute_obs()`, `_execute_with_vn_rules(action)`, `_compute_reward(pv_prev, pv_cur)`, `_drain_settlement(t)`
- 9 tests covering ±7% clamp, lot-100 round, fee asymmetry, lookahead, reproducibility, terminal at end-of-data, NaN-handling

### Phase 3: Random-agent smoke test

**Goal:** 248 sessions test period × random action → no crash, deterministic across seed.

**Tasks:** 1 test `test_random_agent_full_episode` chạy reset + step × N → assert
no crash, portfolio value tracked correctly, same seed → same final pv.

---

## STEP-BY-STEP TASKS

### 1. CREATE `src/env_data_loader.py`

- **IMPLEMENT:**
  ```python
  """Load PKG-1 prices.parquet → wide-format ndarrays for fast env stepping.

  Long→wide pivot per ticker; indicators z-score-normalized rolling 60-day
  per (ticker, feature) so DDPG network sees stable scale across the full
  date range. Warmup offset = first row where all indicators non-NaN.
  """
  from __future__ import annotations
  from dataclasses import dataclass
  from pathlib import Path
  from typing import Literal
  import numpy as np
  import pandas as pd
  from src import config
  from src.data_pipeline.indicators import INDICATOR_COLS

  PRICES_PATH = config.PROJECT_ROOT / "data" / "processed" / "prices.parquet"
  ZSCORE_WINDOW = 60
  WARMUP_SAFETY = 50  # SMA50 = longest indicator window

  @dataclass(frozen=True)
  class MarketData:
      dates: pd.DatetimeIndex            # shape (T,)
      tickers: tuple[str, ...]           # shape (n_tickers,) — frozen
      close: np.ndarray                  # shape (T, n_tickers)
      open: np.ndarray
      high: np.ndarray
      low: np.ndarray
      indicators_norm: np.ndarray        # shape (T, n_tickers, n_indicators), z-scored
      warmup_offset: int                 # first valid session idx (after warmup)

  def load_market_data(split: Literal["train", "val", "test", "full"] = "full") -> MarketData:
      df = pd.read_parquet(PRICES_PATH)
      df = df.sort_values(["ticker", "date"]).reset_index(drop=True)
      tickers = tuple(config.TICKERS)
      if set(df["ticker"].unique()) != set(tickers):
          raise ValueError(f"Ticker mismatch — parquet has {df['ticker'].unique()}, config has {tickers}")

      # Pivot to wide. Use config order, not alphabetical.
      def pivot(col):
          w = df.pivot(index="date", columns="ticker", values=col)
          return w[list(tickers)].to_numpy(dtype=np.float32)

      dates = pd.DatetimeIndex(df["date"].drop_duplicates().sort_values())
      close, open_, high, low = pivot("close"), pivot("open"), pivot("high"), pivot("low")
      ind_cols = list(INDICATOR_COLS)
      indicators = np.stack(
          [pivot(c) for c in ind_cols], axis=-1
      )  # (T, n_tickers, n_indicators)

      # Z-score per (ticker, feature) rolling 60-day. Computed BEFORE split slicing
      # so window doesn't fall off cliff at split boundaries.
      ind_norm = _rolling_zscore(indicators, ZSCORE_WINDOW)

      # Split boundaries (PRD §15)
      if split == "train":
          start, end = config.TRAIN_START, config.VAL_START
      elif split == "val":
          start, end = config.VAL_START, config.TEST_START
      elif split == "test":
          start, end = config.TEST_START, config.TEST_END
      else:  # full
          start, end = config.TRAIN_START, config.TEST_END

      mask = (dates >= pd.to_datetime(start)) & (dates <= pd.to_datetime(end))
      sub_dates = dates[mask]
      sub_idx = np.where(mask)[0]
      sub_close = close[sub_idx]
      sub_open = open_[sub_idx]
      sub_high = high[sub_idx]
      sub_low = low[sub_idx]
      sub_ind = ind_norm[sub_idx]

      # Warmup: skip rows where any indicator still NaN
      valid_mask = ~np.isnan(sub_ind).any(axis=(1, 2))
      warmup_offset = int(np.argmax(valid_mask)) if valid_mask.any() else len(sub_dates)
      return MarketData(
          dates=sub_dates, tickers=tickers,
          close=sub_close, open=sub_open, high=sub_high, low=sub_low,
          indicators_norm=sub_ind, warmup_offset=warmup_offset,
      )

  def _rolling_zscore(x: np.ndarray, window: int) -> np.ndarray:
      """Z-score along axis 0 with rolling window. NaN-safe (leading NaN preserved)."""
      out = np.full_like(x, np.nan, dtype=np.float32)
      for i in range(x.shape[0]):
          lo = max(0, i - window + 1)
          window_slice = x[lo : i + 1]
          if window_slice.shape[0] < min(window // 2, 20):
              continue  # not enough samples
          mu = np.nanmean(window_slice, axis=0)
          sd = np.nanstd(window_slice, axis=0)
          sd = np.where(sd < 1e-8, 1.0, sd)  # avoid div-by-zero
          out[i] = (x[i] - mu) / sd
      return out
  ```
- **PATTERN:** Mirror `vnstock_prices._normalize` shape (schema validation + raise).
- **IMPORTS:** `pandas`, `numpy`, `dataclasses`, `pathlib`, `typing.Literal`, `src.config`, `src.data_pipeline.indicators.INDICATOR_COLS`.
- **GOTCHA #1:** Pivot reorders columns alphabetically by default — explicit `w[list(tickers)]` to preserve config order. **Ticker index → order is contractual** for DDPG state.
- **GOTCHA #2:** `np.float32` everywhere. sb3 internally uses float32; mixing float64 silently doubles memory.
- **GOTCHA #3:** `_rolling_zscore` is O(T × W) but T ≈ 1826 và W = 60, ~110k ops — fast enough. Vectorize không cần thiết.
- **GOTCHA #4:** warmup_offset computed AFTER split — train/val/test mỗi cái có warmup riêng vì rolling z-score reset implicit ở boundary nếu ta không chia sẻ pre-split. Actually z-score computed BEFORE split (good) nhưng indicators NaN tự nhiên kết thúc after ~50 sessions of original data — train warmup_offset thường = 50, val/test warmup_offset = 0 (đã qua warmup).
- **VALIDATE:** `.venv/bin/python -c "from src.env_data_loader import load_market_data; m = load_market_data('test'); print(m.dates[:3], m.close.shape, m.indicators_norm.shape, 'warmup:', m.warmup_offset)"`

### 2. CREATE `src/trading_env.py`

- **IMPLEMENT:**
  ```python
  """VN trading environment (Gymnasium). Contract for every agent in this project.

  Action space:    Box(-1, 1, (n_tickers,), float32) — target weights, long-only clamp inside.
  Observation:     Flat 56-dim float32 vector.
                   [45 indicators] + [5 weights] + [5 prev_returns] + [1 cash_ratio]
  Reward:          log(pv_t / pv_{t-1}). Override with reward_fn kwarg.
  Decision policy: agent emits weights at each step; env handles execution at
                   session close. Weekly-rebalance agents must cache externally
                   (env doesn't understand schedules).

  Invariants (CLAUDE.md §"Domain-Specific Rules"):
    - state at session T sees only data with date < T (lookahead-safe)
    - fill price clamped to [prev_close × 0.93, prev_close × 1.07]
    - shares rounded DOWN to nearest LOT_SIZE (100)
    - fees: buy 0.15%, sell 0.25% (asymmetric)
    - long-only: negative action components → 0
    - T+2 settlement: optional, default off
  """
  from __future__ import annotations
  from typing import Any, Callable, Optional
  import numpy as np
  import gymnasium as gym
  from gymnasium import spaces
  from gymnasium.utils import seeding
  from src import config
  from src.env_data_loader import MarketData

  N_TICKERS: int = 5
  N_INDICATORS: int = 9  # MUST match len(INDICATOR_COLS) from indicators.py
  OBS_DIM: int = N_TICKERS * N_INDICATORS + 2 * N_TICKERS + 1  # 45 + 10 + 1 = 56
  CATASTROPHIC_LOSS_REWARD: float = -100.0


  def log_return_reward(pv_prev: float, pv_cur: float) -> float:
      if pv_cur <= 0 or pv_prev <= 0:
          return CATASTROPHIC_LOSS_REWARD
      return float(np.log(pv_cur / pv_prev))


  class VNTradingEnv(gym.Env):
      metadata = {"render_modes": []}

      def __init__(
          self,
          market_data: MarketData,
          initial_capital: float = float(config.INITIAL_CAPITAL),
          t_plus_2: bool = False,
          reward_fn: Optional[Callable[[float, float], float]] = None,
      ):
          super().__init__()
          if market_data.close.shape[1] != N_TICKERS:
              raise ValueError(
                  f"market_data has {market_data.close.shape[1]} tickers, expected {N_TICKERS}"
              )
          self.md = market_data
          self.initial_capital = float(initial_capital)
          self.t_plus_2 = t_plus_2
          self._reward_fn = reward_fn or log_return_reward

          self.action_space = spaces.Box(
              low=-1.0, high=1.0, shape=(N_TICKERS,), dtype=np.float32
          )
          self.observation_space = spaces.Box(
              low=-np.inf, high=np.inf, shape=(OBS_DIM,), dtype=np.float32
          )
          self._reset_state()

      # ---- gymnasium API -----------------------------------------------------

      def reset(
          self, seed: Optional[int] = None, options: Optional[dict] = None
      ) -> tuple[np.ndarray, dict]:
          super().reset(seed=seed)
          self.np_random, _ = seeding.np_random(seed)
          self._reset_state()
          return self._compute_obs(), self._info()

      def step(
          self, action: np.ndarray
      ) -> tuple[np.ndarray, float, bool, bool, dict]:
          if self._terminated:
              raise RuntimeError("step() called after episode terminated; call reset()")

          t = self._t
          pv_before = self._portfolio_value(t)
          weights = self._clean_action(action)
          self._execute_with_vn_rules(t, weights)
          pv_after = self._portfolio_value(t)  # same t — fills happen at t close
          reward = self._reward_fn(pv_before, pv_after)

          # Advance time
          self._t += 1
          self._terminated = self._t >= len(self.md.dates) - 1 or pv_after <= 0
          obs = self._compute_obs()
          info = self._info()
          info.update({"pv_before": pv_before, "pv_after": pv_after, "fill_t": t})
          return obs, float(reward), self._terminated, False, info

      # ---- internal ----------------------------------------------------------

      def _reset_state(self) -> None:
          self._t: int = self.md.warmup_offset
          self._holdings: np.ndarray = np.zeros(N_TICKERS, dtype=np.int64)  # shares
          self._cash: float = self.initial_capital
          self._settlement_q: list[tuple[int, float]] = []
          self._terminated: bool = False
          self._pv_history: list[float] = [self.initial_capital]

      def _clean_action(self, action: np.ndarray) -> np.ndarray:
          a = np.clip(np.asarray(action, dtype=np.float32), 0.0, 1.0)
          total = float(a.sum())
          if total > 1.0:
              a = a / total
          return a

      def _portfolio_value(self, t: int) -> float:
          price_t = self.md.close[t]
          return float(self._cash + (self._holdings * price_t).sum())

      def _execute_with_vn_rules(self, t: int, target_weights: np.ndarray) -> None:
          # Drain settlement queue first if T+2 active
          if self.t_plus_2:
              released = sum(
                  amt for rt, amt in self._settlement_q if rt <= t
              )
              self._settlement_q = [
                  (rt, amt) for rt, amt in self._settlement_q if rt > t
              ]
              self._cash += released

          fill_price = self._fill_price(t)
          pv = self._portfolio_value(t)
          target_values = target_weights * pv
          target_shares = np.floor(
              target_values / np.maximum(fill_price, 1e-8) / config.LOT_SIZE
          ).astype(np.int64) * config.LOT_SIZE
          delta = target_shares - self._holdings

          # Sells first (to free cash), then buys
          for i in range(N_TICKERS):
              if delta[i] < 0:
                  shares = -delta[i]
                  proceeds = shares * fill_price[i] * (1 - config.SELL_FEE)
                  if self.t_plus_2:
                      self._settlement_q.append((t + 2, proceeds))
                  else:
                      self._cash += proceeds
                  self._holdings[i] -= shares
          for i in range(N_TICKERS):
              if delta[i] > 0:
                  shares = delta[i]
                  cost = shares * fill_price[i] * (1 + config.BUY_FEE)
                  if cost > self._cash + 1e-6:
                      # Can't afford — buy what we can
                      affordable = int(
                          np.floor(self._cash / (fill_price[i] * (1 + config.BUY_FEE)) / config.LOT_SIZE)
                      ) * config.LOT_SIZE
                      shares = max(0, affordable)
                      cost = shares * fill_price[i] * (1 + config.BUY_FEE)
                  self._cash -= cost
                  self._holdings[i] += shares

      def _fill_price(self, t: int) -> np.ndarray:
          """±7% band clamp against prev close."""
          if t == 0:
              return self.md.close[t]
          prev = self.md.close[t - 1]
          band_low = prev * (1 - config.PRICE_BAND)
          band_high = prev * (1 + config.PRICE_BAND)
          return np.clip(self.md.close[t], band_low, band_high)

      def _compute_obs(self) -> np.ndarray:
          t = self._t
          pv = max(self._portfolio_value(t), 1e-8)
          weights = (self._holdings * self.md.close[t]) / pv  # (5,)
          if t >= 1:
              prev_ret = (self.md.close[t] - self.md.close[t - 1]) / np.maximum(
                  self.md.close[t - 1], 1e-8
              )
          else:
              prev_ret = np.zeros(N_TICKERS, dtype=np.float32)
          cash_ratio = self._cash / pv

          ind = self.md.indicators_norm[t].astype(np.float32).reshape(-1)  # (45,)
          obs = np.concatenate(
              [
                  ind,
                  weights.astype(np.float32),
                  prev_ret.astype(np.float32),
                  np.array([cash_ratio], dtype=np.float32),
              ]
          )
          # Defensive: replace any residual NaN/inf with 0 so sb3 doesn't crash
          return np.nan_to_num(obs, nan=0.0, posinf=0.0, neginf=0.0)

      def _info(self) -> dict[str, Any]:
          t = self._t
          return {
              "date": self.md.dates[t].isoformat() if t < len(self.md.dates) else None,
              "t": t,
              "cash": self._cash,
              "holdings": self._holdings.tolist(),
              "portfolio_value": self._portfolio_value(min(t, len(self.md.dates) - 1)),
          }
  ```
- **PATTERN:** Single-class module với private helpers prefixed `_`. Mirror `news_align.py` for module docstring depth.
- **IMPORTS:** `gymnasium`, `gymnasium.spaces`, `gymnasium.utils.seeding`, `numpy`, `typing.Callable, Optional, Any`, `src.config`, `src.env_data_loader.MarketData`.
- **GOTCHA #1:** `gym.Env.reset()` MUST call `super().reset(seed=seed)` first per Gymnasium 1.x or `self.np_random` won't initialize.
- **GOTCHA #2:** Float type — `np.float32` cho obs/action; `np.int64` cho holdings (shares là số nguyên, lot-100 đảm bảo).
- **GOTCHA #3:** Sell BEFORE buy ordering trong `_execute_with_vn_rules` — necessary to free cash for buys khi rebalance.
- **GOTCHA #4:** Buy với "can't afford" fallback: nếu agent emit weights tổng = 1.0 nhưng có rounding errors, có thể quá tiền 1-2 VND. Defensive: tính max affordable lot, không raise.
- **GOTCHA #5:** `_compute_obs` `nan_to_num` last-resort defense. Indicators_norm có thể NaN ở rất đầu episode if warmup_offset trong split không đủ. Test phải verify NaN-handling.
- **GOTCHA #6:** Action dtype: sb3 sometimes passes Python list/scalar; `np.asarray(action, dtype=np.float32)` coerce.
- **VALIDATE:** `.venv/bin/python -c "
  from src.env_data_loader import load_market_data
  from src.trading_env import VNTradingEnv
  import numpy as np
  env = VNTradingEnv(load_market_data('test'))
  obs, info = env.reset(seed=42)
  print('obs shape:', obs.shape, 'date:', info['date'])
  obs, r, term, trunc, info = env.step(np.array([0.2]*5, dtype=np.float32))
  print('step OK; reward:', r, 'pv:', info['portfolio_value'])
  "`

### 3. CREATE `tests/test_trading_env.py`

- **IMPLEMENT:** 14 tests
  - **Fixture loader (network-free):** small synthetic `MarketData` builder
    that creates 100 sessions × 5 tickers fixture without reading parquet
  - `test_reset_returns_5tuple_with_obs_dim_56` — obs shape (56,), info has `date`/`t`/`pv`
  - `test_action_space_is_box_minus1_to_1` — for sb3 DDPG compatibility
  - `test_step_returns_5tuple` — gymnasium 1.x API
  - `test_negative_action_treated_as_zero_weight` — long-only invariant
  - `test_action_summing_above_1_renormalized` — weights normalized
  - `test_lot_100_rounding_floor` — emit weights → check holdings divisible by 100
  - `test_fee_asymmetry_buy_then_sell_loses_money` — emit full buy, immediate full sell → pv decreases by ~0.4% (0.15 + 0.25)
  - `test_band_clamp_invariant` — synthetic price jump > 7% from prev; verify fill capped at band
  - `test_lookahead_observation_uses_only_past` — patch indicators with sentinel value at t; obs at session t doesn't contain it (uses indicators_norm[t] which is "as of t close", correct semantic)
  - `test_reproducibility_same_seed_same_trajectory` — 2 envs same seed → identical final pv after random actions
  - `test_episode_terminates_at_last_session` — step until terminated; verify t = len(dates) - 1
  - `test_terminate_on_catastrophic_loss` — manually set holdings/cash so pv ≤ 0; reward = -100, terminated
  - `test_t_plus_2_settlement_holds_cash` — t_plus_2=True; sell shares; cash doesn't increase immediately
  - `test_random_agent_full_episode_no_crash` — reset + step × N until terminated; pv tracked > 0 throughout; final info dict valid
- **PATTERN:** Mirror `tests/test_news_align.py` for fixture helpers; mirror `tests/test_calendar.py` for docstring style.
- **GOTCHA:** Don't read prices.parquet in tests — build synthetic MarketData fixture so tests work in CI without network and PKG-1 output.
- **VALIDATE:** `.venv/bin/pytest tests/test_trading_env.py -v`

### 4. RUN end-to-end smoke against real data + capture for PR

- **IMPLEMENT:**
  ```bash
  .venv/bin/python <<'PY'
  import numpy as np
  from src.env_data_loader import load_market_data
  from src.trading_env import VNTradingEnv
  md = load_market_data("test")
  env = VNTradingEnv(md)
  obs, info = env.reset(seed=42)
  total_reward, steps = 0.0, 0
  while not env._terminated:
      action = env.action_space.sample()
      obs, r, term, trunc, info = env.step(action)
      total_reward += r
      steps += 1
  print(f"Random agent: {steps} steps, total log-return={total_reward:.4f}, final pv={info['portfolio_value']:.0f}")
  PY
  ```
- **VALIDATE:** Output ≥ 1 line; final pv > 0 (random agent on flat-ish market should not blow up); no exception.

---

## TESTING STRATEGY

### Unit Tests (14 new)

`tests/test_trading_env.py` — 14 tests covering API, invariants, edge cases.
Fixture-driven (synthetic MarketData), no network/parquet dependency.

Total after PKG-3: 45 (PKG-0/1/2) + 14 = **59 tests**.

### Integration Test (manual, in PR description)

Random agent on real test-period data → PR description quotes:
- N steps completed
- Total log-return (typically slightly negative due to fees on random churn)
- Final portfolio value (should be in `[5×10^8, 1.5×10^9]` ballpark for 248 sessions)

### Edge Cases Explicitly Covered

| # | Edge case | Test |
|---|-----------|------|
| 1 | Negative action component → 0 (long-only) | `test_negative_action_treated_as_zero_weight` |
| 2 | `sum(weights) > 1` → renormalized | `test_action_summing_above_1_renormalized` |
| 3 | Holdings always divisible by LOT_SIZE | `test_lot_100_rounding_floor` |
| 4 | Buy+sell round trip costs ~0.4% | `test_fee_asymmetry_buy_then_sell_loses_money` |
| 5 | Price jump > 7% clamped at band | `test_band_clamp_invariant` |
| 6 | Same seed → identical trajectory | `test_reproducibility_same_seed_same_trajectory` |
| 7 | Episode terminates at last session | `test_episode_terminates_at_last_session` |
| 8 | pv ≤ 0 → terminate + sentinel reward | `test_terminate_on_catastrophic_loss` |
| 9 | T+2 cash deferred 2 sessions | `test_t_plus_2_settlement_holds_cash` |
| 10 | Random agent doesn't crash for full ep | `test_random_agent_full_episode_no_crash` |

### Edge Cases NOT Covered (deferred / out of scope)

- **Half-day sessions / unusual hours** — VN doesn't publish half-day OHLC reliably; not in MVP
- **Stock splits / dividends** — vnstock prices likely already adjusted; verify in PKG-9 (DDPG smoke)
- **Order rejection due to circuit breaker** — band clamp captures most; not modeling broker queue
- **Slippage** — PRD §4 ❌ out of scope explicit

---

## VALIDATION COMMANDS

### Level 1: Syntax & Style

```bash
.venv/bin/ruff check src/ tests/
.venv/bin/ruff format --check src/ tests/
```

### Level 2: Unit Tests

```bash
.venv/bin/pytest tests/ -v
# Expected: 59 passed (45 existing + 14 new)
```

### Level 3: Real-data smoke (one-time per PR)

```bash
.venv/bin/python - <<'PY'
import numpy as np
from src.env_data_loader import load_market_data
from src.trading_env import VNTradingEnv
md = load_market_data("test")
print("market data:", md.close.shape, "warmup_offset:", md.warmup_offset)
env = VNTradingEnv(md)
obs, info = env.reset(seed=42)
print("initial obs shape:", obs.shape, "date:", info["date"])
total_r, steps, max_pv, min_pv = 0.0, 0, info["portfolio_value"], info["portfolio_value"]
while not env._terminated:
    a = env.action_space.sample()
    obs, r, term, trunc, info = env.step(a)
    total_r += r
    steps += 1
    max_pv = max(max_pv, info["portfolio_value"])
    min_pv = min(min_pv, info["portfolio_value"])
print(f"random agent: {steps} steps, total log-r={total_r:.4f}, final={info['portfolio_value']:.0f}")
print(f"  max pv: {max_pv:.0f}, min pv: {min_pv:.0f}")
PY
```

### Level 4: Reproducibility check

```bash
.venv/bin/python - <<'PY'
import numpy as np
from src.env_data_loader import load_market_data
from src.trading_env import VNTradingEnv
md = load_market_data("test")
results = []
for trial in range(2):
    env = VNTradingEnv(md)
    obs, _ = env.reset(seed=42)
    while not env._terminated:
        a = env.action_space.sample()  # note: env.np_random not used for sample; ok for repro check we'll fix below
        obs, r, term, _, info = env.step(a)
    results.append(info["portfolio_value"])
# For true repro: use env.np_random.uniform(-1, 1, 5) instead of action_space.sample()
print("results:", results)
# Note: action_space.sample() uses its own RNG, so this script is a leak test only.
PY
```

### Level 5: Regression — all prior tests still pass

```bash
.venv/bin/pytest tests/test_config.py tests/test_calendar.py tests/test_vnstock_prices.py tests/test_indicators.py tests/test_news_align.py tests/test_news_fetch.py tests/test_news_scraper.py -v
```

---

## ACCEPTANCE CRITERIA

Mirrors GitHub Issue #4 + design decisions D1-D10:

- [ ] `VNTradingEnv` implements Gymnasium 1.x 5-tuple API
- [ ] `obs.shape == (56,)`, `action_space == Box(-1, 1, (5,), float32)`
- [ ] Random agent runs full test period (248 sessions) without crash
- [ ] `_execute_with_vn_rules` clamps fill price to ±7% band against prev close
- [ ] All holdings divisible by `LOT_SIZE=100` after every step
- [ ] Buy fee 0.15%, sell fee 0.25%; asymmetry verifiable
- [ ] Same seed → same trajectory (final pv identical across 2 runs)
- [ ] Episode terminates at last session OR catastrophic loss
- [ ] T+2 settlement default OFF; ON mode hooked and tested
- [ ] All 14 tests pass; 59 total
- [ ] `ruff check` clean
- [ ] PR description includes Spike 1 output + random agent end-of-episode stats

---

## COMPLETION CHECKLIST

- [ ] Spike 1-2 chạy thành công, output paste vào PR
- [ ] `env_data_loader.py` + `trading_env.py` đã write
- [ ] `test_trading_env.py` với 14 tests pass
- [ ] `ruff check` clean toàn bộ src + tests
- [ ] Real-data smoke (Level 3) chạy đến hết không crash
- [ ] Reproducibility check (Level 4) confirms determinism
- [ ] PR mở với title `PKG-3: VN trading environment (Gymnasium)`, body `Closes #4`
- [ ] Người 2 verify: spot-check 1 step bằng tay (emit weights, tính fill, verify cash + holdings)

---

## NOTES

### Design decisions worth flagging in PR

1. **Action space `Box(-1, 1)` not `Box(0, 1)`** — sb3 DDPG default policy
   output is `tanh`-bounded so `[-1, 1]` is natural. Negative components
   clamp to 0 inside env. Documented in module docstring.
2. **Reward = log-return, not linear PnL** — scale-invariant; standard for
   DDPG paper Xiong et al + Paper Ensemble. Catastrophic loss → sentinel −100.
3. **Sell-before-buy ordering** in `_execute_with_vn_rules` — must free cash
   before buying. Other order causes silent under-allocation.
4. **Skip raw prices_window from observation** — indicators already encode
   price patterns. Reduces obs dim from 200+ to 56. Faster DDPG training.
5. **Pre-compute z-score normalize indicators** — sb3 networks happier with
   bounded inputs. Z-score per (ticker, feature) rolling 60-day.
6. **MarketData is `frozen=True` dataclass** — agent code shouldn't mutate
   shared market data. Defensive immutability.
7. **No news features in obs (yet)** — adds in PKG-5 (LLM core) where news
   is serialized to text for LLM consumption. RL agents stay numeric-only.

### Risks specific to PKG-3

| # | Risk | Likelihood | Mitigation |
|---|------|-----------|------------|
| 1 | Obs space change after agents trained | M | Lock OBS_DIM=56 constant; any future change requires retraining all agents. PR title flag. |
| 2 | Reward function poorly shaped → DDPG diverge | M | log-return is well-tested; PPO backup (PKG-9) as escape hatch. |
| 3 | Lot-100 round-down accumulates cash drag | L | Cash leftover < 100 × max_price ≈ 7M VND ≈ 0.7% NAV; not material on 1B capital. |
| 4 | T+2 OFF default but accidentally enabled in train | L | Default False everywhere; t_plus_2 must be opt-in. PR tests both. |
| 5 | Float32 precision loss after 1500 train steps | L | Cash + holdings tracked as int64 + float64 internally; only obs is float32. |
| 6 | Catastrophic loss sentinel reward (-100) dominates training | L-M | Only triggers at pv ≤ 0 (rare on long-only with 5 stable tickers). Document. |
| 7 | warmup_offset wrong for val/test → indicator NaN leak | M | Test catches via Spike 1 verification (warmup_offset value printed). |

### Khi gặp blocker

- Spike 1 shows warmup_offset > 100: indicator NaN persists too long, suggests
  bug trong PKG-1 indicators.py. Halt + investigate.
- Random agent crash: most likely cause = NaN in obs from missed `nan_to_num`
  call. Add print in `_compute_obs` to find first NaN component.
- Reproducibility fail: `env.np_random` not seeded properly trong reset; verify
  `super().reset(seed=seed)` called first.
- Buy "can't afford" fallback triggered every step: fee rounding or band clamp
  is over-aggressive; print debug in `_execute_with_vn_rules`.

### Observation contract — LOCK

OBS_DIM = 56 = 5×9 + 5 + 5 + 1. Any change requires:
1. Bump constant + comment in module docstring
2. Retrain DDPG/PPO from scratch (PKG-9)
3. Update LLM tools that serialize state (PKG-5)
4. Coordinate via PR — never change silently.

### Tham khảo paper

- **Xiong et al, "Practical Deep RL Approach for Stock Trading"** (docs/...)
  — DDPG state = balance + prices + holdings + technicals. Our 56-dim mirrors
  this but folds prices into indicators.
- **Paper Ensemble** (docs/...) — uses turbulence index; out of scope MVP.

---

## Confidence Score

**6.5/10** for one-pass implementation.

Subtract:
- −1.5 nhiều design decisions interlocked (D1-D10) — sai 1 thì sai cả env
- −1.0 reproducibility seeding qua gym + numpy random tinh tế, dễ off-by-one
- −1.0 lot-100 + ±7% band + fee math có thể có off-by-one ở edge case test

Add back:
- +0.5 PKG-0/1/2 patterns đã establish convention rõ ràng
- +0.5 test invariant design cover hầu hết bug class trước khi land

PKG-3 đáng dành 1 ngày full (1.0 day estimate trong TASKS.md là tight nhưng
khả thi).
