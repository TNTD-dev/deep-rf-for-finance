# Feature: PKG-2 — VN news scraper (RISK package)

> Đây là rủi ro lớn nhất của thesis (PRD §14 Risk #2). Plan đã đối chiếu PRD/TASKS/CLAUDE.md
> + thực nghiệm trên `Company.news()` của vnstock + sitemap CafeF/VietStock.
> Trước khi code: re-read §"CONTEXT REFERENCES" và §"Pre-implementation spikes".

---

## Feature Description

Build tầng dữ liệu tin tức tiếng Việt cho test period (2025-05 → 2026-04), với 3 yêu cầu nghiêm ngặt:

1. **Coverage đủ:** ≥ 50% ngày trading có ≥ 1 tin/ticker — gate GO/NO-GO ngày 16/05.
2. **Lookahead-safe baked-in schema:** news ngày D chỉ visible từ phiên D+1 close (CLAUDE.md §1) → schema chứa cột `available_for_session` pre-computed, agent không tự handle.
3. **Ticker-tagged đáng tin:** alias-map matching (VCB / Vietcombank / Ngân hàng Ngoại thương) document rõ, test fixture catch false negative.

Output: 1 parquet `data/processed/news.parquet` cho backtest + 1 wrapper RSS cho live mode.

## User Story

As a **Multi-Agent News Analyst (PKG-8 LangGraph node)**
I want to **đọc news đã ticker-tagged cho ngày D-1 close → D open mà không tự lo lookahead**
So that **mỗi quyết định weekly rebalance dùng đúng information set khả thi vào thời điểm đó**.

As a **người verify (Person 2)**
I want to **kiểm tra một câu lệnh duy nhất** (`scripts/news_coverage_report.py`)
So that **CHECKPOINT 16/05 GO/NO-GO ra quyết định dựa trên số liệu thay vì cảm tính**.

## Problem Statement

3 vấn đề độc lập đan vào nhau:

1. **Không có API tin VN tagged-by-ticker historical** — vnstock có `Company.news()` nhưng capped 50 items/ticker (~7-10 tháng). CafeF/VietStock có sitemap public nhưng không tag ticker.
2. **Lookahead bias trong news là silent killer** — timestamp tin VN thường chỉ ngày, agent đọc tin sáng cùng ngày sẽ leak decision context.
3. **Rate limit + bot detection** — CafeF có 200k+ URLs/năm; bị block nếu spam. VietStock từng có Cloudflare WAF.

## Solution Statement

Dual-source strategy đã verify qua probe:

- **Primary: `vnstock.api.company.Company(symbol=t).news()`** → 50 tin ticker-tagged native, public_date ISO, range 7-10 tháng (VCB 2025-09 → 2026-05, FPT 2025-07 → 2026-04, HPG 2025-07 → 2026-05, VIC 2025-10 → 2026-05, VNM 2025-10 → 2026-05). Free, không scrape, không bot risk.
- **Secondary: CafeF sitemap fill-gap** → URL pattern `https://cafef.vn/sitemaps/sitemaps-{Y}-{M}-{D1}-{D2}.xml` (5-day chunks), depth 2016 → present. Fetch ~72 sitemaps cho test period, parse `<loc>` + `<image:title>` (CDATA) + `<lastmod>`, keyword-match tickers trên title.
- **Drop VietStock sitemap** — verified `vietstock.vn/sitemap.xml` chỉ là category index stale từ 2019, không có article-level data. Sub-study riêng nếu thật sự cần.
- **Live mode:** CafeF `latest-news-sitemap.xml` (refresh real-time) — chỉ dùng tin trong N ngày gần nhất.

Lookahead invariant bake vào schema: cột `available_for_session: date` = "trading session đầu tiên mà news này khả dụng cho agent quyết định tại session open". Tính từ `published_at_utc + lookahead_rule(D+1 close)`. Mọi consumer (PKG-3 env, PKG-7 single-agentic, PKG-8 multi-agent) filter `available_for_session <= asof_date` — KHÔNG tự handle timestamp arithmetic.

## Feature Metadata

- **Feature Type:** New Capability (project foundation, RISK package)
- **Estimated Complexity:** **High** — 3 dependencies (vnstock, CafeF, time math), 1 GO/NO-GO checkpoint, lookahead invariant baked into schema
- **Primary Systems Affected:** `src/data_pipeline/{news_fetch,news_scraper,news_align,news_live}.py`, `scripts/news_coverage_report.py`, raw cache `data/raw/news_cache/`, output `data/processed/news.parquet`
- **Dependencies (đã có ở pyproject.toml từ PKG-0):** `httpx>=0.27`, `beautifulsoup4>=4.12`, `lxml>=5.0`, `pandas`, `pyarrow`, `vnstock` (gián tiếp qua `Company.news()`)

---

## CONTEXT REFERENCES

### Relevant Codebase Files — ĐỌC TRƯỚC KHI IMPLEMENT

- `src/data_pipeline/calendar.py` (toàn bộ file, ~37 dòng) — **REUSE bắt buộc**. Đặc biệt `window_until(df, asof_date, date_col)` là single source of truth cho lookahead slicing. PKG-2 thêm helper riêng cho news (`visible_news_at`) nhưng PHẢI build trên cùng nguyên tắc strict `<`.
- `src/data_pipeline/vnstock_prices.py` (toàn bộ, ~75 dòng) — **PATTERN bắt buộc mirror**:
  - Module docstring mô tả contract + deprecation notes
  - `_SCHEMA` constant đứng đầu, output columns lock
  - `_normalize(raw, ...) -> DataFrame` private helper
  - Retry/fallback chain với `noqa: BLE001` comment justify
  - `raise RuntimeError("all sources failed for ...")` khi mọi source fail
- `src/config.py` — đọc `TICKERS`, `TRAIN_START` (cho live news), `TEST_START`, `TEST_END`. KHÔNG sửa.
- `tests/test_vnstock_prices.py` — pattern test với monkeypatch + fake response. Đặc biệt `test_fetch_prices_fallback_to_vci` cho cách monkeypatch một class từ module dưới test.
- `tests/test_calendar.py` — pattern test invariant với docstring giải thích WHY.
- `CLAUDE.md` §"Domain-Specific Rules" §1 (No lookahead bias) — đọc kỹ; news là edge case nhạy cảm nhất.
- `CLAUDE.md` §"Error handling" — log + retry + fallback, never silent-fail; defensive validation chỉ ở scrape boundary.
- `.agent/PRD.md` §7 Feature 1, §11 lookahead-safe rule, §14 Risk #2 + #4.
- `.agent/TASKS.md` PKG-2 block — file ownership, CHECKPOINT 16/05 gate logic.

### New Files to Create

```
src/data_pipeline/
├── news_fetch.py        # PRIMARY: vnstock Company.news() per ticker → DataFrame
├── news_scraper.py      # SECONDARY: CafeF sitemap fetch + parse + ticker-tag
├── news_align.py        # Merge + dedup + lookahead computation (visible_for_session)
└── news_live.py         # Live mode: CafeF latest-news-sitemap.xml + filter recent
scripts/
└── news_coverage_report.py   # CHECKPOINT 16/05 gate report
tests/
├── test_news_fetch.py        # vnstock wrapper, mocked Company.news
├── test_news_scraper.py      # sitemap parse + ticker tagging + alias map
├── test_news_align.py        # timezone normalize + visible_for_session math
└── fixtures/
    ├── cafef_sitemap_index.xml      # mini fixture, 3 sub-sitemaps
    ├── cafef_sitemap_chunk.xml      # mini fixture, 5 articles (2 with ticker)
    └── company_news_response.json   # vnstock Company.news() fixture
data/
├── raw/news_cache/    # cached sitemap XMLs (gitignored)
└── processed/news.parquet  # output (gitignored)
```

### Relevant Documentation — ĐỌC TRƯỚC KHI IMPLEMENT

- **vnstock Company.news() (đã probe):** không có docs public chi tiết. Schema: 21 cols, key fields `ticker`, `news_title`, `news_short_content`, `news_full_content`, `news_source`, `news_source_link`, `public_date`. Cap 50 items/ticker. Source `vci` works; `kbs` returns 1 row only (broken).
- **CafeF sitemap structure (đã probe):**
  - Index: `https://cafef.vn/sitemap.xml` → list of sub-sitemap URLs
  - Sub-sitemap URL pattern: `https://cafef.vn/sitemaps/sitemaps-{YYYY}-{M}-{D1}-{D2}.xml` (5-day chunks, depth back to 2016-12)
  - Sub-sitemap entry schema: `<loc>` (article URL ending in `.chn`), `<lastmod>` (ISO with `+07:00`), `<image:title>` (CDATA, **chứa title bài**), `<priority>`, `<changefreq>`
  - Volume: ~1750 URLs/5-day chunk site-wide (lifestyle + finance + politics + sports — phải filter)
  - Robots: `Allow: /`, no Crawl-delay specified → tự throttle 1s
- **httpx async docs:** https://www.python-httpx.org/async/ — `httpx.AsyncClient` cho concurrent fetch, `timeout=httpx.Timeout(10.0, connect=5.0)`, `headers={"User-Agent": "..."}`.
- **BeautifulSoup lxml parser:** https://beautiful-soup-4.readthedocs.io/en/latest/#installing-a-parser — `BeautifulSoup(xml, "lxml-xml")` cho XML namespaces.
- **Vietnamese diacritic normalization (cho alias matching):** `unicodedata.normalize("NFD", s)` + strip combining chars để match "Vietcombank" với "việt-com-bank" hay "VCB" với "vcb". Document trade-off (false positive risk khi strip diacritics).

### Pre-implementation spikes (chạy 3 lệnh này TRƯỚC khi code)

```bash
# Spike A: verify Company.news() depth cho cả 5 ticker (đã làm, paste output vào PR)
.venv/bin/python -c "
from vnstock.api.company import Company
import pandas as pd
for t in ['VCB','FPT','HPG','VIC','VNM']:
    df = Company(source='vci', symbol=t).news()
    df['public_date'] = pd.to_datetime(df['public_date'])
    print(f'{t}: {len(df)} rows, {df.public_date.min().date()} -> {df.public_date.max().date()}')
"

# Spike B: CafeF sitemap chunk size + title format
curl -s -A 'Mozilla/5.0' 'https://cafef.vn/sitemaps/sitemaps-2025-7-1-5.xml' --max-time 10 | head -50

# Spike C: ticker keyword hit rate on CafeF titles (1 chunk = 5 days mid-July 2025)
.venv/bin/python <<'PY'
import re, httpx
from bs4 import BeautifulSoup
r = httpx.get('https://cafef.vn/sitemaps/sitemaps-2025-7-1-5.xml', headers={'User-Agent':'Mozilla/5.0'}, timeout=15.0)
soup = BeautifulSoup(r.text, 'lxml-xml')
titles = [img.find('image:title').text if img.find('image:title') else '' for img in soup.find_all('url')]
print(f'total: {len(titles)} URLs')
patterns = {
    'VCB': r'\bVCB\b|Vietcombank|Ng[aâ]n h[àa]ng Ngo[aạ]i Th[uư][oơ]ng',
    'FPT': r'\bFPT\b',
    'HPG': r'\bHPG\b|H[oò]a Ph[aá]t',
    'VIC': r'\bVIC\b|Vingroup',
    'VNM': r'\bVNM\b|Vinamilk',
}
for t, p in patterns.items():
    n = sum(1 for x in titles if re.search(p, x, re.IGNORECASE))
    print(f'  {t}: {n} matches in 5-day chunk')
PY
```

**Spike C output** sẽ tell us: nếu mỗi 5-day chunk match ~5 tin/ticker → 365 ngày / 5 = 73 chunks × 5 = ~365 tin/ticker. Với vnstock 50 thêm → tổng ~400/ticker. Coverage 50% gate đạt được dễ.

Nếu Spike C cho < 1 match/chunk → CafeF chunks nặng về lifestyle, plan B: scrape category page `/thi-truong-chung-khoan.chn` thay vì sitemap.

### Patterns to Follow (từ codebase đã land)

**Module shape (mirror `src/data_pipeline/vnstock_prices.py`):**

```python
"""One-paragraph module docstring describing contract + any external API gotchas.

vnstock deprecated X on 2025-08-31 — link to migration. CafeF rate limits — link
to robots. State the lookahead invariant if it touches this module.
"""

from __future__ import annotations

import logging
import pandas as pd
from third_party import Foo

log = logging.getLogger(__name__)

_SCHEMA: list[str] = [...]  # output column contract; lock down

def fetch_xxx(...) -> pd.DataFrame:
    """Concise docstring + Args + Returns + Raises sections."""
    ...

def _normalize(raw, ...) -> pd.DataFrame:
    """Private. Validate schema; raise ValueError if columns missing."""
    ...
```

**Retry/fallback (mirror `vnstock_prices.fetch_prices:34-49`):**

```python
last_err: Exception | None = None
for source in sources:
    try:
        result = call(source)
        if not result or result.empty:
            raise ValueError(f"empty response from {source}")
        return _normalize(result, ticker)
    except Exception as e:  # noqa: BLE001 — fallback chain
        log.warning("%s via %s failed: %s", op, source, e)
        last_err = e
raise RuntimeError(f"all sources failed: {last_err}")
```

**Test invariant (mirror `tests/test_calendar.py`):**

```python
def test_<invariant_name>() -> None:
    """Encode WHY this matters. Reference PRD section or CLAUDE.md domain rule.

    Strict `<` (NOT `<=`) — the most common silent-lookahead path is `<=` here.
    """
    df = ...
    assert ...
```

**Error handling (CLAUDE.md §"Error handling"):**
- Network failure → exp backoff (1s, 2s, 4s), max 3 retries, log warning each retry
- Schema drift (missing column) → raise ValueError loud
- Rate-limit response (429/503) → exp backoff với jitter, ESCALATE if 3 consecutive
- Empty result → treat as failure, try next source

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation — vnstock primary fetch + schema lock

**Goal:** Có dữ liệu news từ vnstock cho 5 ticker, schema canonical, lookahead column pre-computed. Nếu chỉ phase này coverage đã đạt > 50% (likely cho FPT, HPG) thì gate có thể pass mà không cần phase 2.

**Tasks:**
- `news_fetch.py`: `fetch_vnstock_news(ticker) -> DataFrame`, wraps `Company(source='vci', symbol=t).news()`, normalize schema
- `news_align.py`: schema constants `NEWS_SCHEMA`, `visible_at_session(news_df, asof_date, calendar) -> DataFrame` helper, `compute_available_for_session(news_df, calendar) -> Series`
- `tests/test_news_fetch.py` + `tests/test_news_align.py`: 8 tests

### Phase 2: Secondary — CafeF sitemap scrape + tag

**Goal:** Fill gap cho early test-period months. Ticker keyword + alias matching.

**Tasks:**
- `news_scraper.py`: `scrape_cafef_sitemap_range(start, end, tickers) -> DataFrame`. Internal: list sub-sitemap URLs from index, fetch each (cached), parse, keyword-filter on title
- Alias-map dict `_TICKER_ALIASES` với 5 ticker × {symbol, English name, Vietnamese name, common abbreviations}
- `tests/test_news_scraper.py`: 6 tests với fixture XML

### Phase 3: Integration — merge + dedup + write + CHECKPOINT report

**Goal:** 1 CLI command output news.parquet + coverage report cho 16/05 gate.

**Tasks:**
- `news_align.py`: `merge_and_dedup(*dfs) -> DataFrame` (dedup by URL, prefer vnstock when URL collision)
- `scripts/news_coverage_report.py`: CLI; load news.parquet, in bảng `% days_with_news_per_ticker`, gate exit 0/1 dựa trên 50% threshold
- Update `scripts/fetch_data.py` (PKG-1) hoặc tạo `scripts/fetch_news.py` riêng — quyết định: **riêng**, tránh đụng file PKG-1

### Phase 4: Live mode wrapper

**Goal:** PKG-12 (live SSE) consume được tin real-time. Chỉ wrapper, không trùng pipeline backtest.

**Tasks:**
- `news_live.py`: `fetch_live_news(tickers, hours=24) -> DataFrame` đọc `https://cafef.vn/latest-news-sitemap.xml`, filter `lastmod >= now - hours`, tag tickers, return same NEWS_SCHEMA. Test riêng.

---

## STEP-BY-STEP TASKS

Execute in order. Mỗi task atomic, VALIDATE command chạy được.

### 1. CREATE `src/data_pipeline/news_align.py` (schema + lookahead helpers FIRST)

- **IMPLEMENT:**
  ```python
  """Canonical news schema + lookahead-safe visibility helpers.

  Lookahead invariant (CLAUDE.md §1, PRD §11): news published on day D is only
  visible to decisions made from session D+1 close onward. For a decision at
  session T open, visible news has `available_for_session <= T`.

  We pre-compute `available_for_session` at ingest time so consumers never do
  timestamp arithmetic themselves.
  """
  from __future__ import annotations
  import pandas as pd
  import unicodedata

  TZ_VN = "Asia/Ho_Chi_Minh"
  NEWS_SCHEMA: list[str] = [
      "published_at_utc",       # datetime64[ns, UTC]
      "available_for_session",  # date — first trading session this news is usable
      "source",                 # "vnstock" | "cafef" | "vietstock" | ...
      "url",                    # canonical URL (may be None for vnstock disclosures)
      "title",                  # str
      "summary",                # str | None (short content / first paragraph)
      "tickers",                # list[str] — non-empty, sorted, unique
  ]

  def to_utc(ts: pd.Series, source_tz: str = TZ_VN) -> pd.Series:
      """Normalize naive timestamps from source_tz → UTC.

      vnstock public_date is ISO without tz, but it's local Asia/Ho_Chi_Minh
      time. CafeF lastmod ISO carries +07:00. We strip to UTC for consistent
      ordering across sources.
      """
      s = pd.to_datetime(ts, errors="coerce", utc=False)
      if s.dt.tz is None:
          s = s.dt.tz_localize(source_tz, ambiguous="NaT", nonexistent="shift_forward")
      return s.dt.tz_convert("UTC")

  def compute_available_for_session(
      published_at_utc: pd.Series,
      trading_calendar: pd.DatetimeIndex,
  ) -> pd.Series:
      """For each news row, find the first trading session D+2 or later.

      Math: news published on date D (Asia/HCM local) is visible from session
      D+1's close → usable for a decision at session D+2's open. So
      available_for_session = first calendar date strictly greater than
      (publication_date + 1 trading day).

      Implementation: convert published_at_utc → local date D; find calendar
      index >= D; advance 2 sessions (D+1 = close, D+2 = next-open consumer).
      """
      vn_dates = published_at_utc.dt.tz_convert(TZ_VN).dt.normalize().dt.tz_localize(None)
      cal = trading_calendar.normalize()
      out = pd.Series(pd.NaT, index=vn_dates.index, dtype="datetime64[ns]")
      for i, d in enumerate(vn_dates):
          idx = cal.searchsorted(d, side="right")  # first session > d (= D+1)
          if idx + 1 < len(cal):
              out.iloc[i] = cal[idx + 1]  # D+2 session
          # else: news too recent, no future calendar — NaT (not usable yet)
      return out

  def visible_news_at(
      news_df: pd.DataFrame,
      asof_session: str | pd.Timestamp,
  ) -> pd.DataFrame:
      """Return news visible at the OPEN of asof_session.

      Filters `available_for_session <= asof_session`. This is the only
      access pattern downstream code should use. Mirrors window_until in
      calendar.py — strict semantic, no fudge.
      """
      asof = pd.to_datetime(asof_session).normalize()
      mask = (news_df["available_for_session"] <= asof) & news_df["available_for_session"].notna()
      return news_df.loc[mask].copy()

  def normalize_for_match(s: str) -> str:
      """Strip Vietnamese diacritics and lowercase for alias matching.

      'Vietcombank' → 'vietcombank', 'Ngân hàng Ngoại Thương' → 'ngan hang
      ngoai thuong'. Risk: false positives on common Vietnamese words; we
      restrict matching to word boundaries in the alias regex.
      """
      nfd = unicodedata.normalize("NFD", s)
      no_diacritic = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
      return no_diacritic.lower()
  ```
- **PATTERN:** Mirror `src/data_pipeline/calendar.py` for the helper-shape and rule documentation in docstrings.
- **IMPORTS:** `pandas`, `unicodedata` (stdlib).
- **GOTCHA #1:** `published_at_utc` MUST be tz-aware UTC. If `to_utc` is bypassed, comparisons silently fail. Test enforces this.
- **GOTCHA #2:** `compute_available_for_session` uses `searchsorted(side="right")` to find STRICT greater-than. Off-by-one here = lookahead leak.
- **GOTCHA #3:** Don't try to be clever and inline `available_for_session` filter inside `fetch_*` functions — keep it as a single helper.
- **VALIDATE:** `.venv/bin/python -c "import pandas as pd; from src.data_pipeline.news_align import to_utc; s = to_utc(pd.Series(['2025-06-15 14:30:00'])); print(s.iloc[0])"` → should print `2025-06-15 07:30:00+00:00`.

### 2. CREATE `tests/test_news_align.py`

- **IMPLEMENT:** 5 tests
  - `test_to_utc_strips_local_offset` — naive ISO → UTC subtracts 7h
  - `test_to_utc_idempotent_on_tz_aware` — tz-aware input passes through
  - `test_compute_available_for_session_is_d_plus_2` — news published Mon → visible Wed (Mon close, Tue close, Wed open consumer)
  - `test_compute_available_for_session_handles_weekend` — news Fri → visible Tue (Fri close, Mon close, Tue open consumer)
  - `test_visible_news_at_strict_le` — boundary: news with `available_for_session == asof` IS visible; > asof is not
  - `test_normalize_for_match_strips_diacritics` — 'Ngân hàng' → 'ngan hang'
- **PATTERN:** Mirror `tests/test_calendar.py` doc style.
- **VALIDATE:** `.venv/bin/pytest tests/test_news_align.py -v`

### 3. CREATE `src/data_pipeline/news_fetch.py`

- **IMPLEMENT:**
  ```python
  """Fetch ticker-tagged news from vnstock Company API (primary source).

  vnstock community caps Company.news() at 50 items per ticker. Range varies:
  VCB ~8 months, FPT ~10 months, VIC/VNM ~7 months (probed 2026-05-15). Source
  'vci' works; 'kbs' returns 1 row only (broken).

  Output schema matches news_align.NEWS_SCHEMA — but `available_for_session` is
  added by the caller (after we have a trading calendar in hand). This module
  emits everything else.
  """
  from __future__ import annotations
  import logging
  import pandas as pd
  from vnstock.api.company import Company
  from src.data_pipeline.news_align import to_utc

  log = logging.getLogger(__name__)

  _VNSTOCK_SCHEMA: list[str] = [
      "published_at_utc", "source", "url", "title", "summary", "tickers",
  ]

  def fetch_vnstock_news(ticker: str, source: str = "vci") -> pd.DataFrame:
      raw = Company(source=source, symbol=ticker).news()
      if raw is None or raw.empty:
          raise RuntimeError(f"empty Company.news for {ticker}")
      return _normalize(raw, ticker)

  def _normalize(raw: pd.DataFrame, ticker: str) -> pd.DataFrame:
      missing = {"public_date", "news_title", "news_short_content"} - set(raw.columns)
      if missing:
          raise ValueError(f"vnstock news schema missing {missing}: cols={raw.columns.tolist()[:10]}")
      df = pd.DataFrame({
          "published_at_utc": to_utc(raw["public_date"]),
          "source": "vnstock",
          "url": raw["news_source_link"].where(raw["news_source_link"].astype(bool), None),
          "title": raw["news_title"].astype(str),
          "summary": raw["news_short_content"].where(raw["news_short_content"].astype(bool), None),
      })
      df["tickers"] = [[ticker]] * len(df)
      df = df[_VNSTOCK_SCHEMA].sort_values("published_at_utc").reset_index(drop=True)
      return df
  ```
- **PATTERN:** Mirror `vnstock_prices.py` shape: `_SCHEMA` constant, `_normalize` private helper, RuntimeError on empty.
- **IMPORTS:** `pandas`, `logging`, `vnstock.api.company.Company`, `src.data_pipeline.news_align.to_utc`.
- **GOTCHA #1:** vnstock `news_source_link` is often empty string, not None. Use `.where(s.astype(bool), None)` to convert empty → None for clean parquet.
- **GOTCHA #2:** `tickers` column is `list[str]` per row — parquet supports via pyarrow but Series construction is fiddly. Use `[[ticker]] * len(df)` not `df["tickers"] = [ticker]` (latter broadcasts a scalar).
- **GOTCHA #3:** No retry/fallback chain like prices — `kbs` is broken for news. Only `vci`. Document this.
- **VALIDATE:** `.venv/bin/python -c "from src.data_pipeline.news_fetch import fetch_vnstock_news; df = fetch_vnstock_news('VCB'); print(df.shape); print(df.head(2))"` → 50 rows, schema lock.

### 4. CREATE `tests/test_news_fetch.py`

- **IMPLEMENT:** 4 tests (all monkey-patch Company)
  - `test_normalize_schema` — output cols exact match `_VNSTOCK_SCHEMA`
  - `test_normalize_raises_on_missing_column` — schema drift → raise
  - `test_normalize_converts_empty_url_to_none` — empty string → None
  - `test_normalize_tickers_is_list_of_one` — each row has `[ticker]`, not scalar
- **VALIDATE:** `.venv/bin/pytest tests/test_news_fetch.py -v`

### 5. CREATE `src/data_pipeline/news_scraper.py`

- **IMPLEMENT:**
  ```python
  """Scrape CafeF sitemap chunks → ticker-tagged news rows.

  CafeF sitemap structure (verified 2026-05-15):
    Index: https://cafef.vn/sitemap.xml
    Chunks: https://cafef.vn/sitemaps/sitemaps-{Y}-{M}-{D1}-{D2}.xml (5-day)
    Entry: <url><loc>...</loc><lastmod>ISO+07:00</lastmod>
                <image:image><image:title>CDATA</image:title></image:image></url>

  We:
    1. List sub-sitemap URLs by date range from index
    2. Fetch each (cached to data/raw/news_cache/)
    3. Parse: url + title + lastmod
    4. Keyword-match title against ticker alias map; keep only matched rows

  Rate limiting: 1s sleep between sitemap fetches (~72 fetches for 12mo → ~75s
  total). Exp backoff (1s, 2s, 4s) on transient HTTP errors. Bot detection:
  use a realistic User-Agent (CLAUDE.md: never claim to be a fake browser
  beyond what's necessary for non-malicious access).
  """
  from __future__ import annotations
  import logging
  import re
  import time
  from datetime import date, timedelta
  from pathlib import Path
  import httpx
  import pandas as pd
  from bs4 import BeautifulSoup
  from src import config
  from src.data_pipeline.news_align import to_utc, normalize_for_match

  log = logging.getLogger(__name__)

  CACHE_DIR: Path = config.PROJECT_ROOT / "data" / "raw" / "news_cache"
  USER_AGENT: str = "deep-rf-finance-research/0.1 (academic; contact: devinnotech1@gmail.com)"

  # Alias map — VERIFY each entry by hand. False positive on "VIC" is common
  # because it's also a 3-letter word in some contexts. Match on word boundary.
  _TICKER_ALIASES: dict[str, list[str]] = {
      "VCB": ["VCB", "Vietcombank", "Ngân hàng Ngoại Thương", "Ngoai Thuong Vietnam Bank"],
      "FPT": ["FPT", "Tập đoàn FPT", "FPT Corporation"],
      "HPG": ["HPG", "Hòa Phát", "Tập đoàn Hòa Phát", "Hoa Phat Group"],
      "VIC": ["VIC", "Vingroup", "Tập đoàn Vingroup"],
      "VNM": ["VNM", "Vinamilk", "Sữa Việt Nam", "Vietnam Dairy Products"],
  }
  # Compiled regex per ticker, applied to normalized (diacritic-stripped) text
  _TICKER_REGEX: dict[str, re.Pattern] = {
      t: re.compile(
          r"(?<!\w)(?:" + "|".join(re.escape(normalize_for_match(a)) for a in aliases) + r")(?!\w)",
          re.IGNORECASE,
      )
      for t, aliases in _TICKER_ALIASES.items()
  }

  def list_sub_sitemaps(start: date, end: date) -> list[str]:
      """Generate CafeF sub-sitemap URLs covering [start, end].

      Format: sitemaps-{Y}-{M}-{D1}-{D2}.xml with D1∈{1,6,11,16,21,26}, D2 the
      next boundary minus 1 (or end of month). Verified by inspecting index.
      """
      urls = []
      cur = date(start.year, start.month, 1)
      while cur <= end:
          for d1 in (1, 6, 11, 16, 21, 26):
              d2 = min(d1 + 4, _last_day_of_month(cur.year, cur.month))
              chunk_end = date(cur.year, cur.month, d2)
              chunk_start = date(cur.year, cur.month, d1)
              if chunk_end < start:
                  continue
              if chunk_start > end:
                  break
              urls.append(
                  f"https://cafef.vn/sitemaps/sitemaps-{cur.year}-{cur.month}-{d1}-{d2}.xml"
              )
          # next month
          cur = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)
      return urls

  def _last_day_of_month(y: int, m: int) -> int:
      nxt = date(y + (m == 12), 1 if m == 12 else m + 1, 1)
      return (nxt - timedelta(days=1)).day

  def _fetch_with_retry(client: httpx.Client, url: str, attempts: int = 3) -> str | None:
      """GET with exp backoff. Returns text or None if all attempts fail."""
      for i in range(attempts):
          try:
              r = client.get(url, timeout=15.0)
              if r.status_code == 200:
                  return r.text
              if r.status_code in (429, 503):
                  log.warning("rate-limited %s (attempt %d), backing off", url, i + 1)
                  time.sleep(2 ** i + 1)
                  continue
              log.warning("unexpected status %d for %s", r.status_code, url)
              return None
          except httpx.HTTPError as e:
              log.warning("HTTP error %s for %s: %s", type(e).__name__, url, e)
              time.sleep(2 ** i)
      return None

  def _load_or_fetch(client: httpx.Client, url: str) -> str | None:
      """File-cache wrapper. Sub-sitemaps are immutable for past months."""
      CACHE_DIR.mkdir(parents=True, exist_ok=True)
      fname = url.rsplit("/", 1)[-1]
      cached = CACHE_DIR / fname
      if cached.exists() and cached.stat().st_size > 0:
          return cached.read_text(encoding="utf-8")
      text = _fetch_with_retry(client, url)
      if text is not None:
          cached.write_text(text, encoding="utf-8")
      return text

  def _parse_chunk(xml: str) -> list[dict]:
      """Parse one sub-sitemap → list of {url, title, lastmod}."""
      soup = BeautifulSoup(xml, "lxml-xml")
      out = []
      for url_el in soup.find_all("url"):
          loc = url_el.find("loc")
          lastmod = url_el.find("lastmod")
          img = url_el.find("image:image")
          title_el = img.find("image:title") if img else None
          if not loc or not title_el:
              continue
          out.append({
              "url": loc.text.strip(),
              "title": title_el.text.strip(),
              "lastmod": lastmod.text.strip() if lastmod else None,
          })
      return out

  def _tag_tickers(title: str) -> list[str]:
      """Apply alias regex on normalized title. Returns sorted list of matches."""
      norm = normalize_for_match(title)
      return sorted(t for t, pat in _TICKER_REGEX.items() if pat.search(norm))

  def scrape_cafef_sitemap_range(start: date, end: date) -> pd.DataFrame:
      """Fetch + parse + ticker-tag CafeF sub-sitemaps in [start, end].

      Only rows with at least one matched ticker are kept. Output rows lack
      `available_for_session` — caller computes after providing a calendar.
      """
      out_rows = []
      with httpx.Client(headers={"User-Agent": USER_AGENT}) as client:
          for url in list_sub_sitemaps(start, end):
              xml = _load_or_fetch(client, url)
              if xml is None:
                  log.warning("skip %s (fetch failed)", url)
                  continue
              for entry in _parse_chunk(xml):
                  tickers = _tag_tickers(entry["title"])
                  if not tickers:
                      continue
                  out_rows.append({
                      "published_at_utc": entry["lastmod"],
                      "source": "cafef",
                      "url": entry["url"],
                      "title": entry["title"],
                      "summary": None,  # sitemap doesn't carry summary; would need article fetch
                      "tickers": tickers,
                  })
              time.sleep(1.0)  # throttle between sub-sitemap fetches
      df = pd.DataFrame(out_rows)
      if df.empty:
          return df.assign(published_at_utc=pd.to_datetime(pd.Series([], dtype="object"), utc=True))
      df["published_at_utc"] = to_utc(df["published_at_utc"])
      return df.sort_values("published_at_utc").reset_index(drop=True)
  ```
- **PATTERN:** Mirror `vnstock_prices.py` for retry+fallback shape; mirror `news_align.py` for module docstring depth.
- **IMPORTS:** `httpx`, `bs4.BeautifulSoup`, `re`, `time`, `pathlib`, `datetime`, `src.config`, `src.data_pipeline.news_align`.
- **GOTCHA #1:** BeautifulSoup with `lxml-xml` parser handles namespace (`image:title`) automatically. Don't use `html.parser` — it'll silently drop tags.
- **GOTCHA #2:** `list_sub_sitemaps` boundary cases: months with different lengths (Feb 28/29, Apr/Jun/Sep/Nov 30). The d1∈{1,6,11,16,21,26} pattern + `min(d1+4, last_day)` covers it. Verified manually.
- **GOTCHA #3:** CafeF lastmod includes `+07:00`; pd.to_datetime handles tz aware automatically. `to_utc` short-circuits when already tz-aware.
- **GOTCHA #4:** Cache files are immutable for past months but **must NOT be cached for the current month** (still being updated). Add `force_refetch_if_current_month` flag if time permits; else accept staleness for current month.
- **GOTCHA #5:** alias matching uses `(?<!\w)...(?!\w)` not `\b...\b` because \b doesn't behave consistently across Unicode word boundaries.
- **VALIDATE:** `.venv/bin/python -c "from datetime import date; from src.data_pipeline.news_scraper import list_sub_sitemaps; urls = list_sub_sitemaps(date(2025,7,1), date(2025,7,31)); print(len(urls)); print(urls[:3])"` → expect ~6 chunks, first chunk `sitemaps-2025-7-1-5.xml`.

### 6. CREATE `tests/test_news_scraper.py`

- **IMPLEMENT:** 6 tests
  - `test_list_sub_sitemaps_5day_chunks` — `(2025,7,1)..(2025,7,31)` returns exactly 6 URLs
  - `test_list_sub_sitemaps_spans_months` — `(2025,7,28)..(2025,8,7)` returns 3 URLs across boundary
  - `test_parse_chunk_extracts_title_and_lastmod` — fixture XML with 3 articles, parse returns 3 rows with correct fields
  - `test_tag_tickers_matches_alias_case_insensitive` — title "Vietcombank công bố lợi nhuận" matches VCB
  - `test_tag_tickers_handles_diacritics` — "Hòa Phát báo cáo" matches HPG (via diacritic strip)
  - `test_tag_tickers_no_false_positive_substring` — "VICOSTONE" (a different company) does NOT match VIC (word boundary)
- **FIXTURE NEEDED:** `tests/fixtures/cafef_sitemap_chunk.xml` — hand-crafted 5-entry mini sitemap with mix of finance + lifestyle titles + 1 VICOSTONE trap.
- **VALIDATE:** `.venv/bin/pytest tests/test_news_scraper.py -v`

### 7. CREATE `src/data_pipeline/news_live.py`

- **IMPLEMENT:**
  ```python
  """Live news source for SSE streaming (PKG-12).

  Reads CafeF's latest-news-sitemap.xml (updated continuously) and filters to
  the last N hours. Uses the same parse + tag pipeline as scrape_cafef_sitemap.
  """
  from __future__ import annotations
  from datetime import datetime, timedelta, timezone
  import httpx
  import pandas as pd
  from src.data_pipeline.news_scraper import (
      USER_AGENT, _parse_chunk, _tag_tickers,
  )
  from src.data_pipeline.news_align import to_utc

  LATEST_URL = "https://cafef.vn/latest-news-sitemap.xml"

  def fetch_live_news(hours: int = 24) -> pd.DataFrame:
      with httpx.Client(headers={"User-Agent": USER_AGENT}) as client:
          r = client.get(LATEST_URL, timeout=15.0)
          r.raise_for_status()
      rows = []
      cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
      for entry in _parse_chunk(r.text):
          tickers = _tag_tickers(entry["title"])
          if not tickers:
              continue
          rows.append({
              "published_at_utc": entry["lastmod"],
              "source": "cafef_live", "url": entry["url"],
              "title": entry["title"], "summary": None, "tickers": tickers,
          })
      if not rows:
          return pd.DataFrame()
      df = pd.DataFrame(rows)
      df["published_at_utc"] = to_utc(df["published_at_utc"])
      df = df[df["published_at_utc"] >= cutoff]
      return df.sort_values("published_at_utc").reset_index(drop=True)
  ```
- **PATTERN:** Reuse private helpers from `news_scraper` (not separate copies — DRY).
- **VALIDATE:** Skip until PKG-12 wires this in. Smoke test: `.venv/bin/python -c "from src.data_pipeline.news_live import fetch_live_news; print(fetch_live_news(hours=72).head())"` → should return ≥ 0 rows.

### 8. CREATE `scripts/fetch_news.py` (orchestrator)

- **IMPLEMENT:**
  ```python
  """CLI: fetch news from all sources, merge, dedup, compute lookahead, write parquet.

  Output: data/processed/news.parquet conforming to NEWS_SCHEMA.
  """
  from __future__ import annotations
  import argparse, logging, sys
  from datetime import date
  import pandas as pd
  from src import config
  from src.data_pipeline.calendar import build_trading_calendar
  from src.data_pipeline.news_fetch import fetch_vnstock_news
  from src.data_pipeline.news_scraper import scrape_cafef_sitemap_range
  from src.data_pipeline.news_align import (
      NEWS_SCHEMA, compute_available_for_session,
  )

  NEWS_OUT = config.PROJECT_ROOT / "data" / "processed" / "news.parquet"
  PRICES_IN = config.PROJECT_ROOT / "data" / "processed" / "prices.parquet"

  def main() -> int:
      logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
      p = argparse.ArgumentParser()
      p.add_argument("--start", default=config.TEST_START, help="news start date YYYY-MM-DD")
      p.add_argument("--end", default=date.today().isoformat())
      p.add_argument("--skip-cafef", action="store_true", help="skip sitemap scrape (vnstock only)")
      args = p.parse_args()

      # Build calendar from prices (PKG-1 output is dependency)
      prices = pd.read_parquet(PRICES_IN)
      cal = build_trading_calendar(prices)

      chunks = []
      # Primary: vnstock per-ticker
      for t in config.TICKERS:
          df = fetch_vnstock_news(t)
          chunks.append(df)
          print(f"vnstock {t}: {len(df)} rows")

      # Secondary: CafeF sitemap (skip if --skip-cafef for quick iteration)
      if not args.skip_cafef:
          s = date.fromisoformat(args.start)
          e = date.fromisoformat(args.end)
          df = scrape_cafef_sitemap_range(s, e)
          chunks.append(df)
          print(f"cafef sitemap: {len(df)} rows ({s} → {e})")

      news = pd.concat(chunks, ignore_index=True)
      # Dedup by URL (prefer vnstock when collision, but URLs rarely collide cross-source)
      news = news.drop_duplicates(subset=["url"], keep="first") if "url" in news.columns else news

      # Compute lookahead-safe visibility column
      news["available_for_session"] = compute_available_for_session(
          news["published_at_utc"], cal
      )
      news = news[NEWS_SCHEMA].sort_values("published_at_utc").reset_index(drop=True)

      NEWS_OUT.parent.mkdir(parents=True, exist_ok=True)
      news.to_parquet(NEWS_OUT, engine="pyarrow", compression="snappy")
      print(f"\nWritten {NEWS_OUT} ({len(news)} rows)")
      return 0

  if __name__ == "__main__":
      sys.exit(main())
  ```
- **VALIDATE:** `.venv/bin/python scripts/fetch_news.py --start 2025-05-01 --end 2026-04-30` → should write parquet; `du -h data/processed/news.parquet`.

### 9. CREATE `scripts/news_coverage_report.py` (CHECKPOINT 16/05 gate)

- **IMPLEMENT:**
  ```python
  """Coverage report for CHECKPOINT 16/05 GO/NO-GO.

  Prints:
    - Per-ticker: % of trading sessions in test period with ≥ 1 news item
    - Overall: % of (ticker, session) cells covered
    - Source split (vnstock vs cafef)
    - Sample headlines for spot check

  Exit code: 0 if overall coverage ≥ 50% (GO), 1 otherwise (NO-GO → fallback).
  """
  from __future__ import annotations
  import sys
  import pandas as pd
  from src import config

  NEWS = config.PROJECT_ROOT / "data" / "processed" / "news.parquet"
  PRICES = config.PROJECT_ROOT / "data" / "processed" / "prices.parquet"
  GATE_THRESHOLD: float = 0.50

  def main() -> int:
      news = pd.read_parquet(NEWS)
      prices = pd.read_parquet(PRICES)

      # Test period sessions only
      test_start = pd.to_datetime(config.TEST_START)
      test_end = pd.to_datetime(config.TEST_END)
      sessions = (
          prices[(prices["date"] >= test_start) & (prices["date"] <= test_end)]
          ["date"].drop_duplicates().sort_values().reset_index(drop=True)
      )
      print(f"Test sessions: {len(sessions)} ({sessions.iloc[0].date()} → {sessions.iloc[-1].date()})")

      # Explode tickers list → one row per (news, ticker)
      exploded = news.explode("tickers").rename(columns={"tickers": "ticker"})
      exploded["session"] = pd.to_datetime(exploded["available_for_session"])
      exploded = exploded[exploded["session"].between(test_start, test_end)]

      per_ticker = []
      for t in config.TICKERS:
          covered = exploded[exploded["ticker"] == t]["session"].nunique()
          pct = covered / len(sessions) if len(sessions) else 0
          per_ticker.append({"ticker": t, "sessions_with_news": covered, "pct": pct})
      tbl = pd.DataFrame(per_ticker)
      print("\n=== PER-TICKER COVERAGE ===")
      print(tbl.to_string(index=False))

      total_cells = len(sessions) * len(config.TICKERS)
      filled = tbl["sessions_with_news"].sum()
      overall = filled / total_cells if total_cells else 0
      print(f"\nOverall coverage: {filled}/{total_cells} = {overall:.1%}")
      print(f"Gate threshold: {GATE_THRESHOLD:.0%}")

      src = news["source"].value_counts()
      print(f"\nSource split:\n{src.to_string()}")

      if overall < GATE_THRESHOLD:
          print(f"\n❌ NO-GO — coverage below threshold. Trigger fallback (TASKS.md PKG-2 §CHECKPOINT).")
          return 1
      print("\n✅ GO — coverage meets threshold.")
      return 0

  if __name__ == "__main__":
      sys.exit(main())
  ```
- **VALIDATE:** `.venv/bin/python scripts/news_coverage_report.py` — exit 0 iff GO. Output goes into `.agent/plans/checkpoint-16-05.md`.

### 10. ADD `data/raw/news_cache/` to `.gitignore` (already covered by `data/raw/*` glob in PKG-0)

- **VALIDATE:** `git check-ignore data/raw/news_cache/sitemaps-2025-7-1-5.xml` → should print the path (means it IS ignored).

### 11. END-TO-END run + paste output into PR

- **IMPLEMENT:**
  ```bash
  .venv/bin/python scripts/fetch_news.py --start 2025-05-01 --end 2026-04-30
  .venv/bin/python scripts/news_coverage_report.py
  ```
- **PATTERN:** Capture both outputs in PR body verbatim.
- **VALIDATE:** Coverage report exit 0 (≥ 50%) → CHECKPOINT 16/05 GO.

---

## TESTING STRATEGY

### Unit Tests (21 new)

- `test_news_align.py` — 6 tests (timezone, lookahead math, diacritic normalize)
- `test_news_fetch.py` — 4 tests (schema, empty handling, list-of-list ticker column)
- `test_news_scraper.py` — 6 tests (sub-sitemap URL math, parse, alias match, false positive guard)
- `test_news_live.py` — 1 smoke test (skipped if no network)
- 3 fixture XML/JSON files in `tests/fixtures/`

Total after PKG-2: 22 (PKG-0/1) + 17 (excluding live smoke) = **39 tests**.

### Integration Tests (manual, captured in PR description)

- Run `scripts/fetch_news.py --start 2025-05-01 --end 2026-04-30`
- Run `scripts/news_coverage_report.py`
- Eyeball 5 random titles per ticker for tagging correctness

### Edge Cases Explicitly Covered

| # | Edge case | Test |
|---|-----------|------|
| 1 | News published Friday → visible Tuesday (weekend) | `test_compute_available_for_session_handles_weekend` |
| 2 | News at month boundary (Apr 30 → May 1 chunk) | `test_list_sub_sitemaps_spans_months` |
| 3 | Title "VICOSTONE..." doesn't match VIC | `test_tag_tickers_no_false_positive_substring` |
| 4 | Diacritic-heavy title "Hòa Phát" matches HPG | `test_tag_tickers_handles_diacritics` |
| 5 | Empty CafeF response → graceful skip | rate-limit retry already tested in scraper |
| 6 | vnstock schema drift (missing column) | `test_normalize_raises_on_missing_column` |
| 7 | tz-naive vnstock public_date → UTC normalize | `test_to_utc_strips_local_offset` |
| 8 | Boundary `available_for_session == asof_date` IS visible | `test_visible_news_at_strict_le` |

### Edge Cases NOT Covered (deferred / out of scope)

- **Live mode rate-limit during defense demo** — PKG-12 problem; we ship cached fallback.
- **CafeF changes sitemap URL pattern** — manual: re-probe in CI weekly, will fail loud.
- **Sentiment scoring** — out of scope (PRD §4 ❌). News passed to LLM as text only.

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
# Expected: 39 passed (22 existing + 17 new in PKG-2, excl live smoke)
```

### Level 3: End-to-end fetch (one-time per PR)

```bash
# Vnstock-only (fast, no scrape) — sanity
.venv/bin/python scripts/fetch_news.py --skip-cafef --start 2025-05-01 --end 2026-04-30

# Full (slow ~2-3 min: ~72 sitemap fetches × 1s + per-fetch latency)
.venv/bin/python scripts/fetch_news.py --start 2025-05-01 --end 2026-04-30

# CHECKPOINT 16/05 gate — exit 0 means GO
.venv/bin/python scripts/news_coverage_report.py
```

### Level 4: Schema sanity

```bash
.venv/bin/python <<'PY'
import pandas as pd
df = pd.read_parquet("data/processed/news.parquet")
print("shape:", df.shape)
print("cols:", df.columns.tolist())
print("sources:", df["source"].value_counts().to_dict())
print("tz of published_at_utc:", df["published_at_utc"].dtype)
print("any future timestamps?", (df["published_at_utc"] > pd.Timestamp.utcnow()).any())
print("\n=== 3 sample per ticker ===")
for t in ['VCB','FPT','HPG','VIC','VNM']:
    rows = df[df["tickers"].apply(lambda lst: t in lst)].head(3)
    for _, r in rows.iterrows():
        print(f"  [{t}] {r['published_at_utc']} {r['title'][:80]}")
PY
```

### Level 5: Regression

```bash
.venv/bin/pytest tests/test_config.py tests/test_calendar.py tests/test_vnstock_prices.py tests/test_indicators.py -v
# All 22 previously-passing tests still green.
```

---

## ACCEPTANCE CRITERIA

Mirrors GitHub Issue #3 + adds explicit lookahead invariants:

- [ ] Output `data/processed/news.parquet` schema = NEWS_SCHEMA
- [ ] Không có row nào `published_at_utc` ở tương lai (schema sanity Level 4)
- [ ] `available_for_session` luôn ≥ `published_at_utc + 1 trading day`
- [ ] `news_coverage_report.py` chạy được, in bảng coverage, exit 0/1 theo gate 50%
- [ ] Tests pass: 39 (22 cũ + 17 mới)
- [ ] PR description chứa output 3 spikes + fetch_news output + coverage report
- [ ] Quyết định checkpoint write vào `.agent/plans/checkpoint-16-05.md`

---

## COMPLETION CHECKLIST

- [ ] Spike A-C chạy thành công, output paste vào PR
- [ ] 4 module trong `src/data_pipeline/` đã write
- [ ] 2 scripts trong `scripts/` đã write
- [ ] 3 test files với 17 tests pass
- [ ] 3 fixture files trong `tests/fixtures/`
- [ ] `ruff check` clean toàn bộ src + tests + scripts
- [ ] `fetch_news.py` chạy đến hết, write parquet thành công
- [ ] `news_coverage_report.py` exit 0 (hoặc 1 + checkpoint-16-05.md có fallback plan)
- [ ] Schema sanity (Level 4) PASS: no future timestamps
- [ ] PR mở với title `PKG-2: VN news scraper (vnstock + CafeF sitemap)`, body `Closes #3`
- [ ] Người 2 verify: spot check 10 random tagged news cho 1 ticker — false positive rate < 10%

---

## NOTES

### Design decisions worth flagging in PR

1. **vnstock `Company.news()` thành primary thay vì CafeF/VietStock sitemap** — discovered qua probe: cho 50 tin/ticker × 7-10 tháng, ticker-tagged native, không scrape risk. PRD §7 không cấm; chỉ chỉ định nguồn không hard-lock. Document trong PR.

2. **VietStock sitemap dropped** — verified `vietstock.vn/sitemap.xml` chỉ là category index stale (lastmod 2017-2019), không article-level. Nếu future cần sub-study riêng, build dedicated.

3. **Lookahead bake into schema (`available_for_session` cột)** thay vì để mỗi consumer tự handle timestamp arithmetic. Reason: single source of truth, easier verify, Person 2 chỉ cần check 1 hàm thay vì N callsite.

4. **Alias matching dùng normalized (diacritic-stripped) text + word boundary** — false positive trade-off acceptable cho lifestyle news vs financial news ratio. Test `test_tag_tickers_no_false_positive_substring` guard VIC vs VICOSTONE.

5. **Cache CafeF sitemap XMLs trong `data/raw/news_cache/`** — bypass rate limit cho lần chạy thứ 2+. Acceptable vì past chunks là immutable.

6. **No retry chain across multiple news sources** — vnstock và cafef có schema khác nhau, không thể cross-fallback. Mỗi source độc lập với try/log/skip semantic.

### Risks specific to PKG-2

| # | Risk | Likelihood | Mitigation |
|---|------|-----------|------------|
| 1 | Coverage gate fail < 50% | M (worst case 50% bordering) | Fallback paths đã document trong TASKS.md PKG-2 + issue #3. Coverage report exit code automate. |
| 2 | CafeF block IP / 403 burst | L-M | User-Agent realistic, 1s throttle, cache. If blocked: fallback to vnstock-only (still likely > 50% for FPT/HPG). |
| 3 | vnstock community caps news at 50 / lowers further | L | Probe in spike A on every fresh PR. If drops, escalate (similar to PKG-1 fundamentals scope shift). |
| 4 | Ticker alias false positive (e.g. "Vinhomes" tagged VIC) | M | Spot check 10 random tagged news per ticker; tighten regex if false positive rate > 10%. |
| 5 | News published outside trading hours boundary edge case | L | `compute_available_for_session` strictly uses `> D` then `+1 session`, never breaks the rule. Tests cover boundary. |
| 6 | Sitemap chunk schema change | L | First fetch each session re-validates `<image:title>` exists; raise loud if drift. |

### Khi gặp blocker

- Spike A fail (vnstock news rate-limited / capped lower): fall back to CafeF-only run, accept lower coverage, write checkpoint-16-05.md với fallback plan (a) rút test 6 tháng.
- Spike B fail (CafeF sitemap URL pattern changed): manual probe homepage `view-source:https://cafef.vn/sitemap.xml`; update URL builder.
- Spike C cho < 1 match/chunk: regex quá strict; verify alias map; try matching on URL slug too.
- CHECKPOINT 16/05 gate FAIL: STOP. Run report. Discuss with user — chọn fallback (a) hoặc (b). Update PRD §15 if test window rút.

### CHECKPOINT 16/05 decision artifact

Khi gate kích, viết `.agent/plans/checkpoint-16-05.md`:
```
# Checkpoint 16/05 — News Coverage GO/NO-GO

Date: 2026-05-16
Gate: ≥ 50% (ticker, session) cells covered by ≥ 1 news item
Result: [GO | NO-GO]

## Coverage breakdown
[paste news_coverage_report.py output]

## Decision
[GO: continue Phase 2]
[NO-GO: trigger fallback (a) shorten test window to 6 months: 2025-11-01 → 2026-04-30, OR (b) numeric-only main study + news sub-study]

## Rationale
...
```

---

## Confidence Score

**6.5/10** for one-pass implementation. Lower than PKG-1 (7.5) because:

Subtract:
- −1.5 lookahead math (`compute_available_for_session`) là nơi dễ off-by-one nhất trong project; mặc dù có test, vẫn cần human verify
- −1.0 alias matching false positive rate khó dự đoán mà không spot-check thực tế
- −1.0 CafeF sitemap stability: schema có thể đổi giữa khi tôi write code và khi PR ship
- −0.5 GO/NO-GO checkpoint: nếu fail, không phải bug code mà cần quyết định scope

Add back:
- +1.0 vnstock primary đã probe-verify hoạt động + ticker-tagged native
- +0.5 schema baked invariant giảm rủi ro silent lookahead downstream
