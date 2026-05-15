# Requirements Summary: DRL vs LLM/Agentic Stock Trading — Comparative Study (Vietnam Market)

> Chốt qua phiên /grill-me ngày 2026-05-14. Deadline 31/05/2026.

## User Story

**As a** sinh viên làm đồ án DRL Finance,
**I want** thực nghiệm và so sánh DDPG (paper gốc Xiong et al) với 3 phương pháp LLM/agentic hiện đại trên cùng một trading environment cho thị trường chứng khoán Việt Nam,
**so that** đồ án có cả lý thuyết (paper gốc), tính ứng dụng (live demo trên thị trường VN hiện tại), và tính trendy (multi-agent LLM 2024-2026) — đủ ấn tượng với thầy hướng dẫn.

## Scope

### In scope
- Replicate DDPG stock trading từ paper Xiong et al, áp dụng cho thị trường VN
- Build 4 agents để so sánh: DDPG, LLM zero-shot, single-LLM agentic (tool-using), full multi-agent (TradingAgents-style)
- Trading environment chung có model đặc thù VN (±7% band, lot-100)
- 2 baselines: buy-and-hold, equal-weight rebalance
- Full-stack web demo: Next.js + FastAPI với streaming agent debate
- Live mode: chạy agentic stack với giá + tin tức real-time (vnstock_news RSS)
- Report + slides + comparison table

### Out of scope
- Reproduce exact paper (khác thị trường, ticker, thời gian, nguồn data)
- Hybrid RL+LLM (DDPG có state augmented bằng LLM features) — Mức C
- Social/Reddit/Twitter sentiment
- Production deploy public (chỉ localhost demo)
- Market impact, slippage modeling
- UPCOM/HNX small-caps (chỉ VN30)

## Behavior & Rules

### Trading setup
- **Tickers:** VCB, FPT, HPG, VIC, VNM (5 mã VN30, thanh khoản cao, nhiều tin tức)
- **Timeline:**
  - Train: 2019-01 → 2024-12 (6 năm)
  - Validation: 2025-01 → 2025-04
  - Test: 2025-05 → 2026-04 (12 tháng gần nhất)
  - Live demo: 2026-05 → hôm nay (nối tiếp test)
- **State (DDPG):** `[cash, prices, holdings, RSI, MACD, SMA20]`; LLM agents nhận text serialization tương đương
- **Action:** Continuous `[-1,1]^5` (target weights) — env làm tròn xuống bội số 100 khi execute
- **Reward:** `Δportfolio_value − transaction_cost`
- **Transaction cost:** bất đối xứng — buy 0.15%, sell 0.25% (= phí môi giới 0.15% + thuế TNCN chuyển nhượng CK 0.1% chỉ áp khi bán). Đặc thù VN, model đúng để ghi điểm report.
- **Initial capital:** 1,000,000,000 VND (1 tỷ)
- **Frequency:** DDPG daily; LLM/agentic weekly rebalance (thứ 2), env execute daily

### Đặc thù thị trường VN (modeled)
- **Biên độ giá ±7% (HOSE):** clamp giá khớp lệnh trong ±7% so với giá tham chiếu — MODELED
- **Lot size 100:** action continuous → env làm tròn xuống bội số 100 khi execute — MODELED
- **Settlement T+2:** tiền bán không về ngay — NICE-TO-HAVE (model nếu kịp, không thì ghi "Simplifications")
- **Survivorship bias:** 5 mã đã chọn đều niêm yết liên tục + trong VN30 suốt 2019-2026 → fixed basket defensible, NHƯNG phải ghi rõ trong report

### 4 agents to compare
1. **DDPG** — paper gốc, stable-baselines3
2. **LLM Zero-shot Trader** — `gpt-4o-mini`, nhận state + headlines text → trả weights
3. **Single-LLM Agentic** — `gpt-4o-mini` + tools: `get_price_history`, `get_indicators`, `get_news`, `get_fundamentals`
4. **Multi-Agent TradingAgents (full 6.1)** — quyết định **per-portfolio** (không per-stock) để streamable cho demo:
   - 3 Analysts (Technical, News+Sentiment gộp, Fundamental) — `gpt-4o-mini`
   - 2 Researchers debate (Bullish vs Bearish, cap 2 rounds) — `gpt-4o`
   - Trader — `gpt-4o`
   - Risk Manager (3 viewpoints aggregate) — `gpt-4o`
   - Portfolio Manager (final decision) — `gpt-4o`

### Baselines
- Buy-and-Hold (chia đều ngày đầu, giữ tới cuối)
- Equal-Weight Rebalance Monthly

### LLM model lock (chống data leakage)
- Chỉ dùng `gpt-4o` + `gpt-4o-mini` (training cutoff Oct 2023)
- Test period 2025-05 → 2026-04 hoàn toàn out-of-distribution → fair với DDPG
- Ghi rõ trong report: "controlled for training cutoff"

### News lookahead invariant (HARD RULE)
- Cho quyết định tại thời điểm T, chỉ được dùng news có `publish_time < T`
- Vietnamese RSS/sitemap thường chỉ có ngày (không có giờ) → rule: **news ngày D chỉ visible từ phiên D+1 close**
- Bake vào env, không "hy vọng" — đây là lỗi backtest tài chính phổ biến nhất

## Data Sources
- **Prices / OHLCV:** `vnstock` v4.0.0 (backend KBS/VCI auto-route)
- **Technical indicators:** `ta` library (RSI, MACD, SMA, Bollinger)
- **Index / benchmark:** `vnstock` VN-Index + VN30
- **Fundamentals:** `vnstock` financial statements + ratios (P/E, EPS, ROE — quarterly, VN30 OK)
- **News (test period):** scrape sitemap CafeF + VietStock (URL date-stamped) + `vnstock_news`, match ticker bằng keyword
- **News (live mode):** `vnstock_news` RSS (real-time, hoạt động tốt cho tin gần đây)

## Repo Structure

```
deep-rf-for-finance/
├── data/                      # raw + processed
├── src/
│   ├── data_pipeline/         # vnstock fetch, news scraper, alignment
│   ├── trading_env.py         # gym env (VN rules: ±7%, lot-100)
│   ├── baselines.py
│   ├── ddpg_trainer.py
│   ├── llm/
│   │   ├── zero_shot.py
│   │   ├── single_agentic.py
│   │   └── multi_agent/       # LangGraph state machine
│   │       ├── analysts.py
│   │       ├── researchers.py
│   │       ├── trader.py
│   │       ├── risk_manager.py
│   │       └── graph.py
│   └── eval/
│       ├── backtest.py
│       └── metrics.py
├── backend/                   # FastAPI
│   ├── main.py
│   ├── routes/
│   │   ├── backtest.py
│   │   ├── debate.py
│   │   └── live.py            # SSE streaming
│   └── cache/
├── frontend/                  # Next.js 15 + Tailwind + shadcn/ui + Recharts
│   ├── app/
│   ├── components/
│   │   ├── PortfolioChart.tsx
│   │   ├── DebateStream.tsx
│   │   └── AgentCompare.tsx
│   └── lib/
├── notebooks/
│   ├── 01_data_exploration.ipynb
│   ├── 02_env_test.ipynb
│   ├── 03_ddpg_train.ipynb
│   └── 04_results_analysis.ipynb
├── report/
│   ├── paper_summary.md
│   ├── background.md
│   ├── method.md
│   ├── implementation.md
│   ├── results.md
│   └── limitations.md
└── results/
    ├── metrics_table.csv
    ├── portfolio_curves.png
    └── debate_transcripts/
```

## Evaluation Metrics

### Financial (cả 6 strategies: 4 agents + 2 baselines)
- Cumulative return, Annualized return
- Annualized volatility, Sharpe ratio, Sortino ratio
- Max drawdown, Calmar ratio
- Turnover, total transaction cost paid

### LLM-specific (3 LLM agents)
- Total API cost (USD)
- Avg latency / decision
- Total tokens (input/output)
- Parse failure rate (malformed JSON)
- Hallucination rate (LLM "phát minh" giá trị indicator không tồn tại — đo qua tool-call audit log)

### Comparison output
- Bảng metrics 6×N
- Portfolio curve overlay 6 chiến lược + VN-Index
- Per-agent holdings heatmap over time
- Cost-adjusted Sharpe (trừ cost API vào return LLM agents)

## Demo (Web App — 9.2)
- **FastAPI:** `/agents`, `/backtest/{agent}`, `/debate/{agent}/{date}`, `POST /live/run` (SSE streaming)
- **Next.js:** landing + comparison, agent detail, live debate streaming UI (chat-like, token streaming)
- **Live mode:** nút "Run for today" → fetch giá + tin hôm nay → stream toàn bộ quá trình quyết định multi-agent
- **Hosting:** localhost only (tránh leak API key)

## Team Allocation (11.1)
- **Bạn:** toàn bộ code (data, env, DDPG, LLM agents, FE+BE, integration) — dùng Claude Code làm core developer
- **Person 1:** theory write-up — paper_summary, background, method, limitations, slides
- **Person 2:** verification + analysis — review code logic (đặc biệt lookahead bias), implementation.md + results.md, insight comparison

## Edge Cases & Error Handling
- NewsAPI/scrape rate limit → cache aggressive (1 ngày = 1 file), fallback "no news available"
- LLM trả malformed action → retry 1 lần, fail → fallback hold (action zero)
- LLM hallucinate ticker → validate against tickers list, ignore
- DDPG diverge / Q-value explode → fallback PPO backup
- Multi-agent loop → hard cap 2 debate rounds, 30s timeout/decision
- Live demo fail on demo day → cached backtest fallback + **recorded 60s Loom video của clean run** (quay lúc rehearsal)

## Constraints
- **Compute:** DDPG ~100K timesteps trên CPU (~2-3h cho 5 stocks) hoặc Colab GPU free
- **API budget:** ~$30-60 OpenAI (đã có key)
- **LLM models:** `gpt-4o` + `gpt-4o-mini` only (cutoff lock)
- **Deadline:** 31/05/2026 (17 ngày)
- **Localhost demo only**

## Risk Register

| # | Risk | Mitigation |
|---|------|-----------|
| 1 | **Timeline — scope cỡ đồ án tốt nghiệp trong 17 ngày** | Cut-path định sẵn (xem dưới), trigger ngày 10. User commit full-time. |
| 2 | **News scrape VN không đủ coverage** | **Go/no-go checkpoint cuối ngày 2:** nếu coverage 12 tháng <50% → fallback (a) test window ngắn lại 6 tháng, hoặc (b) numeric-only main + news sub-study |
| 3 | **Data leakage qua LLM cutoff** | Model lock Oct 2023 + test period sau cutoff |
| 4 | **Multi-agent debate tốn cost/time** | Per-portfolio decision + 2-round cap + timeout + caching |
| 5 | **Lookahead bias trong news** | Hard rule: news ngày D visible từ D+1, bake vào env |
| 6 | **Live demo fail on demo day** | Cached fallback + recorded Loom video |
| 7 | **VN env phức tạp hơn gym chuẩn** | ±7% + lot-100 modeled (rẻ); T+2 nice-to-have |
| 8 | **Survivorship bias** | 5 mã chọn đều liên tục niêm yết 2019-2026; ghi rõ trong report |

### Cut-path (Mức B-minus) — kích hoạt nếu tới ngày 10 còn tắc
- Multi-agent: full 6-role TradingAgents → custom 3-agent (Technical + Sentiment + Risk → Coordinator)
- Frontend: Next.js custom → Streamlit nếu FE blow up
- Live mode → bỏ, chỉ giữ cached backtest replay
- News-augmented → numeric-only main study + news sub-study trên window ngắn

## Timeline (rough)
```
14-16/05: Data pipeline (vnstock + news scrape) + env (VN rules) + baselines
          → CHECKPOINT ngày 2 (16/05): go/no-go news coverage
17-19/05: DDPG train + LLM zero-shot + single-LLM agentic
20-23/05: Multi-agent LangGraph stack + backtest cả 6 strategies
24-26/05: FastAPI + SSE streaming + Next.js skeleton
          → CHECKPOINT ngày 10 (24/05): trigger cut-path nếu cần
27-29/05: Debate UI + live mode + metrics dashboard + polish
30-31/05: Report integration + slides + rehearsal + record Loom + buffer
```

## Open Questions
- Không còn — tất cả đã chốt qua /grill-me.
- Cần verify thực tế ngày 1-2: vnstock historical depth cho 5 mã từ 2019, và news scrape coverage.
