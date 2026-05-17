# DRL vs LLM/Agentic Trading — Vietnam VN30

Thesis project so sánh **DDPG** (Xiong et al, *Deep Reinforcement Learning
Approach for Stock Trading*) với **3 LLM / agentic** approaches trên thị
trường VN30. Deadline **2026-05-31**. Output: research code + full-stack
demo + report.

For project conventions, universal rules, và domain-specific invariants
(no lookahead, ±7% price band, lot-100, asymmetric fees, model lock), see
[`CLAUDE.md`](./CLAUDE.md). For the product spec see
[`.agent/PRD.md`](./.agent/PRD.md); for the 18-package work breakdown see
[`.agent/TASKS.md`](./.agent/TASKS.md).

## Quickstart

```bash
cp .env.example .env             # fill in OPENAI_API_KEY
python -m venv .venv && source .venv/bin/activate
pip install -e .
pytest                           # ~260 tests; all must pass
```

## Data pipeline

```bash
python scripts/fetch_data.py            # VN30 prices + fundamentals (vnstock)
python scripts/fetch_news.py            # VN news (CafeF + VietStock RSS)
python scripts/news_coverage_report.py  # 16/05 checkpoint input
```

Outputs land in `data/raw/` (gitignored) and `data/processed/*.parquet`.

## Train RL agents

```bash
python scripts/train_ddpg.py        # primary (saturates tanh — see PRD §14)
python scripts/train_ppo.py         # backup, used as the headline RL result
```

Models go to `results/models/{ddpg_best.zip, ppo_best.zip}`.

## Backtest

```bash
python scripts/run_baselines.py             # buy_and_hold, equal_weight, random
python scripts/run_rl_backtest.py           # ddpg + ppo
python scripts/run_zero_shot.py             # gpt-4o-mini single shot
python scripts/run_single_agentic.py        # gpt-4o with tool calls
python scripts/run_multi_agent.py           # ~25 min, ~$2.50 (full test split)

python -m src.eval.run_all                  # aggregate → results/metrics_table.csv
python scripts/make_figures.py              # 4 PNG → report/figures/
```

`python -m src.eval.run_all` is the single entry point that regenerates
`metrics_table.csv` from each agent's `results/<agent>/*.parquet`. Same
seed → identical trajectory (PRD §15 reproducibility).

## Demo (full stack)

```bash
# Terminal 1 — backend
uvicorn backend.main:app --reload

# Terminal 2 — frontend
cd frontend && npm install && npm run dev
```

Open <http://localhost:3000>. Four routes:

| Route                  | Purpose                                                   |
| ---------------------- | --------------------------------------------------------- |
| `/`                    | Dashboard: 8 agent cards with cum return + Sharpe         |
| `/agents/[id]`         | Detail: portfolio curve + holdings + metrics table        |
| `/debate`              | Replay: pick a date → 8-role multi_agent transcript       |
| `/live`                | Live: click → multi_agent runs now (~$0.05, ~30-60s)      |

## Offline mode (demo fallback)

Set `OFFLINE_MODE=true` in `.env`. `POST/GET /live/run` then returns a
friendly **HTTP 503** instead of calling OpenAI. `/debate` keeps working
(cached transcripts). Cứu cánh khi demo mất wifi.

## Project layout

Full layout in `.agent/PRD.md §6`. Highlights:

```
src/
  config.py                  # all locked params (PRD §15)
  trading_env.py             # VN rules (±7%, lot-100, fees, no lookahead)
  baselines.py               # buy_and_hold, equal_weight, random
  ddpg_trainer.py, ppo_trainer.py
  agents/__init__.py         # registry (SERIALIZED — merged in PKG-S)
  llm/                       # zero_shot, single_agentic, multi_agent (LangGraph)
  eval/                      # backtest, metrics, run_all

backend/                     # FastAPI + SSE (PKG-11/12)
frontend/                    # Next.js 16 + Tailwind + Recharts (PKG-13..16)
scripts/                     # CLI entry points
tests/                       # pytest, mirrors src/
report/                      # Person 1 writeup + figures/
results/                     # per-agent backtest artifacts (gitignored)
```

## Reproducibility

- All randomness seeded; same seed → same trajectory.
- LLM agents cached by `(date, ticker_set, prompt_hash)`; re-runs reuse
  responses.
- `python -m src.eval.run_all` is bit-deterministic on a second run.

## Secrets

`.env` is gitignored. **Never commit `OPENAI_API_KEY`.** See
[`.env.example`](./.env.example) for the required variables.

## License & scope

Academic thesis use only. Test period 2025-05 → 2026-04 uses public vnstock
data. Out of scope (do not build): real-money trading, intraday/HFT, social
sentiment, UPCOM/HNX small-caps, deep HP search, public deployment.
