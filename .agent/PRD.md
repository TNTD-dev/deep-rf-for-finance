# PRD: DRL vs LLM/Agentic Stock Trading — Comparative Study (Vietnam Market)

> Phiên bản: 1.0 · Ngày: 2026-05-14 · Deadline: 2026-05-31
> Nguồn: chốt qua phiên /grill-me. Xem thêm `REQUIREMENTS - DRL vs LLM Agentic Trading.md`.

---

## 1. Executive Summary

Đồ án thực nghiệm và so sánh **Deep Reinforcement Learning (DDPG)** — phương pháp từ paper gốc Xiong et al — với **3 phương pháp dựa trên LLM/agentic hiện đại (2024-2026)** trong bài toán giao dịch cổ phiếu, áp dụng trên **thị trường chứng khoán Việt Nam (VN30)**. Thay vì chỉ replicate một paper cũ, đồ án mở rộng theo xu hướng AI mới nhất: LLM-as-trader, single-agent tool-using, và full multi-agent debate system (TradingAgents-style).

Sản phẩm gồm 3 trụ: (1) **lý thuyết** — so sánh có insight giữa 4 nhóm agent trên cùng một trading environment; (2) **tính ứng dụng** — web app full-stack với chế độ live chạy trên thị trường VN thời gian thực; (3) **demo ấn tượng** — giao diện streaming hiển thị quá trình "tranh luận" của multi-agent system theo thời gian thực.

**MVP Goal:** Một hệ thống chạy được end-to-end so sánh 4 agents + 2 baselines trên 5 cổ phiếu VN30 (test 2025-05 → 2026-04), kèm web demo có streaming agentic debate và live mode, hoàn thành trước 2026-05-31.

**Core value proposition:** Trả lời bằng dữ liệu thực nghiệm câu hỏi *"RL truyền thống hay LLM/agentic mạnh hơn trong giao dịch chứng khoán Việt Nam, và mạnh ở đâu?"* — với một demo sản phẩm thật, không chỉ notebook.

---

## 2. Mission

**Mission statement:** Biến một bài toán "replicate paper" thành một nghiên cứu so sánh có chiều sâu và một sản phẩm ứng dụng thực, chứng minh được sự tiến hóa từ RL thuần sang AI agentic trong tài chính định lượng.

**Core principles:**
1. **Fair comparison trên hết** — mọi agent chạy cùng environment, cùng test set, cùng metrics; kiểm soát chặt data leakage.
2. **Methodology đúng > kết quả đẹp** — backtest không có lookahead bias; kết quả xấu vẫn có giá trị nếu phân tích đúng.
3. **Đặc thù Việt Nam là điểm mạnh, không phải gánh nặng** — ±7% band, lot-100, T+2 làm đồ án khác biệt.
4. **De-risk bằng checkpoint** — mỗi giai đoạn có go/no-go rõ ràng và cut-path định sẵn.
5. **Demo phải kể được câu chuyện** — streaming debate cho người xem *thấy* được agentic thinking, không chỉ con số.

---

## 3. Target Users

### Primary persona — Thầy hướng dẫn / hội đồng chấm
- **Technical level:** Cao (giảng viên ngành). Hiểu RL, đọc paper, đánh giá methodology.
- **Needs:** Thấy được tính lý thuyết vững, methodology đúng, và sự khác biệt so với "đồ án replicate" thông thường.
- **Pain points:** Đã xem hàng trăm đồ án Jupyter notebook na ná nhau; dị ứng với backtest có lookahead bias / over-claim.

### Secondary persona — Sinh viên/người quan tâm xem demo
- **Technical level:** Trung bình. Có thể không chuyên RL.
- **Needs:** Hiểu nhanh "agent nào thắng" qua biểu đồ; thấy được multi-agent "suy nghĩ" thế nào.
- **Pain points:** Con số khô khan, khó hình dung agentic system làm gì.

### Internal persona — Team 3 người
- **Người code (chủ đề tài):** full-stack, dùng Claude Code làm core developer.
- **Người 1:** viết lý thuyết, báo cáo, slide.
- **Người 2:** verify code (đặc biệt lookahead bias), viết phần implementation + results.

---

## 4. MVP Scope

### ✅ In Scope

**Core Functionality**
- ✅ Replicate DDPG stock trading (paper Xiong et al) cho thị trường VN
- ✅ LLM Zero-shot Trader agent
- ✅ Single-LLM Agentic agent (tool-using)
- ✅ Full Multi-Agent TradingAgents system (LangGraph, 6 vai trò)
- ✅ 2 baselines: buy-and-hold, equal-weight rebalance monthly
- ✅ Trading environment chung có model đặc thù VN (±7% band, lot-100)
- ✅ Backtest engine + metrics computation (financial + LLM-specific)
- ✅ News-augmented decision với lookahead-safe invariant

**Technical**
- ✅ Data pipeline: vnstock v4 (giá, fundamental, index) + news scraper (CafeF/VietStock)
- ✅ FastAPI backend với SSE streaming
- ✅ Next.js 15 frontend (comparison dashboard, agent detail, streaming debate UI)
- ✅ Live mode: chạy agentic stack với dữ liệu real-time

**Integration**
- ✅ OpenAI API (`gpt-4o`, `gpt-4o-mini`)
- ✅ LangGraph cho multi-agent orchestration
- ✅ vnstock_news RSS cho live mode

**Deployment**
- ✅ Localhost demo (chạy trên máy lúc bảo vệ)
- ✅ Recorded Loom video làm fallback demo

### ❌ Out of Scope

- ❌ Reproduce exact paper (khác thị trường, ticker, thời gian, nguồn data)
- ❌ Hybrid RL+LLM — DDPG có state augmented bằng LLM features (Mức C)
- ❌ Social/Reddit/Twitter sentiment data
- ❌ Market impact & slippage modeling
- ❌ UPCOM / HNX small-caps (chỉ VN30)
- ❌ Production deploy public (tránh leak API key)
- ❌ Real-money trading / broker order execution
- ❌ Intraday / high-frequency trading
- ❌ Hyperparameter tuning sâu / neural architecture search
- ❌ Multi-seed variance study (nice-to-have, không bắt buộc MVP)

---

## 5. User Stories

**US-1 — So sánh tổng quan**
> As a thầy hướng dẫn, I want to xem một bảng + biểu đồ so sánh hiệu suất của cả 4 agents và 2 baselines, so that tôi đánh giá được phương pháp nào hiệu quả hơn.
> *Ví dụ:* Mở trang chủ web app → thấy ngay portfolio curve overlay 6 chiến lược + VN-Index, kèm bảng Sharpe/MDD/Return.

**US-2 — Xem chi tiết một agent**
> As a người xem demo, I want to click vào một agent cụ thể, so that tôi thấy được portfolio curve, holdings heatmap, và các metrics chi tiết của riêng nó.
> *Ví dụ:* Click "Multi-Agent" → trang detail hiện đường vốn, lịch sử nắm giữ 5 mã theo thời gian, drawdown curve.

**US-3 — Xem multi-agent "tranh luận"**
> As a người xem demo, I want to chọn một ngày trong quá khứ và xem lại toàn bộ transcript tranh luận của multi-agent system, so that tôi hiểu agentic system ra quyết định như thế nào.
> *Ví dụ:* Date picker → 2025-08-04 → thấy Technical Analyst, Fundamental Analyst, News Analyst phát biểu → Bullish vs Bearish researcher debate → Trader → Risk Manager → quyết định cuối.

**US-4 — Live mode**
> As a thầy hướng dẫn, I want to bấm nút "Run for today" và xem hệ thống chạy thật trên dữ liệu thị trường VN hôm nay, so that tôi tin đây là sản phẩm ứng dụng được, không phải kết quả tĩnh.
> *Ví dụ:* Bấm "Run for today" → fetch giá + tin tức real-time → stream từng agent suy nghĩ → ra khuyến nghị mua/bán cho phiên tới.

**US-5 — Streaming experience**
> As a người xem demo, I want to thấy agentic debate stream ra theo thời gian thực kiểu chat app, so that demo cảm giác sống động và đúng xu hướng LLM 2026.
> *Ví dụ:* "Technical Analyst đang phân tích..." → text token streaming → agent tiếp theo.

**US-6 — Reproduce backtest**
> As a Người 2 (verifier), I want to chạy lại toàn bộ backtest từ command line và nhận đúng metrics đã cache, so that tôi verify được không có lookahead bias và kết quả reproducible.

**US-7 — Hiểu chi phí LLM**
> As a thầy hướng dẫn, I want to xem metrics riêng cho LLM agents (chi phí API, latency, token, parse failure rate), so that tôi đánh giá được tính khả thi thực tế của phương pháp LLM.

**US-8 — Theory write-up**
> As a Người 1 (report lead), I want to có sẵn cấu trúc report và kết quả backtest dưới dạng file/chart, so that tôi viết báo cáo và slide mà không cần đợi code chạy live.

### Technical user stories
**TUS-1** — As a developer, I want trading env tuân thủ ±7% band + lot-100, so that backtest phản ánh đúng ràng buộc thị trường VN.
**TUS-2** — As a developer, I want news được gate theo rule "ngày D visible từ D+1", so that không có lookahead bias.
**TUS-3** — As a developer, I want mọi LLM call lock vào `gpt-4o`/`gpt-4o-mini`, so that test period luôn out-of-distribution.

---

## 6. Core Architecture & Patterns

### High-level architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Data Layer    vnstock v4 ──┐                                │
│                news scraper ─┼──> data/processed/*.parquet   │
│                fundamentals ─┘                                │
├─────────────────────────────────────────────────────────────┤
│  Core Layer    trading_env.py (gym, VN rules)                │
│                ├── DDPG (stable-baselines3)                  │
│                ├── LLM zero-shot                             │
│                ├── single-LLM agentic (tools)                │
│                └── multi-agent (LangGraph state machine)     │
│                baselines.py · backtest.py · metrics.py       │
├─────────────────────────────────────────────────────────────┤
│  Service Layer FastAPI ── routes/{backtest,debate,live}      │
│                SSE streaming · result cache                  │
├─────────────────────────────────────────────────────────────┤
│  Presentation  Next.js 15 ── comparison · detail · debate UI │
└─────────────────────────────────────────────────────────────┘
```

### Directory structure

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
│   │       ├── analysts.py    # Technical, News+Sentiment, Fundamental
│   │       ├── researchers.py # Bullish vs Bearish debate
│   │       ├── trader.py
│   │       ├── risk_manager.py
│   │       └── graph.py       # LangGraph orchestration
│   └── eval/
│       ├── backtest.py
│       └── metrics.py
├── backend/                   # FastAPI
│   ├── main.py
│   ├── routes/{backtest,debate,live}.py
│   └── cache/
├── frontend/                  # Next.js 15
│   ├── app/
│   ├── components/{PortfolioChart,DebateStream,AgentCompare}.tsx
│   └── lib/
├── notebooks/                 # 01_data → 04_results
├── report/                    # paper_summary → limitations
└── results/                   # metrics_table.csv, charts, transcripts
```

### Key design patterns
- **Shared environment, pluggable agent** — mọi agent implement cùng interface `decide(state) -> action`; env không biết agent là RL hay LLM.
- **Execution layer tách khỏi decision layer** — agent output continuous `[-1,1]` target weight; env layer làm tròn lot-100, clamp ±7%, áp transaction cost. Cho phép DDPG giữ continuous action mà vẫn tuân thủ ràng buộc VN.
- **Lookahead-safe data access** — env chỉ expose data có `timestamp < T`; news ngày D chỉ visible từ phiên D+1 close.
- **State machine cho multi-agent** — LangGraph node = vai trò, edge = luồng quyết định; streaming built-in.
- **Cache-first cho demo** — backtest results pre-computed và cache; web app đọc cache, chỉ live mode gọi LLM thật.
- **Per-portfolio decision** — multi-agent ra quyết định cho cả danh mục (không per-stock) → streamable, latency thấp cho demo.

---

## 7. Tools / Features

### Feature 1 — Data Pipeline
- **Purpose:** Cung cấp dữ liệu sạch, aligned, lookahead-safe cho mọi agent.
- **Operations:** fetch OHLCV (vnstock), compute indicators (`ta`), fetch fundamentals (vnstock), scrape news (CafeF/VietStock sitemap), align theo trading calendar, tag news theo ticker.
- **Key features:** caching theo ngày, survivorship-aware ticker list, news timestamp normalization.

### Feature 2 — Trading Environment
- **Purpose:** Môi trường MDP chung mô phỏng thị trường VN.
- **Operations:** `reset()`, `step(action)`, `_get_state()`, `_execute_with_vn_rules()`, `_calculate_portfolio_value()`.
- **Key features:** ±7% price band clamp, lot-100 rounding, asymmetric transaction cost (buy 0.15% / sell 0.25%), optional T+2 settlement queue, lookahead-safe data window.

### Feature 3 — DDPG Agent
- **Purpose:** Baseline RL từ paper gốc.
- **Operations:** train (stable-baselines3 DDPG), predict, save/load.
- **Key features:** PPO backup fallback nếu DDPG diverge; continuous action space.

### Feature 4 — LLM Zero-shot Trader
- **Tool design:** không có tool — nhận state + headlines serialize thành text → output JSON weights.
- **Key features:** retry-on-malformed, fallback hold.

### Feature 5 — Single-LLM Agentic Trader
- **Tool design:** `get_price_history`, `get_indicators`, `get_news`, `get_fundamentals`.
- **Key features:** tool-call audit log (đo hallucination rate), max iteration cap.

### Feature 6 — Multi-Agent TradingAgents System
- **Tool design (LangGraph nodes):**
  - 3 Analysts (Technical / News+Sentiment / Fundamental) — `gpt-4o-mini`
  - 2 Researchers debate (Bullish / Bearish, cap 2 rounds) — `gpt-4o`
  - Trader (tổng hợp) — `gpt-4o`
  - Risk Manager (3 viewpoints aggregate) — `gpt-4o`
  - Portfolio Manager (final decision) — `gpt-4o`
- **Key features:** per-portfolio decision, streaming transcript, 30s timeout/decision, 2-round debate cap, full transcript lưu cho replay.

### Feature 7 — Backtest & Metrics Engine
- **Purpose:** Chạy mọi agent qua test period, tính metrics.
- **Key features:** reproducible, financial metrics + LLM-specific metrics, cost-adjusted Sharpe.

### Feature 8 — Web Demo
- **Purpose:** Trình diễn kết quả + agentic thinking.
- **Key features:** comparison dashboard, agent detail page, streaming debate UI, live mode với SSE.

---

## 8. Technology Stack

### Backend / Core
| Thành phần | Công nghệ | Ghi chú |
|---|---|---|
| Language | Python 3.11+ | |
| RL framework | `stable-baselines3` | DDPG + PPO backup |
| Env | `gymnasium` | custom trading env |
| LLM orchestration | `langgraph` | multi-agent state machine |
| LLM SDK | `openai` | `gpt-4o`, `gpt-4o-mini` only |
| API server | `fastapi` + `uvicorn` | SSE streaming |
| Data — VN stocks | `vnstock` v4.0.0 | giá, fundamental, index |
| Data — VN news | `vnstock_news` + custom scraper | RSS + sitemap CafeF/VietStock |
| Indicators | `ta` | RSI, MACD, SMA, Bollinger |
| Data wrangling | `pandas`, `numpy`, `pyarrow` | |

### Frontend
| Thành phần | Công nghệ |
|---|---|
| Framework | Next.js 15 (App Router) |
| Styling | Tailwind CSS + shadcn/ui |
| Charts | Recharts |
| Streaming | EventSource (SSE) |

### Third-party integrations
- **OpenAI API** — đã có key. Models lock: `gpt-4o`, `gpt-4o-mini`.
- **vnstock backends** — KBS (primary), VCI (fallback), auto-route.

### Optional / nice-to-have
- `torch` (GPU acceleration cho DDPG nếu có)
- Google Colab (free GPU fallback cho training)

---

## 9. Security & Configuration

### Authentication / Authorization
- Không có auth — app chạy localhost cho demo cá nhân.
- **Không deploy public** → không cần auth layer, tránh rủi ro abuse API key.

### Configuration management
- `.env` file: `OPENAI_API_KEY`, model names, ngày train/val/test boundaries, ticker list, transaction cost rate, initial capital.
- `.env` **không commit** (thêm vào `.gitignore`).
- Config tập trung trong `src/config.py`, đọc từ env với default values.

### Security scope
**In scope:**
- ✅ API key trong `.env`, không hardcode, không commit
- ✅ Rate-limit awareness với vnstock (60 req/min) và OpenAI

**Out of scope:**
- ❌ Authentication / user management
- ❌ Public deployment hardening
- ❌ Input sanitization cho external users (không có external users)

### Deployment considerations
- Chạy `localhost` lúc bảo vệ.
- Backup: recorded Loom video 60s clean run.
- Offline mode toggle: nếu mất mạng, web app đọc cache, live mode disable.

---

## 10. API Specification

Base URL: `http://localhost:8000`

### `GET /agents`
Trả về danh sách agents + baselines.
```json
{ "agents": ["ddpg", "llm_zeroshot", "single_agentic", "multi_agent"],
  "baselines": ["buy_and_hold", "equal_weight"] }
```

### `GET /backtest/{agent}`
Trả về kết quả backtest đã cache cho một agent.
```json
{ "agent": "multi_agent",
  "portfolio_curve": [{"date": "2025-05-02", "value": 1003200000}, ...],
  "holdings": [{"date": "...", "VCB": 1200, "FPT": 800, ...}],
  "metrics": { "cumulative_return": 0.18, "sharpe": 1.42, "max_drawdown": -0.11,
               "turnover": 2.3, "total_cost": 4500000,
               "llm_cost_usd": 12.4, "avg_latency_s": 6.2, "parse_failure_rate": 0.01 } }
```

### `GET /debate/{agent}/{date}`
Trả về transcript multi-agent cho một ngày (chỉ áp dụng `multi_agent`).
```json
{ "date": "2025-08-04",
  "transcript": [
    { "role": "technical_analyst", "content": "RSI VCB đang ở 71, quá mua..." },
    { "role": "bullish_researcher", "content": "..." },
    { "role": "portfolio_manager", "content": "...", "decision": {"VCB": 0.15, "FPT": 0.30, ...} } ] }
```

### `POST /live/run`  (SSE streaming)
Trigger agentic pipeline với dữ liệu real-time. Stream từng event.
```
event: agent_start    data: {"role": "technical_analyst"}
event: token          data: {"role": "technical_analyst", "text": "RSI..."}
event: agent_complete data: {"role": "technical_analyst", "summary": "..."}
...
event: decision       data: {"weights": {"VCB": 0.2, ...}, "rationale": "..."}
```
- Auth: không (localhost).
- Request body: `{ "tickers": ["VCB","FPT","HPG","VIC","VNM"] }` (optional, default full list).

---

## 11. Success Criteria

### MVP success definition
Hệ thống chạy được end-to-end: 4 agents + 2 baselines hoàn thành backtest trên test period 2025-05 → 2026-04, web app hiển thị so sánh + streaming debate + live mode hoạt động, report có đủ chart và bảng metrics — tất cả trước 2026-05-31.

### Functional requirements
- ✅ Data pipeline lấy được giá + fundamental + news cho 5 mã, lookahead-safe
- ✅ Trading env tuân thủ ±7% band + lot-100, pass random-agent test
- ✅ DDPG train được, không diverge (hoặc PPO backup hoạt động)
- ✅ 3 LLM agents chạy hết test period, parse failure rate < 5%
- ✅ Multi-agent system hoàn thành 1 decision < 30s
- ✅ Backtest reproducible — chạy lại ra cùng metrics
- ✅ Web app: comparison + detail + debate replay + live mode đều hoạt động
- ✅ SSE streaming mượt, không hang trên demo

### Quality indicators
- Không có lookahead bias (Người 2 verify pass)
- Metrics table đầy đủ financial + LLM-specific
- Report có phân tích insight, không chỉ con số
- Code reproducible từ command line

### User experience goals
- Thầy hiểu được "agent nào thắng" trong < 30 giây nhìn trang chủ
- Streaming debate cảm giác sống động, đúng xu hướng LLM 2026
- Live mode chạy không lỗi trong buổi bảo vệ (hoặc fallback video sẵn sàng)

---

## 12. Implementation Phases

### Phase 1 — Data & Environment (14/05 → 16/05)
**Goal:** Có dữ liệu sạch và environment chạy được.
**Deliverables:**
- ✅ Data pipeline: vnstock fetch giá + fundamental cho 5 mã từ 2019
- ✅ News scraper CafeF/VietStock cho test period
- ✅ Trading env với VN rules (±7%, lot-100)
- ✅ 2 baselines
- ✅ Random agent test pass
**Validation — CHECKPOINT NGÀY 2 (16/05):** go/no-go news coverage. Nếu coverage 12 tháng < 50% → kích hoạt fallback (rút test window còn 6 tháng / numeric-only main + news sub-study).

### Phase 2 — Agents & Backtest (17/05 → 23/05)
**Goal:** Cả 4 agents chạy xong backtest.
**Deliverables:**
- ✅ DDPG train + backtest (+ PPO backup)
- ✅ LLM zero-shot agent
- ✅ Single-LLM agentic agent
- ✅ Multi-agent LangGraph stack (6 vai trò)
- ✅ Backtest cả 6 strategies + metrics table + charts
**Validation:** metrics table đầy đủ, transcripts lưu, không lookahead bias.

### Phase 3 — Web Demo (24/05 → 29/05)
**Goal:** Web app hoàn chỉnh.
**Deliverables:**
- ✅ FastAPI + routes + SSE streaming
- ✅ Next.js: comparison dashboard + agent detail + debate replay UI
- ✅ Live mode với vnstock_news RSS
**Validation — CHECKPOINT NGÀY 10 (24/05):** nếu multi-agent hoặc FE còn tắc → kích hoạt cut-path (3-agent custom / Streamlit / bỏ live mode).

### Phase 4 — Report & Polish (30/05 → 31/05)
**Goal:** Sẵn sàng bảo vệ.
**Deliverables:**
- ✅ Report integration (theory + implementation + results + limitations)
- ✅ Slides
- ✅ Rehearsal + record Loom fallback video
- ✅ Bug fix + buffer
**Validation:** demo chạy offline được, mọi path cố định, fallback sẵn sàng.

---

## 13. Future Considerations

**Post-MVP enhancements:**
- Mức C — Hybrid RL+LLM: DDPG có state augmented bằng LLM sentiment features
- Multi-seed variance study cho DDPG (5 seeds + variance band)
- Mở rộng universe: full VN30 thay vì 5 mã
- Turbulence index / regime detection (như paper Ensemble)
- Ensemble strategy DDPG + PPO + A2C (paper thứ 2)

**Integration opportunities:**
- Social sentiment (StockTwits VN / forum F319) nếu có nguồn data
- Broker API integration (DNSE/SSI FastConnect) cho paper-trading thật
- Deploy public lên HuggingFace Spaces với rate limit + auth

**Advanced features:**
- Time-travel replay slider qua cả test period
- T+2 settlement modeling đầy đủ
- Fine-tune small model trên Vietnamese financial text
- Reflection/memory cho agents (FinAgent-style)

---

## 14. Risks & Mitigations

| # | Risk | Mitigation |
|---|------|-----------|
| 1 | **Timeline — scope cỡ đồ án tốt nghiệp trong 17 ngày.** Claude Code tăng tốc viết code nhưng không rút ngắn training time, debug, rehearsal. | Cut-path (Mức B-minus) định sẵn, trigger ngày 10. User commit full-time. Mỗi phase có validation gate. |
| 2 | **News scrape VN không đủ coverage** — không có API news lịch sử tagged-by-ticker. | Go/no-go checkpoint cuối ngày 2: nếu coverage < 50% → rút test window 6 tháng, hoặc numeric-only main + news sub-study. |
| 3 | **Data leakage qua LLM training cutoff** — model "nhớ" tương lai. | Lock `gpt-4o`/`gpt-4o-mini` (cutoff Oct 2023); test period 2025-05→2026-04 hoàn toàn out-of-distribution. |
| 4 | **Lookahead bias trong news** — timestamp VN thường chỉ có ngày. | Hard rule: news ngày D chỉ visible từ phiên D+1 close. Bake vào env. Người 2 verify. |
| 5 | **Multi-agent debate tốn cost/time, có thể loop.** | Per-portfolio decision, 2-round debate cap, 30s timeout, prompt caching. Budget ~$30-60. |
| 6 | **Live demo fail trong buổi bảo vệ** — streaming hang, mất mạng. | Cached backtest fallback + offline mode toggle + recorded 60s Loom video quay lúc rehearsal. |
| 7 | **DDPG diverge / Q-value explode.** | PPO backup agent train sẵn song song. |
| 8 | **Survivorship bias** trong việc chọn 5 mã. | 5 mã (VCB, FPT, HPG, VIC, VNM) đều niêm yết liên tục + trong VN30 suốt 2019-2026; ghi rõ trong report. |

---

## 15. Appendix

### Related documents
- `REQUIREMENTS - DRL vs LLM Agentic Trading.md` — requirements summary chi tiết
- `Deep Reinforcement Learning Approach for Stock Trading_.pdf` — paper gốc (Xiong et al)
- `Deep Reinforcement Learning for Automated Stock Trading An Ensemble Strategy_.pdf` — paper mở rộng tham khảo
- 3 survey papers 2025 (RL in Finance, Intelligent Investment, Evolution of RL in Quant Finance)

### Key dependencies
- [vnstock](https://github.com/thinh-vu/vnstock) — v4.0.0, dữ liệu chứng khoán VN
- [vnstock_news](https://vnstocks.com/docs/vnstock-news/huong-dan-co-ban) — news crawler
- [stable-baselines3](https://stable-baselines3.readthedocs.io/) — DDPG/PPO
- [LangGraph](https://langchain-ai.github.io/langgraph/) — multi-agent orchestration
- [TradingAgents paper](https://arxiv.org/abs/2412.20138) — Xiao et al, multi-agent design reference

### Locked parameters
| Tham số | Giá trị |
|---|---|
| Tickers | VCB, FPT, HPG, VIC, VNM |
| Train period | 2019-01 → 2024-12 |
| Validation | 2025-01 → 2025-04 |
| Test period | 2025-05 → 2026-04 |
| Initial capital | 1,000,000,000 VND |
| Transaction cost | buy 0.15% / sell 0.25% (gồm thuế bán 0.1%) |
| LLM models | `gpt-4o`, `gpt-4o-mini` |
| Decision frequency | DDPG daily; LLM/agentic weekly |
| Price band | ±7% (HOSE) |
| Lot size | 100 |
