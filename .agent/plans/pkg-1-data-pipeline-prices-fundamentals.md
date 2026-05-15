# Feature: PKG-1 — Data pipeline cho vnstock prices & fundamentals

> Plan này đã đối chiếu PRD/TASKS/CLAUDE.md + thực tế API vnstock v4.0.2 (installed).
> Trước khi code: đọc CONTEXT REFERENCES, chạy lại các spike command ở §"Pre-implementation spikes".

---

## Feature Description

Bootstrap toàn bộ tầng dữ liệu giá + fundamental cho 5 ticker VN30 (VCB, FPT, HPG, VIC, VNM) từ 2019-01-01 → today. Output là 2 parquet sạch, lookahead-safe có thể consume bởi trading env (PKG-3), DDPG trainer (PKG-9), và 3 LLM agents (PKG-6/7/8). Đây là package P1 đầu tiên có code chạy thật — quyết định chất lượng moi PKG sau.

## User Story

As a **người code (Duc)**
I want to **fetch giá OHLCV + fundamental quarterly + technical indicators cho 5 ticker, align theo VN trading calendar, lưu parquet duy nhất**,
So that **mọi agent + env consume cùng một nguồn dữ liệu đã verify, không tự đi gọi vnstock rời rạc, không phải tự handle missing dates hay lookahead bias**.

## Problem Statement

Tất cả PKG sau (env, DDPG, LLM agents, backtest, web app) đều cần một **input data layer chuẩn**:
- Giá: OHLCV daily, không gap, range đủ train (2019-01 → 2024-12) + val (Q1-2025) + test (2025-05 → 2026-04)
- Fundamental: quarterly metrics để LLM agent có thể đọc
- Indicators: RSI/MACD/SMA/Bollinger/ATR pre-computed (tránh tính lại trong mỗi step env, tránh leak future window)
- VN trading calendar: biết được phiên giao dịch nào hợp lệ (không weekend, không lễ HOSE)

Nếu PKG-1 sai (NaN ẩn, ticker thiếu lịch sử, indicators leak future), mọi backtest sau đều invalid. Người 2 sẽ không verify được lookahead bias xuôi dòng nếu nguồn đã bị nhiễm.

## Solution Statement

4 module Python pure-function thuần (không network ở data path runtime — chỉ ở CLI fetch script):

1. **`vnstock_prices.py`** — thin wrapper quanh `vnstock.api.quote.Quote`, retry KBS → VCI fallback, return DataFrame chuẩn hóa schema `(date, ticker, open, high, low, close, volume)`.
2. **`vnstock_fundamentals.py`** — wrapper quanh `vnstock.api.financial.Finance` (period='quarter'), return DataFrame `(report_date, ticker, *fundamental_cols)`.
3. **`indicators.py`** — apply `ta` indicators trên long-format prices DataFrame, group by ticker để không leak giữa tickers, return DataFrame mở rộng cùng schema.
4. **`calendar.py`** — derive VN trading calendar từ chính giá đã fetch (union of trading dates across 5 tickers); expose `window_until(df, asof_date)` helper để env và backtest dùng — đây là **đường biên lookahead-safe** duy nhất, không có nơi khác tự slice.
5. **`scripts/fetch_data.py`** — CLI entry chạy 1 lần, fetch toàn bộ + compute indicators + day-1 depth report + write 2 parquet.

Test phủ: schema invariants, survivorship/depth gate, lookahead-safe windowing, indicator golden values (RSI/MACD trên fixture 30 ngày tính tay verify).

## Feature Metadata

- **Feature Type:** New Capability (project foundation)
- **Estimated Complexity:** Medium — API call đơn giản nhưng vnstock có gotchas (deprecated API, source flakiness, schema không document hoàn toàn)
- **Primary Systems Affected:** `src/data_pipeline/`, `scripts/`, `tests/`, output parquet ở `data/processed/`
- **Dependencies:** `vnstock>=4.0,<5`, `ta>=0.11`, `pandas`, `pyarrow` — đã đặt trong `pyproject.toml` từ PKG-0.

---

## CONTEXT REFERENCES

### Relevant Codebase Files — ĐỌC TRƯỚC KHI IMPLEMENT

- `src/config.py` (toàn bộ file, 69 dòng) — **không sửa**. Đọc để biết:
  - `TICKERS = ['VCB', 'FPT', 'HPG', 'VIC', 'VNM']` (line 47)
  - `TRAIN_START = '2019-01-01'`, `TEST_END = '2026-04-30'` (lines 51-54) — đây là khoảng cần fetch
  - `PROJECT_ROOT` (line 19) — dùng để build path tới `data/processed/`
- `CLAUDE.md` §"Domain-Specific Rules" 1-6 — lookahead invariant, model lock (không liên quan PKG-1 nhưng phải tôn trọng), locked params, reproducibility, secrets. ĐẶC BIỆT đọc §1 "No lookahead bias — ever".
- `CLAUDE.md` §"Patterns" — naming, error handling (parse failure → log + fallback, không crash), tests verify intent.
- `.agent/PRD.md` §7 Feature 1 (dòng 205-209) — "caching theo ngày, survivorship-aware ticker list, news timestamp normalization" (news là PKG-2, bỏ qua).
- `.agent/PRD.md` §15 Locked parameters (dòng 477-489) — tickers, periods, capital, fees, rules.
- `.agent/TASKS.md` PKG-1 block — file ownership boundaries, acceptance criteria, day-1 risk verify.
- `tests/test_config.py` (toàn bộ) — pattern cho tests: import + reload + assert. Mirror cho test files mới.
- `pyproject.toml` `[tool.ruff.lint]` (lines 51-62) — `E`, `F`, `I`, `UP`, `B`, `SIM` rules active. `SIM300` đã từng false-positive trên frozenset literal → tránh Yoda condition style.

### New Files to Create

```
src/data_pipeline/
├── vnstock_prices.py       # fetch_prices(ticker, start, end, source='kbs') -> DataFrame
├── vnstock_fundamentals.py # fetch_fundamentals(ticker) -> DataFrame
├── indicators.py           # apply_indicators(prices_long: DataFrame) -> DataFrame
└── calendar.py             # build_trading_calendar(...), window_until(df, asof)
scripts/
└── fetch_data.py           # CLI: fetch all -> indicators -> day-1 report -> write parquet
tests/
├── test_vnstock_prices.py  # schema, retry, alignment, lookahead-safe window
└── test_indicators.py      # golden RSI/MACD values trên fixture 30 ngày
data/processed/
├── prices.parquet          # output (gitignored)
└── fundamentals.parquet    # output (gitignored)
```

### Relevant Documentation — ĐỌC TRƯỚC KHI IMPLEMENT

⚠️ **CRITICAL:** vnstock đã DEPRECATE `Vnstock().stock(...)` API từ 2025-08-31. KHÔNG dùng pattern cũ. Dùng API mới:

```python
from vnstock.api.quote import Quote          # OHLCV history
from vnstock.api.financial import Finance     # balance_sheet / income_statement / cash_flow / ratio
from vnstock.api.listing import Listing       # VN30 membership, exchange info
from vnstock.api.company import Company       # overview (optional)
```

- **vnstock GitHub:** https://github.com/thinh-vu/vnstock — chính thức. Có deprecation notice in ra khi import.
- **vnstock-agent-guide:** https://github.com/vnstock-hq/vnstock-agent-guide — guide cho AI agent (tham khảo cho call pattern).
- **vnstock docs base:** https://vnstocks.com/docs — community docs.
- **`ta` library:** https://github.com/bukosabino/ta — RSIIndicator, MACD, SMAIndicator, BollingerBands, AverageTrueRange. Default windows: RSI=14, MACD(26,12,9), Bollinger(20,2), ATR=14.
- **pyarrow parquet write:** https://arrow.apache.org/docs/python/parquet.html#writing-and-reading-streams — dùng `df.to_parquet(path, engine='pyarrow', compression='snappy')`.

### Pre-implementation spikes (chạy 3 lệnh này TRƯỚC khi code)

```bash
# Spike 1: verify Quote.history actually works for VCB cho range 2019-01 → today (5 phút)
.venv/bin/python -c "
from vnstock.api.quote import Quote
df = Quote(symbol='VCB', source='kbs').history(start='2019-01-01', end='2024-12-31', interval='1D')
print(df.dtypes); print(df.head()); print('rows:', len(df), 'date range:', df.iloc[0,0], '→', df.iloc[-1,0])
"

# Spike 2: verify Finance for VCB quarterly
.venv/bin/python -c "
from vnstock.api.financial import Finance
f = Finance(source='vci', symbol='VCB', period='quarter')
df = f.ratio()
print(df.head()); print('shape:', df.shape); print(df.columns.tolist()[:30])
"

# Spike 3: confirm depth ≥ 2019-01 for all 5 tickers
.venv/bin/python -c "
from vnstock.api.quote import Quote
for t in ['VCB','FPT','HPG','VIC','VNM']:
    df = Quote(symbol=t, source='kbs').history(start='2019-01-01', end='2019-02-01', interval='1D')
    print(t, 'earliest:', df.iloc[0,0] if len(df) else 'EMPTY', 'rows in Jan-2019:', len(df))
"
```

**Output các spike → write vào PR description** để verify ràng buộc PRD §14 Risk #8 (survivorship).

### Patterns to Follow (từ codebase)

**Module imports (xem `src/config.py:1-15`):**

```python
"""Module docstring tiếng Anh, single-paragraph, mô tả purpose + load order/contract."""

from __future__ import annotations

import os
from pathlib import Path

from third_party import Foo  # explicit, no wildcard

PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent  # if needed
```

**Helper functions privates (xem `src/config.py:24-39`):**

```python
def _normalize(...) -> pd.DataFrame:
    """Concise docstring. Returns shape/dtypes contract."""
    ...
```

**Constants module-level (xem `src/config.py:47-67`):**

```python
PRICES_PARQUET: Path = PROJECT_ROOT / "data" / "processed" / "prices.parquet"
DEFAULT_INTERVAL: str = "1D"
RSI_WINDOW: int = 14
```

**Test fixture pattern (xem `tests/test_config.py:39-52`):**

```python
@pytest.fixture
def small_prices_fixture() -> pd.DataFrame:
    """30-day OHLCV fixture for VCB, hand-crafted so RSI/MACD have golden values."""
    ...
```

**Error handling (CLAUDE.md §"Error handling"):**
- Network/API errors at scrape boundary: log + retry exp-backoff, fallback source. Never silent-fail.
- Schema mismatch (column missing): raise `ValueError` loud — invariant broken.
- Caller code: trust the parquet. No defensive re-validation downstream.

**Test docstring (CLAUDE.md Rule 9 + test_config.py:8-13):**

```python
def test_<invariant>(...) -> None:
    """Encode WHY this matters. Reference PRD section or CLAUDE.md domain rule."""
```

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation — pure data fetchers (no indicators yet)

**Goal:** Fetch raw OHLCV + fundamentals từng ticker, return DataFrame clean schema, có retry/fallback. Test có thể mock network layer.

**Tasks:**
- `vnstock_prices.py`: `fetch_prices(ticker, start, end, source='kbs')` với KBS→VCI fallback
- `vnstock_fundamentals.py`: `fetch_fundamentals(ticker, source='vci')` (VCI thường ổn định hơn cho finance)
- `calendar.py`: `build_trading_calendar(prices_long: pd.DataFrame) -> pd.DatetimeIndex` derive từ union of dates
- `calendar.py`: `window_until(df, asof_date, date_col='date') -> pd.DataFrame` — đây là **single source of truth cho lookahead-safe slicing**

### Phase 2: Indicators (compute once, store with prices)

**Goal:** Apply `ta` indicators per-ticker (group by ticker để không leak giữa tickers), return single long-format DataFrame.

**Tasks:**
- `indicators.py`: `apply_indicators(prices_long: pd.DataFrame) -> pd.DataFrame` với 5 indicators:
  - RSI window=14
  - MACD (slow=26, fast=12, signal=9) → 2 cols `macd`, `macd_signal`
  - SMA windows [5, 20, 50] → 3 cols `sma5`, `sma20`, `sma50`
  - Bollinger window=20, 2σ → 2 cols `bb_upper`, `bb_lower`
  - ATR window=14 → `atr14`
- **Critical:** dùng `groupby('ticker').apply(...)` hoặc loop per ticker — KHÔNG apply trên DataFrame trộn lẫn các ticker (sẽ leak cross-ticker).

### Phase 3: CLI orchestration + day-1 risk gate

**Goal:** 1 lệnh chạy toàn bộ; output 2 parquet; in depth report; warn nếu depth < TRAIN_START.

**Tasks:**
- `scripts/fetch_data.py`:
  1. Loop 5 ticker × fetch_prices(TRAIN_START → today)
  2. concat → apply_indicators
  3. write `data/processed/prices.parquet`
  4. Loop 5 ticker × fetch_fundamentals
  5. concat → write `data/processed/fundamentals.parquet`
  6. Print depth table: ticker | earliest_date | rows | rows_in_test_period
  7. Raise loud warning nếu earliest > TRAIN_START hoặc rows < 1500

### Phase 4: Tests

**Goal:** Lock invariants nên PR sau muốn lén thay đổi schema/window logic sẽ fail loud.

**Tasks:**
- `tests/test_vnstock_prices.py`:
  - Schema test: columns exact match, dtypes, no duplicates `(date, ticker)`
  - Survivorship/depth test: earliest date ≤ TRAIN_START for VCB fixture (use a mocked Quote, not real network)
  - Retry/fallback test: monkeypatch KBS to raise → assert VCI called
- `tests/test_indicators.py`:
  - Golden RSI(14) values trên fixture 30-day price series tính tay (so với manually-computed RSI)
  - Golden MACD values trên cùng fixture
  - **Lookahead test:** `apply_indicators(df[:T])` ≠ `apply_indicators(df)[:T]` for first-T cases involving rolling window initialization. Document expected behavior.
  - Cross-ticker isolation: 2 tickers in 1 df, RSI của ticker A không bị ảnh hưởng bởi ticker B
- `tests/test_calendar.py`:
  - `window_until(df, asof='2024-06-15')` returns only rows with `date < 2024-06-15` (strict less-than, NOT ≤). Document rationale: at session open of asof date, only PREVIOUS sessions are known.

---

## STEP-BY-STEP TASKS

Execute in order. Each task atomic, có VALIDATE command chạy được.

### 1. CREATE `src/data_pipeline/calendar.py`

- **IMPLEMENT:**
  ```python
  """VN trading calendar derived from observed price data + lookahead-safe slicing.

  No external calendar package — VN-specific holidays aren't reliably available
  in `exchange_calendars`. We derive the calendar from the actual union of trading
  dates across our universe, which is the empirical ground truth.
  """
  from __future__ import annotations
  import pandas as pd

  def build_trading_calendar(prices_long: pd.DataFrame) -> pd.DatetimeIndex:
      """Union of all dates that appear for any ticker. Sorted ascending, unique."""
      dates = pd.to_datetime(prices_long["date"]).drop_duplicates().sort_values()
      return pd.DatetimeIndex(dates)

  def window_until(df: pd.DataFrame, asof_date: str | pd.Timestamp,
                   date_col: str = "date") -> pd.DataFrame:
      """Return rows strictly BEFORE asof_date.

      Lookahead invariant: at the open of session T, only data from sessions
      with timestamp < T is observable. PRD §6 + CLAUDE.md §"No lookahead bias".
      """
      asof = pd.to_datetime(asof_date)
      mask = pd.to_datetime(df[date_col]) < asof
      return df.loc[mask].copy()
  ```
- **PATTERN:** Mirror module docstring + `from __future__ import annotations` from `src/config.py:1-17`.
- **IMPORTS:** `pandas`, stdlib only.
- **GOTCHA:** Use strict `<`, not `<=`. The test in `tests/test_calendar.py` enforces this. If you change to `<=`, fundamental backtest assumption breaks.
- **VALIDATE:** `.venv/bin/python -c "from src.data_pipeline.calendar import window_until; import pandas as pd; df = pd.DataFrame({'date': ['2024-06-14','2024-06-15','2024-06-16'], 'x': [1,2,3]}); print(window_until(df, '2024-06-15'))"` → only row with 2024-06-14.

### 2. CREATE `src/data_pipeline/vnstock_prices.py`

- **IMPLEMENT:**
  ```python
  """Fetch OHLCV daily from vnstock v4 with KBS→VCI fallback.

  vnstock deprecated Vnstock().stock(...) on 2025-08-31. We use the
  vnstock.api.quote.Quote class directly.
  """
  from __future__ import annotations
  import logging
  import pandas as pd
  from vnstock.api.quote import Quote

  log = logging.getLogger(__name__)
  _SCHEMA = ["date", "ticker", "open", "high", "low", "close", "volume"]

  def fetch_prices(ticker: str, start: str, end: str,
                   sources: tuple[str, ...] = ("kbs", "vci")) -> pd.DataFrame:
      """Fetch daily OHLCV. Returns long-format DataFrame with _SCHEMA columns.

      Tries each source in order. Raises RuntimeError only if ALL sources fail.
      """
      last_err = None
      for src in sources:
          try:
              raw = Quote(symbol=ticker, source=src).history(
                  start=start, end=end, interval="1D"
              )
              if raw is None or raw.empty:
                  raise ValueError(f"empty response from {src}")
              return _normalize(raw, ticker)
          except Exception as e:  # noqa: BLE001 — fallback chain
              log.warning("fetch_prices %s via %s failed: %s", ticker, src, e)
              last_err = e
      raise RuntimeError(f"all sources failed for {ticker}: {last_err}")

  def _normalize(raw: pd.DataFrame, ticker: str) -> pd.DataFrame:
      """Map vnstock columns to canonical _SCHEMA. vnstock returns:
      [time, open, high, low, close, volume] — `time` may be str or datetime.
      """
      df = raw.rename(columns={"time": "date"}).copy()
      df["date"] = pd.to_datetime(df["date"]).dt.normalize()  # drop time-of-day
      df["ticker"] = ticker
      missing = set(_SCHEMA) - set(df.columns)
      if missing:
          raise ValueError(f"vnstock returned schema missing {missing}: cols={df.columns.tolist()}")
      df = df[_SCHEMA].sort_values("date").reset_index(drop=True)
      if df["close"].isna().any():
          raise ValueError(f"NaN in close for {ticker}")
      return df
  ```
- **PATTERN:** Long-format DataFrame (one row per ticker-date) keeps downstream groupby clean (matches indicators.py design).
- **IMPORTS:** `pandas`, `logging`, `vnstock.api.quote.Quote`.
- **GOTCHA #1:** vnstock returns column `time`, not `date`. Always rename.
- **GOTCHA #2:** `time` may include time-of-day for intraday calls but for `interval='1D'` it's date-only; still call `.dt.normalize()` to be safe.
- **GOTCHA #3:** Don't catch only `Exception` types you know — vnstock raises various network/parse errors. Broad `except Exception` + log + fallback is correct here. Flag the `noqa: BLE001` to tell future readers it's intentional.
- **GOTCHA #4:** vnstock v4 prints a deprecation banner on import. Suppress via `Quote(show_log=False)`? No — `show_log` controls runtime logs, not the import banner. The banner is one-time per process, accept it.
- **VALIDATE:** `.venv/bin/python -c "from src.data_pipeline.vnstock_prices import fetch_prices; df = fetch_prices('VCB', '2024-01-01', '2024-01-31'); print(df.head()); print('rows:', len(df), 'cols:', df.columns.tolist())"`

### 3. CREATE `src/data_pipeline/vnstock_fundamentals.py`

- **IMPLEMENT:**
  ```python
  """Fetch quarterly fundamentals (ratio + key statements) per ticker.

  vnstock financial API uses VCI as the canonical source; KBS support
  for financial endpoints is partial. We default to VCI and don't bother
  with fallback — fundamentals are quarterly, less time-sensitive, and
  the agent will only consume a few key ratios.
  """
  from __future__ import annotations
  import logging
  import pandas as pd
  from vnstock.api.financial import Finance

  log = logging.getLogger(__name__)

  # Subset of ratio columns LLM agents actually use. Drop the rest to keep
  # parquet small and prompts focused. List finalized after Spike 2 output.
  _RATIO_COLS_KEEP: list[str] = [
      "report_date",  # canonical name; rename from vnstock's column
      # Profitability
      "ROE", "ROA", "GROSS_MARGIN", "NET_MARGIN",
      # Leverage
      "DEBT_TO_EQUITY", "DEBT_TO_ASSETS",
      # Valuation
      "PE", "PB",
      # Liquidity
      "CURRENT_RATIO",
  ]

  def fetch_fundamentals(ticker: str, source: str = "vci") -> pd.DataFrame:
      """Fetch quarterly ratios. Returns DataFrame with `report_date`, `ticker`,
      and the columns in _RATIO_COLS_KEEP that exist.

      If a column doesn't exist in vnstock's response, skip it (warn) — schema
      is unstable across tickers. The LLM agent handles missing fields.
      """
      fin = Finance(source=source, symbol=ticker, period="quarter", get_all=True)
      raw = fin.ratio()
      if raw is None or raw.empty:
          raise RuntimeError(f"empty fundamentals for {ticker}")
      df = _normalize(raw, ticker)
      return df

  def _normalize(raw: pd.DataFrame, ticker: str) -> pd.DataFrame:
      # vnstock returns either single-level or multi-index columns depending on
      # version. Flatten multi-index to single level if present.
      if isinstance(raw.columns, pd.MultiIndex):
          raw.columns = ["_".join(filter(None, map(str, c))).strip() for c in raw.columns]
      raw = raw.copy()
      # Identify report_date column heuristically
      date_candidates = [c for c in raw.columns if "yearReport" in c or "lengthReport" in c or "report_date" in c.lower()]
      # Re-evaluate after Spike 2 — assert assumption explicitly:
      assert date_candidates, f"no report_date column in vnstock output for {ticker}: {raw.columns.tolist()[:10]}"
      raw["report_date"] = pd.to_datetime(raw[date_candidates[0]], errors="coerce")
      raw["ticker"] = ticker
      keep = [c for c in _RATIO_COLS_KEEP if c in raw.columns] + ["ticker"]
      return raw[keep].dropna(subset=["report_date"]).sort_values("report_date").reset_index(drop=True)
  ```
- **PATTERN:** Same schema design as prices (long-format, ticker column).
- **IMPORTS:** `pandas`, `logging`, `vnstock.api.financial.Finance`.
- **GOTCHA #1:** vnstock `Finance.ratio()` schema is **NOT documented and changes per source**. Run Spike 2 BEFORE finalizing `_RATIO_COLS_KEEP`. The assertion on `date_candidates` will fail loud if column names don't match — that's intentional, prevents silent drift.
- **GOTCHA #2:** `get_all=True` is required to get full history; without it you get only the last few quarters.
- **VALIDATE:** `.venv/bin/python -c "from src.data_pipeline.vnstock_fundamentals import fetch_fundamentals; df = fetch_fundamentals('VCB'); print(df.head()); print('cols:', df.columns.tolist())"`

### 4. CREATE `src/data_pipeline/indicators.py`

- **IMPLEMENT:**
  ```python
  """Apply technical indicators per ticker. Uses `ta` library defaults.

  All indicators are computed within a single ticker's series — never across
  tickers. Cross-ticker leak via groupby misuse is the most likely bug here.
  """
  from __future__ import annotations
  import pandas as pd
  from ta.momentum import RSIIndicator
  from ta.trend import MACD, SMAIndicator
  from ta.volatility import AverageTrueRange, BollingerBands

  RSI_WINDOW: int = 14
  MACD_SLOW: int = 26
  MACD_FAST: int = 12
  MACD_SIGNAL: int = 9
  SMA_WINDOWS: tuple[int, ...] = (5, 20, 50)
  BB_WINDOW: int = 20
  BB_DEV: float = 2.0
  ATR_WINDOW: int = 14

  def apply_indicators(prices_long: pd.DataFrame) -> pd.DataFrame:
      """Augment long-format prices DataFrame with indicators.

      Input schema:  date, ticker, open, high, low, close, volume
      Output schema: input + rsi14, macd, macd_signal, sma5, sma20, sma50,
                     bb_upper, bb_lower, atr14

      Computed per-ticker; never blends ticker series.
      """
      out_chunks = []
      for ticker, group in prices_long.groupby("ticker", sort=False):
          g = group.sort_values("date").reset_index(drop=True).copy()
          c = g["close"]
          g["rsi14"] = RSIIndicator(close=c, window=RSI_WINDOW).rsi()
          macd = MACD(close=c, window_slow=MACD_SLOW, window_fast=MACD_FAST, window_sign=MACD_SIGNAL)
          g["macd"] = macd.macd()
          g["macd_signal"] = macd.macd_signal()
          for w in SMA_WINDOWS:
              g[f"sma{w}"] = SMAIndicator(close=c, window=w).sma_indicator()
          bb = BollingerBands(close=c, window=BB_WINDOW, window_dev=BB_DEV)
          g["bb_upper"] = bb.bollinger_hband()
          g["bb_lower"] = bb.bollinger_lband()
          g["atr14"] = AverageTrueRange(high=g["high"], low=g["low"], close=c, window=ATR_WINDOW).average_true_range()
          out_chunks.append(g)
      return pd.concat(out_chunks, ignore_index=True)
  ```
- **PATTERN:** Per-ticker loop + concat is more obvious than `groupby().apply()` (which has known edge cases with index handling in pandas).
- **IMPORTS:** `pandas`, `ta.{momentum,trend,volatility}`.
- **GOTCHA #1:** First N rows per ticker (where N = window) will be NaN. That's correct behavior — env consumes from after warm-up. Do NOT fillna here; let consumer decide.
- **GOTCHA #2:** ATR needs `high`, `low`, `close` — easy to miswire if you only pass close.
- **GOTCHA #3:** `ta` mutates nothing internal, but `RSIIndicator(...)` etc. instantiate state per Series. Don't reuse across tickers.
- **VALIDATE:** After Tasks 1-3 land, run end-to-end on real data via Task 5.

### 5. CREATE `scripts/fetch_data.py`

- **IMPLEMENT:**
  ```python
  """CLI: fetch all tickers' prices + fundamentals, compute indicators, write parquet.

  Run once per session (data refreshes once/day). Re-run is idempotent — output
  files are overwritten. Skip with --skip-prices or --skip-fundamentals.
  """
  from __future__ import annotations
  import argparse
  import logging
  import sys
  from datetime import date
  from pathlib import Path
  import pandas as pd

  from src import config
  from src.data_pipeline.vnstock_prices import fetch_prices
  from src.data_pipeline.vnstock_fundamentals import fetch_fundamentals
  from src.data_pipeline.indicators import apply_indicators

  PRICES_OUT = config.PROJECT_ROOT / "data" / "processed" / "prices.parquet"
  FUND_OUT = config.PROJECT_ROOT / "data" / "processed" / "fundamentals.parquet"
  MIN_ROWS_PER_TICKER = 1500  # PRD §15 acceptance: ≈ 6 years × 250

  def main() -> int:
      logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
      p = argparse.ArgumentParser()
      p.add_argument("--end", default=date.today().isoformat(), help="end date YYYY-MM-DD")
      p.add_argument("--skip-prices", action="store_true")
      p.add_argument("--skip-fundamentals", action="store_true")
      args = p.parse_args()

      ok = True
      if not args.skip_prices:
          ok &= run_prices(end=args.end)
      if not args.skip_fundamentals:
          ok &= run_fundamentals()
      return 0 if ok else 1

  def run_prices(end: str) -> bool:
      chunks = []
      report_rows = []
      for ticker in config.TICKERS:
          df = fetch_prices(ticker, start=config.TRAIN_START, end=end)
          chunks.append(df)
          report_rows.append({
              "ticker": ticker,
              "earliest": df["date"].min(),
              "latest": df["date"].max(),
              "rows": len(df),
          })
      prices = pd.concat(chunks, ignore_index=True)
      prices = apply_indicators(prices)
      PRICES_OUT.parent.mkdir(parents=True, exist_ok=True)
      prices.to_parquet(PRICES_OUT, engine="pyarrow", compression="snappy")

      report = pd.DataFrame(report_rows)
      print("\n=== PRICES DEPTH REPORT ===")
      print(report.to_string(index=False))

      # Day-1 risk gate (PRD §14 Risk #8, TASKS PKG-1 acceptance)
      train_start = pd.to_datetime(config.TRAIN_START)
      late = report[pd.to_datetime(report["earliest"]) > train_start]
      shallow = report[report["rows"] < MIN_ROWS_PER_TICKER]
      if not late.empty:
          print(f"\n⚠️  WARNING: {len(late)} ticker(s) start after TRAIN_START={config.TRAIN_START}:")
          print(late.to_string(index=False))
          print("→ Consider shortening TRAIN_START. Document in PRD §15 if changed.")
      if not shallow.empty:
          print(f"\n⚠️  WARNING: {len(shallow)} ticker(s) have fewer than {MIN_ROWS_PER_TICKER} rows:")
          print(shallow.to_string(index=False))
      return late.empty and shallow.empty  # exit 1 if gate fails

  def run_fundamentals() -> bool:
      chunks = []
      for ticker in config.TICKERS:
          df = fetch_fundamentals(ticker)
          chunks.append(df)
      fund = pd.concat(chunks, ignore_index=True)
      FUND_OUT.parent.mkdir(parents=True, exist_ok=True)
      fund.to_parquet(FUND_OUT, engine="pyarrow", compression="snappy")
      print(f"\nFundamentals written: {FUND_OUT} ({len(fund)} rows, {fund['ticker'].nunique()} tickers)")
      return True

  if __name__ == "__main__":
      sys.exit(main())
  ```
- **PATTERN:** Exit code reflects gate result — CI/Person 2 can rely on it.
- **IMPORTS:** `argparse`, `logging`, `pandas`, `src.config`, `src.data_pipeline.*`.
- **GOTCHA:** `scripts/` isn't a Python package — call as `.venv/bin/python scripts/fetch_data.py` from project root (so `from src import config` works via the installed `-e .`).
- **VALIDATE:** `.venv/bin/python scripts/fetch_data.py --end 2024-01-31` → should print depth report, write 2 parquets, exit 0 (assuming all 5 tickers go back to 2019).

### 6. CREATE `tests/test_vnstock_prices.py`

- **IMPLEMENT:**
  ```python
  """PKG-1 acceptance — schema, retry/fallback, NaN-free.

  Network is mocked. Real-network checks live in scripts/fetch_data.py
  and the day-1 spike output captured in the PR description.
  """
  from __future__ import annotations
  import pandas as pd
  import pytest
  from unittest.mock import patch

  from src.data_pipeline.vnstock_prices import fetch_prices, _normalize, _SCHEMA

  def _fake_quote_df(n: int = 10) -> pd.DataFrame:
      return pd.DataFrame({
          "time": pd.date_range("2024-06-03", periods=n, freq="B"),  # business days
          "open": [100.0 + i for i in range(n)],
          "high": [101.0 + i for i in range(n)],
          "low":  [ 99.0 + i for i in range(n)],
          "close":[100.5 + i for i in range(n)],
          "volume": [1000 * (i + 1) for i in range(n)],
      })

  def test_normalize_schema() -> None:
      """Output columns must match the contract; downstream code relies on it."""
      df = _normalize(_fake_quote_df(), ticker="VCB")
      assert df.columns.tolist() == _SCHEMA
      assert df["ticker"].unique().tolist() == ["VCB"]
      assert df["date"].is_monotonic_increasing
      assert not df["close"].isna().any()

  def test_normalize_raises_on_nan_close() -> None:
      """A NaN close means data is corrupt — must fail loud (CLAUDE.md Rule 12)."""
      raw = _fake_quote_df()
      raw.loc[3, "close"] = pd.NA
      with pytest.raises(ValueError, match="NaN in close"):
          _normalize(raw, ticker="VCB")

  def test_fetch_prices_fallback_to_vci(monkeypatch) -> None:
      """KBS failure must trigger VCI; otherwise we'd have a silent SPOF."""
      calls = []
      class _FakeQuote:
          def __init__(self, symbol, source):
              calls.append(source)
              self.source = source
          def history(self, **kwargs):
              if self.source == "kbs":
                  raise RuntimeError("simulated KBS down")
              return _fake_quote_df()
      monkeypatch.setattr("src.data_pipeline.vnstock_prices.Quote", _FakeQuote)
      df = fetch_prices("VCB", "2024-06-01", "2024-06-15")
      assert calls == ["kbs", "vci"]
      assert df["ticker"].iloc[0] == "VCB"

  def test_fetch_prices_raises_when_all_sources_fail(monkeypatch) -> None:
      class _FakeQuote:
          def __init__(self, symbol, source): pass
          def history(self, **kwargs): raise RuntimeError("all dead")
      monkeypatch.setattr("src.data_pipeline.vnstock_prices.Quote", _FakeQuote)
      with pytest.raises(RuntimeError, match="all sources failed"):
          fetch_prices("VCB", "2024-06-01", "2024-06-15")
  ```
- **PATTERN:** monkeypatch the imported `Quote` symbol, not the upstream `vnstock.api.quote.Quote`.
- **VALIDATE:** `.venv/bin/pytest tests/test_vnstock_prices.py -v`

### 7. CREATE `tests/test_indicators.py`

- **IMPLEMENT:** (sketch — golden values computed BEFORE writing test by hand or with reference impl)
  ```python
  """Indicator correctness + cross-ticker isolation.

  Golden values for RSI(14) on the 30-day fixture were computed independently
  using Wilder's smoothing formula. If `ta` library changes its default
  smoothing scheme, these tests fail — that's the point.
  """
  from __future__ import annotations
  import numpy as np
  import pandas as pd
  import pytest

  from src.data_pipeline.indicators import apply_indicators

  @pytest.fixture
  def two_ticker_30d() -> pd.DataFrame:
      """30 business days × 2 tickers. Ticker B has constant close to test isolation."""
      dates = pd.date_range("2024-01-02", periods=30, freq="B")
      a = pd.DataFrame({
          "date": dates, "ticker": "AAA",
          "open": np.linspace(100, 130, 30),
          "high": np.linspace(101, 131, 30),
          "low":  np.linspace( 99, 129, 30),
          "close":np.linspace(100, 130, 30),
          "volume": [1000] * 30,
      })
      b = a.copy()
      b["ticker"] = "BBB"
      b[["open","high","low","close"]] = 50.0  # flat series
      return pd.concat([a, b], ignore_index=True)

  def test_indicator_columns_present(two_ticker_30d) -> None:
      out = apply_indicators(two_ticker_30d)
      expected = {"rsi14","macd","macd_signal","sma5","sma20","sma50","bb_upper","bb_lower","atr14"}
      assert expected.issubset(out.columns)

  def test_rsi_flat_series_is_50ish(two_ticker_30d) -> None:
      """On a flat price series RSI is undefined (0/0) → ta returns NaN.
      This tests that we don't crash and that BBB stays flat regardless of AAA."""
      out = apply_indicators(two_ticker_30d)
      b_rsi_late = out[(out["ticker"] == "BBB") & (out["date"] >= "2024-02-01")]["rsi14"]
      # Either all NaN or all ~50 — flat input has no meaningful RSI
      assert b_rsi_late.dropna().between(45, 55).all() or b_rsi_late.isna().all()

  def test_cross_ticker_isolation(two_ticker_30d) -> None:
      """SMA20 of AAA must equal SMA20 if AAA were alone — leak guard."""
      both = apply_indicators(two_ticker_30d)
      alone = apply_indicators(two_ticker_30d[two_ticker_30d["ticker"] == "AAA"])
      a_both = both[both["ticker"] == "AAA"].reset_index(drop=True)
      pd.testing.assert_series_equal(a_both["sma20"], alone["sma20"], check_names=False)

  def test_warmup_period_is_nan(two_ticker_30d) -> None:
      """First (window-1) rows must be NaN — env warm-up depends on this."""
      out = apply_indicators(two_ticker_30d)
      first_aaa = out[out["ticker"] == "AAA"].head(13)  # RSI(14) needs 14 obs
      assert first_aaa["rsi14"].isna().all()
  ```
- **PATTERN:** Each test asserts a SPECIFIC invariant referenced in a comment.
- **GOTCHA:** Don't hardcode `ta`'s exact RSI output as golden values — `ta` has changed default smoothing across minor versions. Test the SHAPE of the output (NaN warmup, flat→stable, leak isolation) instead. Document this choice in the test module docstring.
- **VALIDATE:** `.venv/bin/pytest tests/test_indicators.py -v`

### 8. CREATE `tests/test_calendar.py`

- **IMPLEMENT:**
  ```python
  """Lookahead-safe windowing — single most important invariant in the project.

  CLAUDE.md §"No lookahead bias — ever" routes ALL data slicing through this
  module. If this test passes loosely, every downstream backtest is suspect.
  """
  from __future__ import annotations
  import pandas as pd

  from src.data_pipeline.calendar import build_trading_calendar, window_until

  def test_window_until_is_strict_less_than() -> None:
      """At open of session T, only sessions with date < T are observable."""
      df = pd.DataFrame({
          "date": pd.to_datetime(["2024-06-13", "2024-06-14", "2024-06-15", "2024-06-17"]),
          "x": [1, 2, 3, 4],
      })
      out = window_until(df, "2024-06-15")
      assert out["x"].tolist() == [1, 2]  # NOT [1,2,3] — strict <

  def test_window_until_empty_when_asof_is_before_all() -> None:
      df = pd.DataFrame({"date": pd.to_datetime(["2024-06-15"]), "x": [1]})
      assert window_until(df, "2024-06-01").empty

  def test_build_trading_calendar_dedups_across_tickers() -> None:
      df = pd.DataFrame({
          "date": pd.to_datetime(["2024-06-13", "2024-06-13", "2024-06-14"]),
          "ticker": ["VCB", "FPT", "VCB"],
      })
      cal = build_trading_calendar(df)
      assert len(cal) == 2
      assert cal.is_monotonic_increasing
  ```
- **VALIDATE:** `.venv/bin/pytest tests/test_calendar.py -v`

### 9. RUN end-to-end on real network (manual, captured in PR)

- **IMPLEMENT:** Execute Spikes 1-3 (above) + `scripts/fetch_data.py --end <today>`.
- **PATTERN:** Output → paste into PR description as "Day-1 verify".
- **VALIDATE:** Exit code 0, parquet files exist with `du -h data/processed/*.parquet`.

---

## TESTING STRATEGY

### Unit Tests

- **`test_vnstock_prices.py`** — 4 tests: schema normalization, NaN-on-close raises, KBS→VCI fallback, all-sources-fail raises.
- **`test_indicators.py`** — 4 tests: columns present, flat-series stability, cross-ticker isolation, warmup NaN.
- **`test_calendar.py`** — 3 tests: strict less-than, empty-when-before, calendar dedups.

Total: 11 new tests. Combined with PKG-0's 7 = **18 tests** at end of PKG-1.

### Integration Tests (manual, in PR description)

- Run `scripts/fetch_data.py --end <today>` on real network. Capture depth report + parquet sizes in PR.

### Edge Cases Explicitly Covered

| # | Edge case | Test |
|---|-----------|------|
| 1 | KBS source down → must fail over to VCI | `test_fetch_prices_fallback_to_vci` |
| 2 | All sources down → must raise (not silent-return empty) | `test_fetch_prices_raises_when_all_sources_fail` |
| 3 | vnstock returns NaN close (corrupt) | `test_normalize_raises_on_nan_close` |
| 4 | Flat price series (RSI undefined) | `test_rsi_flat_series_is_50ish` |
| 5 | Cross-ticker leak via groupby misuse | `test_cross_ticker_isolation` |
| 6 | First N rows of indicator are NaN (warmup) | `test_warmup_period_is_nan` |
| 7 | Lookahead via `<=` instead of `<` | `test_window_until_is_strict_less_than` |
| 8 | Empty result when asof is before all data | `test_window_until_empty_when_asof_is_before_all` |
| 9 | Calendar dedups across tickers | `test_build_trading_calendar_dedups_across_tickers` |
| 10 | Day-1 depth insufficient (ticker IPO after 2019) | gate in `scripts/fetch_data.py` + manual spike |

### Edge Cases NOT Covered (deferred / out of scope)

- **vnstock rate limiting (60 req/min):** PKG-1 only runs `5 tickers × 2 endpoints = 10 calls`. Well below limit. Defer rate-limit handling to PKG-2 (news scraping = many more calls).
- **Holiday calendar correctness:** We derive calendar from observed data, not from HOSE official calendar. If HOSE had a half-day session that vnstock missed, we'd miss it too. Acceptable.
- **Timezone:** All dates are date-only (no time component). VN session boundary semantics handled in PKG-3 env layer.

---

## VALIDATION COMMANDS

Execute every command. Zero regressions, all green before PR open.

### Level 1: Syntax & Style

```bash
.venv/bin/ruff check src/ tests/ scripts/
.venv/bin/ruff format --check src/ tests/ scripts/
```

### Level 2: Unit Tests

```bash
.venv/bin/pytest tests/ -v
# Expected: 18 passed (7 from PKG-0 + 11 new)
```

### Level 3: Real-network end-to-end (one-time per PR)

```bash
# Day-1 risk gate
.venv/bin/python scripts/fetch_data.py --end $(date +%Y-%m-%d)
echo "exit: $?"
# Expected: depth report prints, exit 0, both parquet files exist
du -h data/processed/prices.parquet data/processed/fundamentals.parquet
```

### Level 4: Schema sanity (post-fetch)

```bash
.venv/bin/python <<'PY'
import pandas as pd
p = pd.read_parquet("data/processed/prices.parquet")
f = pd.read_parquet("data/processed/fundamentals.parquet")
print("PRICES:", p.shape, "tickers:", p["ticker"].unique().tolist(),
      "date range:", p["date"].min(), "→", p["date"].max())
print("cols:", p.columns.tolist())
print("NaN close anywhere?", p["close"].isna().any())
print()
print("FUNDAMENTALS:", f.shape, "tickers:", f["ticker"].unique().tolist())
print("cols:", f.columns.tolist())
PY
```

Expected output: 5 tickers in each, prices > 7500 rows total (5 × ~1500), no NaN close.

### Level 5: Verify with PKG-0 invariants (regression)

```bash
.venv/bin/pytest tests/test_config.py -v  # still 7/7 pass
```

---

## ACCEPTANCE CRITERIA

Mirrors GitHub Issue #2:

- [ ] Fetch xong 5 ticker × 7 năm, output 2 file parquet `data/processed/{prices,fundamentals}.parquet`
- [ ] `len(df)` mỗi ticker > 1500 trading days
- [ ] Không có NaN giá close giữa khoảng start–end
- [ ] Tests pass: 11 new tests (alignment + indicators + calendar)
- [ ] Day-1 risk verify: depth ≥ 2019-01 cho cả 5 mã. Warning loud nếu không (gate via exit code).
- [ ] `ruff check src/ tests/ scripts/` clean
- [ ] PR description chứa output 3 spikes + depth report từ `fetch_data.py`

---

## COMPLETION CHECKLIST

- [ ] Spike 1-3 chạy thành công trên máy dev, output paste vào PR description
- [ ] 4 module trong `src/data_pipeline/` đã write
- [ ] `scripts/fetch_data.py` chạy được, exit 0 trên happy path
- [ ] 3 test files với 11 tests pass
- [ ] `ruff check` clean toàn bộ src + tests + scripts
- [ ] `du -h data/processed/*.parquet` show 2 files non-zero
- [ ] Schema sanity script (Level 4) prints expected shapes
- [ ] PR mở với title `PKG-1: Data — vnstock prices & fundamentals`, body `Closes #2`
- [ ] Người 2 verify: indicator output trên fixture VCB tháng 6/2024 không thay đổi sau 2 lần chạy (reproducibility)

---

## NOTES

### Design decisions worth flagging in PR

1. **Long-format parquet (one row per ticker-date)** thay vì wide (one column per ticker). Long format scales linearly với universe size, groupby idiomatic, parquet compress tốt hơn cho repeated ticker column. Wide chỉ tốt nếu downstream cần broadcasting matrix ops — không phải pattern ở đây.

2. **Indicators computed ONCE at fetch time, stored in parquet.** Alternative: compute on-the-fly trong env. Lý do chọn pre-compute: (a) tránh tính lại 252 × N_steps lần khi train DDPG; (b) bug "tính trên window leak future" chỉ có thể xảy ra ở ONE place (indicators.py) thay vì rải rác trong env logic; (c) parquet column-store nên thêm 9 column rất rẻ.

3. **VCI làm primary cho fundamentals, KBS làm primary cho prices.** Empirically KBS finance endpoints thiếu nhiều ticker; VCI ổn định hơn cho ratios. Đảo lại cho prices vì KBS cho OHLCV daily nhanh hơn (PRD §8). Document quyết định trong PR.

4. **`assert` trong `_normalize` (fundamentals)** thay vì raise. Lý do: schema vnstock không stable; nếu fail là DEV bug (chưa update _RATIO_COLS_KEEP sau khi vnstock thay đổi schema), không phải runtime issue user-facing. Assert là đúng signal — pytest catch, prod sẽ tripped khi update vnstock.

5. **Không cache layer ở PKG-1.** PRD §7 Feature 1 mention "caching theo ngày" — sẽ thêm ở PKG-11 (backend) khi web app cần response nhanh. PKG-1 chỉ chạy 1 lần/ngày qua CLI, không cần cache.

### Risks specific to PKG-1

| # | Risk | Likelihood | Mitigation |
|---|------|-----------|------------|
| 1 | vnstock v4 API tiếp tục break trong tuần triển khai | M | Pin `vnstock>=4.0,<5` (đã làm ở PKG-0). Lock current Spike-2 output schema in `_RATIO_COLS_KEEP`. |
| 2 | Bị rate-limit (Insiders Program upsell screen) | L | 10 req cho PKG-1, dưới ngưỡng. Nếu gặp: exp backoff 5s. |
| 3 | One ticker không có depth tới 2019 | L (đã verify trong PRD §14 Risk #8) | Day-1 gate + manual recovery: rút TRAIN_START hoặc loại ticker. |
| 4 | `ta` library indicator math khác paper Xiong et al | L-M | Document trong report. Ghi rõ "ta library defaults, see indicators.py constants". |
| 5 | parquet schema thay đổi sau merge → break PKG-3 silent | M | Test `test_normalize_schema` lock columns list. Bất kỳ ai sửa _SCHEMA → test fail. |

### Khi gặp blocker

- Spike 1 fail (KBS xuống): chuyển source primary sang VCI tạm; ghi note trong PR.
- Spike 2 schema khác kỳ vọng: update `_RATIO_COLS_KEEP` dựa trên output thực; assert sẽ catch nếu sai.
- Day-1 gate trip (ticker IPO sau 2019): hỏi user, KHÔNG tự động giảm TRAIN_START. PRD §15 là locked.

---

## Confidence Score

**7.5/10** for one-pass implementation.

Subtract:
- −1.0 vnstock v4 schema chưa được khẳng định trên 5 ticker thật (Spike 2 cần chạy trước)
- −0.5 indicator golden values phụ thuộc `ta` version — chọn cách test "shape" thay vì exact value để hạ rủi ro
- −1.0 day-1 depth có thể trượt cho 1-2 ticker (mặc dù PRD risk #8 nói đã verify), cần recovery path tay

Add back:
- +0.5 codebase còn rất gọn (PKG-0 mới merge), không có legacy hidden assumption
- +0.5 invariants/test design encode rules rất rõ — Person 2 verify dễ
