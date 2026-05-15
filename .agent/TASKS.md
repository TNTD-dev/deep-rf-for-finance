# Task Breakdown — DRL vs LLM/Agentic Trading

> Nguồn: `.agent/PRD.md` v1.0
> Tổng ngân sách: ~14.5 ngày code + report/verify song song · Deadline 2026-05-31
> Team: Duc (code) + Người 1 (report) + Người 2 (verify)

---

## Seam analysis

Các trục độc lập về file (rút từ directory structure ở PRD §6):

| Seam | Owner package | File boundary |
|------|---------------|---------------|
| Data — giá + indicators | PKG-1 | `src/data_pipeline/{vnstock_prices,indicators,calendar}.py` |
| Data — fundamentals (moved) | PKG-5 | `src/data_pipeline/vnstock_fundamentals.py` |
| Data — news | PKG-2 | `src/data_pipeline/news_*.py` |
| Trading env | PKG-3 | `src/trading_env.py` |
| Baselines | PKG-4 | `src/baselines.py` |
| LLM shared (client/tools/serialize) | PKG-5 | `src/llm/{client,tools,serialize}.py` |
| LLM zero-shot | PKG-6 | `src/llm/zero_shot.py` |
| Single-LLM agentic | PKG-7 | `src/llm/single_agentic.py` |
| Multi-agent LangGraph | PKG-8 | `src/llm/multi_agent/*` |
| DDPG/PPO trainer | PKG-9 | `src/ddpg_trainer.py`, `src/ppo_trainer.py` |
| Backtest + metrics | PKG-10 | `src/eval/{backtest,metrics}.py` |
| FastAPI shell | PKG-11 | `backend/{main,routes/backtest,routes/debate}.py` |
| SSE + live route | PKG-12 | `backend/routes/live.py`, `backend/sse.py` |
| Next.js shell + dashboard | PKG-13 | `frontend/app/page.tsx`, charts |
| Detail page | PKG-14 | `frontend/app/agents/[id]/page.tsx` |
| Debate replay UI | PKG-15 | `frontend/app/debate/page.tsx` |
| Live UI | PKG-16 | `frontend/app/live/page.tsx`, `frontend/lib/sse.ts` |

**Serialized infra:** `pyproject.toml`, `src/config.py`, `src/agents/__init__.py` (registry), `.env` — gom vào PKG-0 (làm trước) và PKG-S (làm cuối).

---

## Sprint board snapshot

| Pkg | Title | Estimate | Depends on | Phase | Status |
|-----|-------|----------|------------|-------|--------|
| PKG-0 | Repo scaffolding + config | ½ day | none (serialized first) | P1 | open |
| PKG-1 | Data — vnstock prices (+ indicators) | 1 day | PKG-0 | P1 | open |
| PKG-2 | Data — VN news scraper (RISK) | 1 day | PKG-0 | P1 | open |
| PKG-3 | Trading env (VN rules) | 1 day | PKG-0 | P1 | open |
| PKG-4 | Baselines + random-agent test | ½ day | PKG-3 | P1 | blocked |
| PKG-5 | LLM core (client + tools + serialize) | ½ day | PKG-3 | P2 | blocked |
| PKG-6 | LLM zero-shot agent | ½ day | PKG-5 | P2 | blocked |
| PKG-7 | Single-LLM agentic agent | ½ day | PKG-5 | P2 | blocked |
| PKG-8 | Multi-agent LangGraph (6 roles) | 2 days | PKG-5 | P2 | blocked |
| PKG-9 | DDPG trainer + PPO backup | 1.5 day | PKG-3 | P2 | blocked |
| PKG-10 | Backtest engine + metrics | 1 day | PKG-1, PKG-2, PKG-3, all agents | P2 | blocked |
| PKG-11 | FastAPI shell + cache routes | ½ day | PKG-10 | P3 | blocked |
| PKG-12 | SSE + live mode backend route | 1 day | PKG-11, PKG-8 | P3 | blocked |
| PKG-13 | Next.js shell + comparison dashboard | 1 day | PKG-11 | P3 | blocked |
| PKG-14 | Agent detail page | ½ day | PKG-13 | P3 | blocked |
| PKG-15 | Debate replay UI | ½ day | PKG-13 | P3 | blocked |
| PKG-16 | Live mode UI + SSE client | ½ day | PKG-13, PKG-12 | P3 | blocked |
| PKG-S | Serialized integration + rehearsal | 1 day | tất cả | P4 | blocked |

**Merge order (DAG)**

```
PKG-0 ──┬── PKG-1 ─┐
        ├── PKG-2 ─┤
        └── PKG-3 ─┼── PKG-4
                   ├── PKG-5 ─┬── PKG-6 ──┐
                   │          ├── PKG-7 ──┤
                   │          └── PKG-8 ──┤
                   └── PKG-9 ─────────────┴── PKG-10 ── PKG-11 ─┬── PKG-13 ─┬── PKG-14
                                                                │           ├── PKG-15
                                                                └── PKG-12 ─┴── PKG-16
                                                                                  │
                                                                              PKG-S
```

**Human decision gates (resolve trước khi unblock package liên quan)**
- [ ] CHECKPOINT 16/05: news coverage ≥ 50%? → blocking continuation of PKG-2 → PKG-10
- [ ] CHECKPOINT 24/05: multi-agent + FE on track? → có thể cut-path PKG-8/PKG-15/PKG-16

---

## Packages

```
=========================================
PKG-0: Repo scaffolding + config
Labels: ~p1 ~serialized
Phase: 1 (14/05 morning)
Estimate: ½ day
=========================================

## Goal
Tạo bộ khung repo cho mọi package sau cắm vào: pyproject, config module, env template, directory tree, base CLAUDE.md.

## Depends on
none — phải làm đầu tiên.

## Scope

**Create**
- `pyproject.toml` — deps: vnstock>=4.0, stable-baselines3, gymnasium, ta, langgraph, langchain-openai, openai, fastapi, uvicorn, pandas, pyarrow, pytest, ruff
- `.env.example` — OPENAI_API_KEY, MODEL_PRIMARY, MODEL_MINI, train/val/test boundary dates, ticker list, initial capital, fees
- `.gitignore` — .env, __pycache__, .venv, data/raw/, data/processed/, results/, backend/cache/, frontend/node_modules
- `src/config.py` — load env, expose `TICKERS`, `TRAIN_START`, `VAL_START`, `TEST_START`, `TEST_END`, `INITIAL_CAPITAL`, `BUY_FEE`, `SELL_FEE`, `PRICE_BAND`, `LOT_SIZE`
- `src/__init__.py`, `src/data_pipeline/__init__.py`, `src/llm/__init__.py`, `src/llm/multi_agent/__init__.py`, `src/eval/__init__.py`
- `data/raw/.gitkeep`, `data/processed/.gitkeep`, `results/.gitkeep`, `notebooks/.gitkeep`, `report/.gitkeep`
- `tests/__init__.py`, `tests/test_config.py`
- `CLAUDE.md` — short project conventions: Python 3.11+, ruff, pytest, never commit .env, lookahead-safe rule, VN-specific constants in config

**Modify**
- none

**Do not touch**
- `.agent/PRD.md`, `.agent/plans/`, `docs/` — văn bản đã chốt

## Read before starting
- `.agent/PRD.md` §6 directory structure, §15 locked parameters
- `REQUIREMENTS - DRL vs LLM Agentic Trading.md` nếu còn tồn tại

## Acceptance criteria
- [ ] `pip install -e .` chạy không lỗi
- [ ] `pytest tests/test_config.py` pass — verify mọi constant đọc đúng từ `.env.example`
- [ ] `ruff check src/` pass
- [ ] Tree đầy đủ như PRD §6

## Branch name
`duc/PKG-0-scaffold`
```

```
=========================================
PKG-1: Data — vnstock prices & fundamentals
Labels: ~p1 ~parallel
Phase: 1 (14-15/05)
Estimate: 1 day
=========================================

## Goal
Fetch giá OHLCV + fundamental cho 5 ticker từ 2019-01 đến hôm nay, align theo VN trading calendar, lưu parquet. Verify depth dữ liệu (day-1 risk).

## Depends on
PKG-0

## Scope

**Create**
- `src/data_pipeline/vnstock_prices.py` — `fetch_prices(ticker, start, end)`, retry với fallback backend VCI nếu KBS lỗi
- `src/data_pipeline/indicators.py` — wrapper quanh `ta`: RSI, MACD, SMA(5/20/50), Bollinger, ATR
- `src/data_pipeline/calendar.py` — VN trading calendar, align dates
- `scripts/fetch_data.py` — CLI entry: tải xong → `data/processed/prices.parquet`
- `tests/test_vnstock_prices.py` — fixture nhỏ, test alignment + survivorship + lookahead-safe windowing
- `tests/test_indicators.py` — golden value cho RSI/MACD trên fixture

**Scope change 15/05 (Spike 2 finding):** vnstock community version **giới hạn Finance API chỉ 4 quý gần nhất** (paid Insiders Program để mở khóa full history). Fundamentals lịch sử cho train period 2019-2024 không khả thi với free tier. Quyết định: defer fundamentals khỏi PKG-1, move sang PKG-5 (LLM tools) — `get_fundamentals` tool fetch live 4 quý cuối tại decision time. Tránh fake-historical-fundamentals (lookahead).

**Modify**
- none

**Do not touch**
- `src/data_pipeline/news_*.py` — owned by PKG-2
- `src/trading_env.py` — PKG-3
- `src/config.py` — chỉ đọc, không sửa

## Read before starting
- vnstock v4 docs: https://github.com/thinh-vu/vnstock
- PRD §7 Feature 1, §15 locked parameters

## Acceptance criteria
- [ ] Fetch xong 5 ticker × 7 năm prices, output `data/processed/prices.parquet`
- [ ] `len(df)` mỗi ticker > 1500 trading days (≈ 6 năm × 250)
- [ ] Không có NaN giá close giữa khoảng start–end
- [ ] Test pass: alignment + indicators
- [ ] Day-1 risk verify: depth ≥ 2019-01 cho cả 5 mã (VCB, FPT, HPG, VIC, VNM) — nếu không, log warning rõ và đề xuất rút train start

## Branch name
`duc/PKG-1-data-prices`
```

```
=========================================
PKG-2: Data — VN news scraper (RISK package)
Labels: ~p1 ~parallel ~risk
Phase: 1 (14-15/05) — gate ở 16/05
Estimate: 1 day
=========================================

## Goal
Scrape tin CafeF + VietStock cho test period (2025-05 → today), tag theo ticker, normalize timestamp, gate lookahead-safe ngay từ output schema. Đây là rủi ro lớn nhất của đồ án.

## Depends on
PKG-0

## Scope

**Create**
- `src/data_pipeline/news_scraper.py` — `scrape_cafef(start, end, tickers)`, `scrape_vietstock(start, end, tickers)` qua sitemap; rate-limit + retry
- `src/data_pipeline/news_live.py` — `fetch_live_news()` wrapper quanh `vnstock_news` RSS
- `src/data_pipeline/news_align.py` — normalize timestamp về Asia/Ho_Chi_Minh, tag ticker bằng keyword match + alias map (VCB/Vietcombank/Ngân hàng Ngoại thương ...)
- `scripts/news_coverage_report.py` — CLI: in % ngày có ≥1 tin/ticker, % ticker có ≥1 tin/ngày → output cho CHECKPOINT 16/05
- `tests/test_news_align.py` — fixture HTML, test ticker tagging + timestamp normalization

**Modify**
- none

**Do not touch**
- `src/data_pipeline/vnstock_*.py`, `src/data_pipeline/indicators.py` — PKG-1
- `src/trading_env.py` — PKG-3

## Read before starting
- PRD §14 Risk #2, §11 lookahead-safe rule
- CafeF sitemap structure: https://cafef.vn/sitemap.xml (verify trước khi code)

## Acceptance criteria
- [ ] Output `data/processed/news.parquet` schema: `published_at_utc, source, url, title, summary, tickers[list]`
- [ ] Không có row nào `published_at_utc` ở tương lai khi scrape ngày D
- [ ] `python scripts/news_coverage_report.py` in được bảng coverage
- [ ] Test pass

## CHECKPOINT 16/05 — GO/NO-GO
- Coverage 12 tháng ≥ 50% → GO, continue
- Coverage < 50% → trigger fallback:
  - (a) rút test window còn 6 tháng (2025-11 → 2026-04)
  - (b) numeric-only main study + news sub-study
- Quyết định write vào `.agent/plans/checkpoint-16-05.md`

## Branch name
`duc/PKG-2-data-news`
```

```
=========================================
PKG-3: Trading environment (VN rules)
Labels: ~p1 ~parallel
Phase: 1 (15-16/05)
Estimate: 1 day
=========================================

## Goal
Gymnasium env chung cho mọi agent: ±7% band, lot-100 rounding, asymmetric fee, lookahead-safe data window. Pass random-agent smoke test.

## Depends on
PKG-0 (config), không cần data thật ban đầu — dùng fixture.

## Scope

**Create**
- `src/trading_env.py` — class `VNTradingEnv(gym.Env)` với:
  - obs space: `[prices_window, indicators, holdings, cash, news_features_optional]`
  - action space: `Box(-1, 1, (n_tickers,))` continuous target weight
  - `_execute_with_vn_rules(target_weights)`: clamp ±7% band, round to lot-100, apply buy 0.15% / sell 0.25%
  - `_get_state(t)`: chỉ data có `timestamp < T`, news ngày D chỉ visible từ phiên D+1 close
  - hook optional T+2 settlement queue (default off)
- `src/env_data_loader.py` — load parquet, slice theo window
- `tests/test_trading_env.py` — test các invariant:
  - random action không cho phép short (clamp 0 nếu cấu hình long-only)
  - lot-100 rounding chính xác
  - ±7% band không cho giá vượt
  - fee buy < fee sell
  - news ngày D không xuất hiện ở state ngày D
  - reproducibility: cùng seed → cùng trajectory

**Modify**
- none

**Do not touch**
- `src/baselines.py`, agent files

## Read before starting
- PRD §6 design pattern "Execution layer tách khỏi decision layer", §7 Feature 2, §11 success criteria

## Acceptance criteria
- [ ] Random agent chạy 1 năm test data không crash
- [ ] Tất cả invariant test pass
- [ ] Portfolio value chính xác trước/sau 1 step có thể tính tay verify

## Branch name
`duc/PKG-3-trading-env`
```

```
=========================================
PKG-4: Baselines + random-agent E2E
Labels: ~p1 ~sequential
Phase: 1 (16/05)
Estimate: ½ day
=========================================

## Goal
2 baselines (buy-and-hold, equal-weight monthly rebalance) chạy hết test period, validate env stack end-to-end.

## Depends on
PKG-1 (data), PKG-3 (env). Verify được sau PKG-2 cũng nhưng không phụ thuộc.

## Scope

**Create**
- `src/baselines.py` — `BuyAndHold`, `EqualWeightRebalance`, common interface `decide(state) -> action`
- `scripts/run_baselines.py` — chạy cả 2 baseline qua env, save portfolio curve vào `results/baselines/`
- `tests/test_baselines.py` — buy-and-hold: 1 lần buy đầu period, weight giữ nguyên; equal-weight: rebalance đúng monthly

**Modify**
- none

**Do not touch**
- `src/trading_env.py`

## Acceptance criteria
- [ ] Cả 2 baselines chạy end-to-end test period không crash
- [ ] Portfolio curve có shape `(n_test_days, 1)` + ≥ 1 holding luôn > 0 (sanity)
- [ ] Cumulative return so với VN-Index trong cùng kỳ in ra console — verify trực giác

## Branch name
`duc/PKG-4-baselines`
```

```
=========================================
PKG-5: LLM core — client, tools, state serializer
Labels: ~p2 ~parallel
Phase: 2 (17/05)
Estimate: ½ day
=========================================

## Goal
Lớp shared cho cả 3 LLM agents (zero-shot, single-agentic, multi-agent). Tách riêng để 3 package sau làm song song trên file độc lập.

## Depends on
PKG-3 (env state schema)

## Scope

**Create**
- `src/llm/client.py` — wrapper OpenAI: lock model `gpt-4o`/`gpt-4o-mini`, retry với exp backoff, prompt cache support, return `(text, usage)`. Throw nếu user pass model khác.
- `src/llm/tools.py` — function definitions (OpenAI tool spec): `get_price_history(ticker, days)`, `get_indicators(ticker)`, `get_news(date, ticker)`, `get_fundamentals(ticker)` (last 4 quarters from vnstock Finance API — community tier limit, moved here from PKG-1). Mỗi tool đọc qua env-bound data window (lookahead-safe).
- `src/data_pipeline/vnstock_fundamentals.py` — moved from PKG-1. Returns 4-quarter snapshot at fetch time. Caveat: at backtest decision time T, only quarters with `report_date < T - report_lag_days` should be visible — implement lookahead gate in the tool wrapper, not the fetcher.
- `src/llm/serialize.py` — `state_to_text(state)`, `news_to_bullets(news)`, `holdings_to_text(holdings)` — đầu vào cho zero-shot prompt
- `src/llm/parser.py` — `parse_weights_json(text) -> dict[ticker, weight]`, fallback `hold` khi malformed, log parse_failure
- `tests/test_llm_client.py` — mock OpenAI, test retry + model lock
- `tests/test_llm_parser.py` — happy + 3 malformed cases

**Modify**
- none

**Do not touch**
- `src/llm/zero_shot.py`, `src/llm/single_agentic.py`, `src/llm/multi_agent/*` — owned by PKG-6/7/8

## Read before starting
- PRD §7 Feature 4-6, §8 LLM SDK, §14 Risk #3 (model lock)

## Acceptance criteria
- [ ] Model whitelist enforced — pass `gpt-3.5` → raise
- [ ] Parser pass 4 test cases
- [ ] Prompt cache header set

## Branch name
`duc/PKG-5-llm-core`
```

```
=========================================
PKG-6: LLM zero-shot trader
Labels: ~p2 ~parallel
Phase: 2 (17/05)
Estimate: ½ day
=========================================

## Goal
Agent đơn giản nhất: serialize state + headlines → 1 prompt → JSON weights. Làm baseline LLM, ghi parse_failure_rate.

## Depends on
PKG-5

## Scope

**Create**
- `src/llm/zero_shot.py` — `class ZeroShotTrader: decide(state) -> action`
- `src/llm/prompts/zero_shot.md` — system prompt VN: vai trò trader, output schema JSON
- `tests/test_zero_shot.py` — mock client, test decision frequency = weekly, fallback hold khi parse fail

**Do not touch**
- `src/llm/{client,tools,serialize,parser}.py` — PKG-5
- `src/llm/single_agentic.py`, `multi_agent/*` — PKG-7/8

## Acceptance criteria
- [ ] Mock chạy 1 quarter test data, output weights hợp lệ ≥ 95%
- [ ] Weekly cadence — daily call không gọi LLM trừ đúng ngày rebalance

## Branch name
`duc/PKG-6-llm-zeroshot`
```

```
=========================================
PKG-7: Single-LLM agentic trader (tool-using)
Labels: ~p2 ~parallel
Phase: 2 (18/05)
Estimate: ½ day
=========================================

## Goal
1 LLM được phép gọi 4 tools (price/indicator/news/fundamental) tự khám phá data, ra weights. Audit tool-call để đo hallucination.

## Depends on
PKG-5

## Scope

**Create**
- `src/llm/single_agentic.py` — `class SingleAgenticTrader: decide(state)`, max 10 tool iterations, log mỗi tool call
- `src/llm/prompts/single_agentic.md` — system prompt: bạn có 4 tools, hãy điều tra, quyết định
- `tests/test_single_agentic.py` — mock tool returns, test iteration cap + audit log

**Do not touch**
- `src/llm/zero_shot.py`, `multi_agent/*` — PKG-6/8

## Acceptance criteria
- [ ] Audit log file `results/single_agentic/tool_calls.jsonl` ghi đủ mọi call
- [ ] Iteration cap enforced — không có decision nào > 10 tool calls

## Branch name
`duc/PKG-7-llm-single-agentic`
```

```
=========================================
PKG-8: Multi-agent LangGraph (6 roles)
Labels: ~p2 ~sequential ~risk
Phase: 2 (18-22/05)
Estimate: 2 days (lớn nhất — có thể chia 8A/8B nếu cần)
=========================================

## Goal
Full TradingAgents-style stack: 3 Analysts → 2 Researchers debate (≤2 round) → Trader → Risk Manager → Portfolio Manager. Per-portfolio decision, streamable, 30s timeout, transcript lưu full cho replay.

## Depends on
PKG-5 (shared client/tools)

## Cân nhắc split nếu Phase 2 chậm hơn dự kiến
- **PKG-8A** (1 day): LangGraph skeleton + 3 Analysts + transcript store
- **PKG-8B** (1 day): Researchers debate + Trader + Risk Manager + Portfolio Manager + streaming events

## Scope

**Create**
- `src/llm/multi_agent/graph.py` — LangGraph state machine, edges, streaming hook
- `src/llm/multi_agent/state.py` — TypedDict cho state qua các node
- `src/llm/multi_agent/analysts.py` — `technical_analyst`, `news_sentiment_analyst`, `fundamental_analyst` (gpt-4o-mini)
- `src/llm/multi_agent/researchers.py` — `bullish_researcher`, `bearish_researcher` với round cap (gpt-4o)
- `src/llm/multi_agent/trader.py` — tổng hợp (gpt-4o)
- `src/llm/multi_agent/risk_manager.py` — 3 viewpoints aggregate (gpt-4o)
- `src/llm/multi_agent/portfolio_manager.py` — quyết định cuối, output weights (gpt-4o)
- `src/llm/multi_agent/transcript.py` — lưu transcript dict theo date → JSON
- `src/llm/prompts/multi_agent/*.md` — 6 file prompt
- `tests/test_multi_agent_graph.py` — mock LLM, test toàn graph chạy < 30s, debate cap 2 round, transcript đủ 6 role

**Do not touch**
- `src/llm/zero_shot.py`, `single_agentic.py` — PKG-6/7
- `src/llm/{client,tools,serialize,parser}.py` — PKG-5

## Read before starting
- TradingAgents paper (Xiao et al, arxiv 2412.20138)
- LangGraph streaming docs
- PRD §7 Feature 6, §14 Risk #5

## Acceptance criteria
- [ ] 1 decision end-to-end < 30s với real OpenAI call
- [ ] Transcript có đúng 6 role + decision + thời điểm
- [ ] Debate cap 2 round verified
- [ ] Cost report sau 1 quarter test < $15 (sanity)

## CHECKPOINT 24/05 — cut-path nếu blocked
Nếu PKG-8 chưa xong/quá đắt → fallback:
- 3-agent custom (Technical, Fundamental, Trader) không debate
- Bỏ Risk Manager, để Portfolio Manager nhận trực tiếp
Quyết định write vào `.agent/plans/checkpoint-24-05.md`

## Branch name
`duc/PKG-8-multi-agent`
```

```
=========================================
PKG-9: DDPG trainer + PPO backup
Labels: ~p2 ~parallel
Phase: 2 (17-19/05) — chạy song song với LLM packages
Estimate: 1.5 day
=========================================

## Goal
Train DDPG (paper Xiong et al) trên 2019-2024 train + 2025-Q1 val. PPO backup train song song để không bị diverge chặn deadline.

## Depends on
PKG-3 (env)

## Scope

**Create**
- `src/ddpg_trainer.py` — `train_ddpg(env, total_timesteps, save_path)`, sử dụng sb3, save best model trên val
- `src/ppo_trainer.py` — PPO backup, cùng interface
- `configs/ddpg.yaml`, `configs/ppo.yaml` — hyperparams
- `scripts/train_ddpg.py`, `scripts/train_ppo.py` — CLI entry
- `tests/test_ddpg_smoke.py` — train 1000 steps trên fixture env, không NaN, model save/load round-trip

**Do not touch**
- `src/trading_env.py` — PKG-3
- `src/eval/*` — PKG-10

## Read before starting
- Paper Xiong et al + paper Ensemble
- sb3 docs DDPG + PPO

## Acceptance criteria
- [ ] DDPG train xong, val Sharpe ≥ -0.5 (sanity, không phải tốt — chỉ là không diverge hoàn toàn)
- [ ] Nếu Q-value blow up → tự động fallback PPO log warning
- [ ] Model save tại `results/models/ddpg_best.zip`, `ppo_best.zip`

## Branch name
`duc/PKG-9-ddpg`
```

```
=========================================
PKG-10: Backtest engine + metrics
Labels: ~p2 ~sequential
Phase: 2 (22-23/05)
Estimate: 1 day
=========================================

## Goal
Hàm chung chạy tất cả strategy qua test period, tính financial + LLM-specific metrics, lưu artifact cho web app + report đọc lại.

## Depends on
PKG-1, PKG-2, PKG-3, PKG-4, PKG-6, PKG-7, PKG-8, PKG-9 (toàn bộ agents)

## Scope

**Create**
- `src/eval/backtest.py` — `run_backtest(agent, env, start, end) -> result`
- `src/eval/metrics.py` — financial: cumulative_return, sharpe, sortino, max_drawdown, turnover, total_cost; LLM-specific: llm_cost_usd, avg_latency_s, parse_failure_rate, hallucination_rate (cho single-agentic)
- `src/eval/run_all.py` — CLI: chạy 6 strategies, save `results/{agent}/portfolio_curve.parquet`, `holdings.parquet`, `metrics.json`, transcripts (cho multi-agent)
- `src/agents/__init__.py` — registry: mapping name → class (Note: file này SERIALIZED — PKG-S sẽ merge nếu xung đột)
- `tests/test_metrics.py` — golden values: known portfolio curve → expected Sharpe/MDD

**Modify**
- KHÔNG modify agent files

**Do not touch**
- backend/, frontend/

## Read before starting
- PRD §11 Success Criteria, §10 API spec (output schema phải match)

## Acceptance criteria
- [ ] `python -m src.eval.run_all` chạy hết 6 strategies, output cache đầy đủ
- [ ] Reproducibility: 2 lần chạy ra cùng metrics (LLM agent cache reuse)
- [ ] Người 2 verify lookahead-safe trên transcript multi-agent
- [ ] Metrics JSON schema khớp với `GET /backtest/{agent}` ở PRD §10

## Branch name
`duc/PKG-10-backtest`
```

```
=========================================
PKG-11: FastAPI shell + cache routes
Labels: ~p3 ~parallel
Phase: 3 (24-25/05)
Estimate: ½ day
=========================================

## Goal
Backend HTTP layer đọc cache từ PKG-10, serve dashboard + debate replay.

## Depends on
PKG-10

## Scope

**Create**
- `backend/main.py` — FastAPI app, CORS cho localhost, mount routes
- `backend/routes/agents.py` — `GET /agents`
- `backend/routes/backtest.py` — `GET /backtest/{agent}` đọc `results/{agent}/`
- `backend/routes/debate.py` — `GET /debate/{agent}/{date}` đọc transcript
- `backend/cache/__init__.py` — in-memory LRU
- `backend/models.py` — pydantic response schemas khớp PRD §10
- `tests/test_routes_backtest.py` — fixture results dir, test 200 + 404

**Do not touch**
- `backend/routes/live.py` — PKG-12
- frontend/

## Acceptance criteria
- [ ] `uvicorn backend.main:app` start không lỗi
- [ ] curl 3 endpoint trả schema khớp PRD §10
- [ ] Cold start < 2s

## Branch name
`duc/PKG-11-fastapi-shell`
```

```
=========================================
PKG-12: SSE + live mode backend route
Labels: ~p3 ~sequential
Phase: 3 (25-26/05)
Estimate: 1 day
=========================================

## Goal
`POST /live/run` stream SSE từng event từ multi-agent graph chạy real-time.

## Depends on
PKG-11 (shell), PKG-8 (graph với streaming hook)

## Scope

**Create**
- `backend/sse.py` — generic SSE helpers
- `backend/routes/live.py` — `POST /live/run`, fetch live data (vnstock + news RSS), invoke graph với streaming callback, yield events khớp PRD §10
- `backend/live_data.py` — fetch real-time price + news, normalize giống offline schema
- `tests/test_sse.py` — mock graph stream, verify event ordering

**Do not touch**
- `backend/routes/{agents,backtest,debate}.py`

## Acceptance criteria
- [ ] curl `-N` thấy events stream theo thứ tự agent_start → token → agent_complete → decision
- [ ] Mất mạng → graceful error event, không crash app
- [ ] 30s timeout per agent enforced

## Branch name
`duc/PKG-12-sse-live`
```

```
=========================================
PKG-13: Next.js shell + comparison dashboard
Labels: ~p3 ~parallel
Phase: 3 (24-25/05)
Estimate: 1 day
=========================================

## Goal
US-1: trang chủ — overlay portfolio curve 6 strategy + VN-Index, bảng metrics. < 30s là hiểu agent nào thắng.

## Depends on
PKG-11

## Scope

**Create**
- `frontend/package.json`, `next.config.ts`, `tailwind.config.ts`, `tsconfig.json`
- `frontend/app/layout.tsx`, `frontend/app/page.tsx` — comparison dashboard
- `frontend/components/PortfolioChart.tsx` — Recharts line overlay
- `frontend/components/MetricsTable.tsx` — bảng Sharpe/MDD/Return/Cost
- `frontend/lib/api.ts` — fetch `/agents`, `/backtest/{agent}` từ localhost:8000
- `frontend/lib/types.ts` — types khớp pydantic models

**Do not touch**
- `frontend/app/agents/[id]/` — PKG-14
- `frontend/app/debate/` — PKG-15
- `frontend/app/live/` — PKG-16

## Acceptance criteria
- [ ] `npm run dev` → mở `localhost:3000` thấy chart + table
- [ ] Hover line thấy tooltip ngày + giá trị
- [ ] Responsive ≥ 1280px (demo trên laptop)

## Branch name
`duc/PKG-13-frontend-dashboard`
```

```
=========================================
PKG-14: Agent detail page
Labels: ~p3 ~parallel
Phase: 3 (26/05)
Estimate: ½ day
=========================================

## Goal
US-2: detail từng agent — portfolio curve, holdings heatmap, drawdown curve, metrics chi tiết.

## Depends on
PKG-13 (shell + types)

## Scope

**Create**
- `frontend/app/agents/[id]/page.tsx`
- `frontend/components/HoldingsHeatmap.tsx`
- `frontend/components/DrawdownChart.tsx`
- `frontend/components/AgentMetricsDetail.tsx`

**Do not touch**
- `frontend/app/page.tsx`, `frontend/components/{PortfolioChart,MetricsTable}.tsx` — PKG-13

## Acceptance criteria
- [ ] Click agent từ dashboard → đến `/agents/multi_agent` thấy 4 chart
- [ ] Holdings heatmap đọc đúng 5 ticker × thời gian

## Branch name
`duc/PKG-14-frontend-detail`
```

```
=========================================
PKG-15: Debate replay UI
Labels: ~p3 ~parallel
Phase: 3 (26-27/05)
Estimate: ½ day
=========================================

## Goal
US-3: date picker → render transcript multi-agent với role styling.

## Depends on
PKG-13

## Scope

**Create**
- `frontend/app/debate/page.tsx`
- `frontend/components/DebateStream.tsx` — render từng turn với role badge, markdown content
- `frontend/components/DatePicker.tsx`

**Do not touch**
- `frontend/components/SSEStream.tsx` — PKG-16

## Acceptance criteria
- [ ] Chọn date → fetch `/debate/multi_agent/{date}` → render 6 role + decision
- [ ] Role có màu/icon riêng

## Branch name
`duc/PKG-15-frontend-debate`
```

```
=========================================
PKG-16: Live mode UI + SSE client
Labels: ~p3 ~sequential
Phase: 3 (27-28/05)
Estimate: ½ day
=========================================

## Goal
US-4 + US-5: button "Run for today" → SSE stream từng agent suy nghĩ kiểu chat app → quyết định cuối.

## Depends on
PKG-13 (shell), PKG-12 (live route)

## Scope

**Create**
- `frontend/app/live/page.tsx`
- `frontend/components/SSEStream.tsx` — `useEventSource`, accumulate tokens theo role, animate
- `frontend/lib/sse.ts` — wrapper EventSource với reconnect

**Do not touch**
- `frontend/app/debate/page.tsx`

## Acceptance criteria
- [ ] Click "Run for today" → thấy text streaming theo từng agent
- [ ] Mất mạng giữa stream → hiển thị error banner, không crash
- [ ] Decision cuối hiển thị weights cho 5 ticker

## Branch name
`duc/PKG-16-frontend-live`
```

```
=========================================
PKG-S: Serialized integration + rehearsal
Labels: ~p4 ~serialized ~blocked
Phase: 4 (30-31/05)
Note: unblock chỉ khi tất cả package trên đã merge
=========================================

## Why serialized
Touch shared files + cần state cuối của mọi component:

| File | Reason | Touched by |
|------|--------|------------|
| `src/agents/__init__.py` | registry mapping name → class | PKG-6,7,8,9,10 |
| `src/config.py` | final tuning số liệu | PKG-1,2,3,8,9 |
| `pyproject.toml` | dep manifest cuối | PKG-1..16 |
| `README.md` | runbook đầy đủ | tất cả |

## Tasks (in order)

**S1: Resolve registry conflicts**
- Merge mọi agent vào `src/agents/__init__.py`
- Validate: `python -m src.eval.run_all` chạy được không lỗi import

**S2: End-to-end demo dry-run**
- Bật `uvicorn backend.main:app` + `npm run dev`
- Click qua đủ 4 page (dashboard, detail, debate, live)
- Validate: không có error console + tất cả route 200

**S3: Offline mode toggle**
- Thêm flag `OFFLINE_MODE` trong `.env`, live route trả 503 friendly khi bật
- Validate: tắt wifi, demo vẫn chạy cache

**S4: Loom fallback recording**
- Record 60s clean run multi-agent debate
- Save `report/demo_fallback.mp4`
- Validate: video phát được, có audio

**S5: Report integration support**
- Generate final `results/metrics_table.csv` cho Người 1
- Export 4 chart PNG vào `report/figures/`
- Validate: Người 1 confirm đủ tài liệu cho slide

**S6: Rehearsal**
- Chạy thử end-to-end 2 lần với timer
- Verify mọi cut-path còn hoạt động

## Acceptance criteria (final go for defense)
- [ ] Demo end-to-end 5 phút không crash
- [ ] Mọi unit test pass, ruff clean
- [ ] Loom video sẵn sàng
- [ ] Người 2 ký off "no lookahead bias"
- [ ] Người 1 đã có đủ chart + metrics cho slide
```

---

## Output report

```
Task Breakdown Complete
=======================
PRD: .agent/PRD.md

Parallel (cùng phase, file độc lập):
  P1: PKG-1, PKG-2, PKG-3            — 3 packages, ~3 person-days
  P2: PKG-6, PKG-7, PKG-9            — 3 packages parallel sau PKG-5
  P3: PKG-13/14/15 (FE), PKG-11 (BE) — 4 packages parallel
Sequential:
  PKG-0 → PKG-4 → PKG-5 → PKG-8 → PKG-10 → PKG-11 → PKG-12 → PKG-16
Serialized:
  PKG-S (1 day, last)
Human decision gates: 2
  - CHECKPOINT 16/05 (news coverage)
  - CHECKPOINT 24/05 (multi-agent + FE)

Tổng: 17 work packages
Effort: ~14.5 person-days code + report/verify chạy song song
Phù hợp deadline 17 ngày (14-31/05) — buffer ~2.5 ngày
```

## Notes về team

- **Duc = sole coder** → "parallel" ở đây = packages có thể làm trong các session Claude Code riêng biệt không xung đột file, không phải nhiều người cùng push. Lợi ích: mỗi session focus, PR nhỏ, Người 2 verify được từng phần.
- **Người 1 (report)** chạy song song toàn bộ — pull `results/` artifact theo từng PKG hoàn thành để viết tăng dần, không đợi cuối.
- **Người 2 (verify)** ưu tiên gate sau PKG-3 (env invariant), PKG-2 (news lookahead), PKG-10 (full backtest). Verify package-by-package, không gom cuối.
