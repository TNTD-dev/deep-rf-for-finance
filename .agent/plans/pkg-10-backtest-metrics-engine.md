# Feature: PKG-10 — Backtest engine + metrics

> The aggregation layer. PKG-4 through PKG-9 each shipped their own CLI +
> per-agent `results/{name}/{portfolio_curve, holdings}.parquet`. PKG-10
> centralizes:
>
> 1. **`run_all`** — one command runs all 7 agents end-to-end (deterministic,
>    reuses cached LLM responses where possible)
> 2. **`metrics`** — financial (Sharpe, Sortino, MDD, turnover, total_cost)
>    + LLM-specific (cost USD, latency, parse failure rate, hallucination
>    rate, multi-agent timeouts) computed from artifacts each agent already wrote
> 3. **`results/metrics_table.csv`** — final cross-agent comparison table
>    + `results/{agent}/metrics.json` per-agent payload matching PRD §10
>    `GET /backtest/{agent}` shape, ready for PKG-11 FastAPI to serve
>
> Critically: **PKG-10 does NOT modify any agent code.** It reads parquets +
> JSONL audit logs that PKG-6/7/8/9 already produce. The metrics module is
> pure math on a DataFrame.

## Feature Description

3 new modules + 1 CLI + 1 registry + tests:

1. **`src/eval/metrics.py`** — pure functions taking
   `portfolio_curve: pd.DataFrame` → metric dicts. Each metric is a separate
   function (testable in isolation against golden values).
2. **`src/eval/backtest.py`** — thin wrapper that imports
   `src.baselines.run_backtest` (the existing function from PKG-4) and adds
   metric computation on top. PKG-4's `run_backtest` already produces
   `BacktestResult` with `portfolio_curve` + `holdings_curve` — we don't
   reimplement.
3. **`src/eval/aggregate.py`** — collect per-agent metrics from
   `results/{agent}/metrics.json`, produce `results/metrics_table.csv`.
4. **`src/agents/__init__.py`** — agent registry (`name → factory`). This
   is the file marked SERIALIZED in TASKS.md §"file ownership" — PKG-S
   will merge if conflicts arise. PKG-10 creates the first version.
5. **`scripts/run_all.py`** — single CLI that runs all 7 agents on test
   split, writes per-agent artifacts + final `metrics_table.csv`.

Acceptance criteria (Issue #11):
- `python -m src.eval.run_all` (or `scripts/run_all.py`) runs all agents
- Reproducibility: 2 runs produce identical `metrics.json` (LLM agents
  cache via the file-system path already; for now we accept temp=0
  near-deterministic and document residual drift)
- Person 2 lookahead-safe verification on multi-agent transcripts
- Metrics JSON schema matches `GET /backtest/{agent}` payload in PRD §10

## User Story

As a **report writer (Person 1)**
I want **one CSV table comparing all 7 agents on the same metrics**
So that **I can paste it directly into the report's Results section and
the narrative writes itself ("PPO +40%, multi-agent +X%, ...")**.

As a **PKG-11 FastAPI backend**
I want **`results/{agent}/metrics.json` files matching the PRD §10
response schema**
So that **`GET /backtest/{agent}` is a thin file read + JSON dump, no
business logic in the route**.

As a **Person 2 (verifier)**
I want **a single script that re-runs everything from artifacts on disk**
So that **lookahead-safe audit is a re-run + diff, not a re-implementation
from scratch**.

As a **deadline-bound dev (Duc)**
I want **`run_all` to be incremental — skip an agent whose artifacts are
already on disk and fresh**
So that **iterating on one agent doesn't re-spend $0.30 × N other agents
worth of LLM cost**.

## Problem Statement

5 challenges:

1. **Schema drift across agents.** PKG-4 baselines, PKG-6 zero_shot, PKG-7
   single_agentic, PKG-8 multi_agent, PKG-9 RL all write
   `portfolio_curve.parquet` + `holdings.parquet`. Schemas already aligned
   (`date, agent_name, portfolio_value, cash, w_*` + `date, agent_name, h_*`)
   because they all use `src.baselines._records_to_frames`. But there's no
   ENFORCEMENT — a future agent could break this. PKG-10 must validate
   inputs + fail loud, not silently mis-compute.
2. **LLM-specific metrics live in different places per agent.** Zero-shot:
   `metrics.get_snapshot()` (in-process, lost after backtest unless saved).
   Single-agentic: `tool_calls.jsonl`. Multi-agent: `decisions.jsonl` +
   `transcripts/<date>.json`. PKG-10 needs a unified reader per agent type.
3. **Reproducibility constraint with LLM agents.** Issue #11 says "2 lần
   chạy ra cùng metrics". Real LLM calls are ~98% deterministic at temp=0
   but not bit-exact. Two options: (a) build an LLM response cache in
   PKG-10, (b) accept drift + document. PKG-S was hinted as the proper
   cache home. For PKG-10: accept drift; document in metrics.json a
   `provenance.{timestamp, seed, llm_temp}` block so Person 2 can diff.
4. **Cost of full re-run.** All 7 agents × 248-session test = ~$2-15 LLM
   spend per `run_all`. Need `--skip-existing` flag so dev iteration on one
   agent doesn't re-burn budget.
5. **Multi-agent vs single-agent metric set diverges.** `hallucination_rate`
   only meaningful for single-agentic (tool dispatch errors). `debate_rounds`
   only meaningful for multi-agent. Cleanest: `metrics.json` has a
   superset schema with `null` for inapplicable fields. PKG-11 serializer
   handles `null` → omits from response.

## Solution Statement

10 design decisions LOCK before code:

- **D1.** Pure-function metrics in `src/eval/metrics.py` — each metric
  takes `portfolio_curve: pd.DataFrame` (+ optional inputs) and returns a
  scalar / dict. No I/O. Easy golden-value testing.
- **D2.** **Daily log-return series** is the canonical input.
  `log_returns = np.log(pv_t / pv_{t-1})`. Sharpe/Sortino/MDD all compute
  from this. Matches env reward exactly.
- **D3.** Annualization factor = **252** (VN trading days/year).
  Hardcoded — VN market has ~248 sessions/year actually; 252 is convention
  even though slightly inflated. Document in module docstring.
- **D4.** **Turnover** = sum of |Δweights| over the period / N_periods.
  Computed from `w_*` columns frame-to-frame. Equal-weight does ≥1.0
  monthly; buy-and-hold ≈ 0.04 (initial allocation only).
- **D5.** **`total_cost`** = sum of (buy_fee + sell_fee) × VND traded
  across all periods. Reconstructed from `holdings.parquet` diff × close
  price × fee rate. Approximation: doesn't account for partial fills,
  but env doesn't do partial fills either.
- **D6.** LLM-specific metrics come from THREE readers:
  - `from_in_process_metrics()` — for `metrics.get_snapshot()` style (no
    persistent file; we accept this exists only when the agent is currently
    running). PKG-10 doesn't use this; per-agent CLIs do.
  - `from_audit_jsonl(path)` — reads `results/single_agentic/tool_calls.jsonl`
    OR `results/multi_agent/decisions.jsonl`, computes `llm_cost_usd`,
    `avg_latency_s`, `parse_failure_rate`, `hallucination_rate` (single-agentic
    only), `multi_agent_timeout_rate`.
  - `from_metrics_snapshot_json(path)` — reads a saved snapshot if the agent
    CLI was modified to save one. Optional path — we add it to PKG-10's
    `run_all` so it captures the in-process counters before they're lost.
- **D7.** **Per-agent `metrics.json`** schema matches PRD §10
  `GET /backtest/{agent}` exactly. Top-level keys: `agent`, `portfolio_curve`
  (truncated to ~20 points for JSON size — full series in parquet), `holdings`
  (same truncation), `metrics` (the financial + LLM dict). Single source of
  truth shape so PKG-11 is a file-read.
- **D8.** **`metrics_table.csv`** cross-agent: rows = agents, columns =
  metric names. NaN where inapplicable. Sorted by `cum_return` descending.
- **D9.** **Agent registry in `src/agents/__init__.py`** — pure factories:
  `name → callable(market_data, news_data) → Agent`. Used by `run_all` to
  iterate. SERIALIZED file (PKG-S) — keep minimal.
- **D10.** **`--skip-existing` CLI flag** — checks if `results/{agent}/portfolio_curve.parquet`
  AND `metrics.json` both exist + their mtime > some threshold (e.g. 1
  hour); if so, skips the run and just re-aggregates metrics_table.csv.
  Default off (full re-run); turn on for iteration.

## Feature Metadata

- **Feature Type:** New Capability (the aggregation that turns 6 separate
  agent outputs into a single comparison artifact)
- **Estimated Complexity:** **Medium** — metrics math is well-known but
  the JSONL readers + per-agent reader dispatch is N+1 plumbing; agent
  registry adds first canonical wiring of all agents in one place
- **Primary Systems Affected:**
  - New module: `src/eval/{metrics,backtest,aggregate}.py`
  - New module: `src/agents/__init__.py` (SERIALIZED — coordinate with PKG-S)
  - New CLI: `scripts/run_all.py`
  - New tests: `tests/test_metrics.py`, `tests/test_eval_aggregate.py`,
    `tests/test_agents_registry.py`
- **Dependencies:** Already in `pyproject.toml` — pandas, numpy, pyarrow.
  No new external deps.

---

## CONTEXT REFERENCES

### Relevant Codebase Files — ĐỌC TRƯỚC KHI IMPLEMENT

**The function PKG-10 wraps + extends (PKG-4):**

- `src/baselines.py:97-156` — `run_backtest(env, agent, seed) -> BacktestResult`,
  `_snapshot`, `_records_to_frames`. PKG-10 reuses this verbatim — it's
  battle-tested across baselines + all LLM agents + RL.
- `src/agent_base.py` — `Agent` Protocol + `BacktestResult` dataclass

**Each agent module (READ to understand registry entries):**

- `src/baselines.py` — `BuyAndHold`, `EqualWeightRebalance`, `RandomAgent`
- `src/llm/zero_shot.py:39-131` — `ZeroShotTrader(market_data, news_data, model, ...)`
- `src/llm/single_agentic.py:48-330` — `SingleAgenticTrader(market_data, news_data, model, ...)`
- `src/llm/multi_agent/agent.py:67-220` — `MultiAgentTrader(market_data, news_data, ...)`
- `src/agents/rl_agent.py:14-50` — `RLAgent(model_path)` (different constructor!)

**Existing per-agent CLIs (the patterns PKG-10 must NOT duplicate):**

- `scripts/run_baselines.py` — runs 3 baselines, writes parquets
- `scripts/run_zero_shot.py` — runs zero_shot, writes parquets + metrics print
- `scripts/run_single_agentic.py` — runs single_agentic, writes parquets +
  audit log JSONL
- `scripts/run_multi_agent.py` — runs multi_agent, writes parquets +
  transcripts + decisions.jsonl
- `scripts/run_rl_backtest.py` — loads sb3 model, runs RL, writes parquets

**The LLM metrics module (PKG-5 — reuse READ-only):**

- `src/llm/metrics.py` — `reset()`, `record_llm_call()`,
  `record_parse_failure()`, `get_snapshot()` returns dict with `llm_calls`,
  `by_model`, `total_prompt_tokens`, `total_completion_tokens`,
  `total_cached_tokens`, `estimated_cost_usd`, `parse_success`,
  `parse_failure`, `parse_failure_reasons`, `parse_failure_rate`. In-process
  singleton — PKG-10 reads after each agent's backtest if we add a save call.

**Audit log shapes (READ to know what to parse):**

- `results/single_agentic/tool_calls.jsonl` — one row per LLM iteration +
  one per decision. Iteration rows: `{ts, agent, event:"iteration", date,
  iteration, model, finish_reason, n_tool_calls, tool_calls:[{id,name,args,errored}],
  usage:{prompt_tokens, completion_tokens, cached_tokens}}`. Decision rows:
  `{event:"decision", iterations_used, cap_hit, tool_name_counts, parse_ok, action_sum}`
- `results/multi_agent/decisions.jsonl` — one row per decision: `{ts, date,
  agent, duration_s, debate_rounds, node_errors_count, node_error_roles,
  timed_out, parse_ok, action_sum, cost_delta_usd}`
- `results/multi_agent/transcripts/<date>.json` — full per-decision detail;
  PKG-10 may inspect for Person 2 audit but not for metrics

**Existing parquet schemas (PKG-4 contract; CONFIRMED via shell):**

```
portfolio_curve.parquet: date, agent_name, portfolio_value, cash,
                        w_VCB, w_FPT, w_HPG, w_VIC, w_VNM
holdings.parquet:       date, agent_name, h_VCB, h_FPT, h_HPG, h_VIC, h_VNM
```

**Config (PKG-0):**

- `src/config.py` — `TICKERS`, `INITIAL_CAPITAL`, `BUY_FEE`, `SELL_FEE`,
  `PROJECT_ROOT`. **No new constants needed.**

**Read-only context:**

- `CLAUDE.md` §"Domain-Specific Rules" §5 (Reproducibility — explicitly
  notes LLM cache deferred to PKG-S)
- `CLAUDE.md` §"Patterns" — pure functions in eval/, side effects at edges
- `.agent/PRD.md` §10 (API spec — JSON schema we must match), §11
  (Success Criteria)
- `.agent/TASKS.md:523-560` (PKG-10 spec)
- GitHub Issue #11

**Don't touch (file ownership):**

- All agent modules (`src/baselines.py`, `src/llm/*`, `src/agents/rl_agent.py`)
- `src/trading_env.py`, `src/env_data_loader.py`
- Per-agent existing scripts (`scripts/run_*.py`) — PKG-10 adds a NEW
  unified script `scripts/run_all.py`
- Test fixtures (`tests/conftest.py`)

### New Files to Create

```
src/eval/
├── __init__.py
├── metrics.py                       # pure-function financial + LLM metrics
├── backtest.py                      # wrapper around src.baselines.run_backtest
└── aggregate.py                     # build metrics_table.csv from per-agent JSONs

src/agents/
└── __init__.py                      # registry: name → factory (SERIALIZED with PKG-S)

scripts/
└── run_all.py                       # CLI: run all agents + write metrics + table

tests/
├── test_metrics.py                  # golden-value tests for Sharpe/Sortino/MDD/etc.
├── test_eval_aggregate.py           # JSON shape + CSV aggregation
└── test_agents_registry.py          # registry contract: every entry produces an Agent

results/
├── metrics_table.csv                # cross-agent comparison (output)
└── {agent}/metrics.json             # per-agent payload matching PRD §10
```

### Relevant Documentation — ĐỌC TRƯỚC KHI IMPLEMENT

- **Sharpe / Sortino / MDD formulas** (well-known):
  - Sharpe = mean(returns) / std(returns) × √annualization_factor
  - Sortino = mean(returns) / downside_std × √annualization_factor;
    downside_std = std of negative returns only
  - MDD = max((running_max - pv) / running_max) over time series
- **Turnover** (Frazzini-Pedersen convention):
  turnover = sum |w_t - w_{t-1}| / N
- **PRD §10 response schema** — locked. Re-paste here for convenience:
  ```json
  {"agent": "multi_agent",
   "portfolio_curve": [{"date":"2025-05-02","value":1003200000}, ...],
   "holdings": [{"date":"...","VCB":1200,"FPT":800,...}, ...],
   "metrics": {"cumulative_return": 0.18, "sharpe": 1.42, "max_drawdown": -0.11,
              "turnover": 2.3, "total_cost": 4500000,
              "llm_cost_usd": 12.4, "avg_latency_s": 6.2, "parse_failure_rate": 0.01}}
  ```
- **pandas pivot for holdings JSON shape:** input has `h_VCB, h_FPT, ...`
  columns; output JSON needs `{"VCB": 1200, "FPT": 800, ...}` per date.
  `df.rename(columns=lambda c: c[2:] if c.startswith("h_") else c)` strips prefix.

### Pre-implementation spikes

**Spike A — Compute metrics on existing buy_and_hold output:**

```bash
.venv/bin/python <<'PY'
"""Verify metrics math against a known-good portfolio curve."""
import numpy as np
import pandas as pd

df = pd.read_parquet("results/baselines/buy_and_hold/portfolio_curve.parquet")
pv = df["portfolio_value"].to_numpy()
r = np.log(pv[1:] / pv[:-1])
sharpe = (r.mean() / r.std()) * np.sqrt(252) if r.std() > 0 else 0
mdd = ((np.maximum.accumulate(pv) - pv) / np.maximum.accumulate(pv)).max()
cum = pv[-1] / pv[0] - 1
print(f"buy_and_hold: cum={cum:+.2%}, sharpe={sharpe:.3f}, mdd={mdd:.2%}")
# Expected: cum ~+103% per checkpoint memory
PY
```

Expected: cum_return matches checkpoint memory (~+103%). Locks the
canonical input shape before writing metric functions.

**Spike B — Reconstruct total_cost from holdings diff:**

```bash
.venv/bin/python <<'PY'
"""Verify total_cost reconstruction from holdings parquet."""
import pandas as pd
import numpy as np
from src import config
from src.env_data_loader import load_market_data

h_df = pd.read_parquet("results/baselines/buy_and_hold/holdings.parquet")
h_cols = [f"h_{t}" for t in config.TICKERS]
h = h_df[h_cols].to_numpy(dtype=np.float64)
delta = np.diff(h, axis=0)  # shape (T-1, N)

# Use close on the EXECUTION day (the day after the prior holdings = current row)
md = load_market_data("test")
close = md.close  # (T, N) float32
# Align: holdings row at date t reflects holdings AFTER step at t (env close).
# delta[i] = holdings[i+1] - holdings[i] occurred at session i+1's execution price.
T_h = h.shape[0]
# Match holdings dates to market_data dates
h_dates = pd.to_datetime(h_df["date"]).dt.date.tolist()
md_dates = [d.date() for d in md.dates]
fills = []
for i, d in enumerate(h_dates[1:], start=1):
    if d in md_dates:
        idx = md_dates.index(d)
        fills.append(close[idx])
fills = np.asarray(fills, dtype=np.float64)
buy_cost = np.where(delta > 0, delta, 0) * fills * config.BUY_FEE
sell_cost = np.where(delta < 0, -delta, 0) * fills * config.SELL_FEE
total = float(buy_cost.sum() + sell_cost.sum())
print(f"reconstructed total_cost: {total:,.0f} VND")
# Expected for buy_and_hold: ~0.15% × initial_capital ≈ 1.5M VND
PY
```

Expected: ~$1.5M VND for buy_and_hold (single initial allocation only).
Locks the fee-reconstruction logic.

**Spike C — Parse multi_agent decisions.jsonl, compute aggregates:**

```bash
.venv/bin/python <<'PY'
"""Reduce decisions.jsonl to {n_decisions, avg_duration, total_cost,
timeout_rate, avg_debate_rounds}."""
import json
import statistics
recs = [json.loads(l) for l in open("results/multi_agent/decisions.jsonl")]
print(f"n_decisions: {len(recs)}")
print(f"avg_duration_s: {statistics.mean(r['duration_s'] for r in recs):.2f}")
print(f"total_cost_usd: {sum(r['cost_delta_usd'] for r in recs):.4f}")
print(f"timeout_rate: {sum(r['timed_out'] for r in recs) / len(recs):.1%}")
print(f"avg_debate_rounds: {statistics.mean(r['debate_rounds'] for r in recs):.2f}")
PY
```

Expected: 1 decision (the smoke we ran), ~30s, $0.055, 0% timeout, 2 rounds.

### Patterns to Follow

**Pure-function metric (mirror existing style in `src/llm/metrics.py:43-77`):**

```python
def compute_sharpe(
    portfolio_value: np.ndarray, annualization: int = 252
) -> float:
    """Annualized Sharpe ratio from a portfolio-value series.

    Uses log-returns (matches env reward function — log(pv_t / pv_{t-1})).
    Returns 0.0 if stddev is zero (degenerate flat curve).
    """
    if len(portfolio_value) < 2:
        return 0.0
    r = np.log(portfolio_value[1:] / portfolio_value[:-1])
    s = float(r.std())
    if s < 1e-12:
        return 0.0
    return float(r.mean() / s * np.sqrt(annualization))
```

**Reader for JSONL audit log (mirror `scripts/run_single_agentic.py:_print_audit_summary`):**

```python
def read_audit_jsonl(path: Path) -> list[dict]:
    """Tolerant JSONL reader — skips blank lines + malformed entries."""
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError as e:
            log.warning("skipping bad JSONL line in %s: %s", path, e)
    return out
```

**Per-agent metrics dispatcher:**

```python
LLM_AUDIT_READERS: dict[str, callable] = {
    "zero_shot":       _read_zero_shot_metrics,      # in-process snapshot only
    "single_agentic":  _read_single_agentic_metrics, # tool_calls.jsonl
    "multi_agent":     _read_multi_agent_metrics,    # decisions.jsonl
    # baselines + ddpg + ppo: no LLM metrics; reader returns empty dict
}

def llm_metrics_for(agent_name: str, results_dir: Path) -> dict:
    reader = LLM_AUDIT_READERS.get(agent_name)
    if reader is None:
        return {}
    return reader(results_dir / agent_name)
```

**Agent registry (`src/agents/__init__.py` — SERIALIZED, keep minimal):**

```python
"""Agent registry — name → factory function.

SERIALIZED FILE (TASKS.md §"file ownership"): owned by PKG-10 + PKG-S.
Keep entries alphabetical to minimize merge conflicts.
"""
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pandas as pd

from src.agent_base import Agent
from src.baselines import BuyAndHold, EqualWeightRebalance, RandomAgent
from src.env_data_loader import MarketData
from src.llm.multi_agent.agent import MultiAgentTrader
from src.llm.single_agentic import SingleAgenticTrader
from src.llm.zero_shot import ZeroShotTrader

# RL agents need a model path, not a fresh agent class. We provide
# closure factories that load from default paths; CLI can override.
def _rl_factory(model_path: Path, name: str):
    def make(market_data: MarketData, news_data: pd.DataFrame,
             env=None, **kwargs: Any) -> Agent:
        from src.agents.rl_agent import RLAgent
        return RLAgent(model_path, name=name)
    return make

def _random_factory(market_data, news_data, env, **kw) -> Agent:
    return RandomAgent(env)

AgentFactory = Callable[..., Agent]

DEFAULT_RL_MODEL_DIR = Path("results/models")

AGENT_REGISTRY: dict[str, AgentFactory] = {
    "buy_and_hold":   lambda md, news, env=None, **kw: BuyAndHold(),
    "equal_weight":   lambda md, news, env=None, **kw: EqualWeightRebalance(),
    "random":         _random_factory,
    "zero_shot":      lambda md, news, env=None, **kw: ZeroShotTrader(md, news),
    "single_agentic": lambda md, news, env=None, **kw: SingleAgenticTrader(md, news),
    "multi_agent":    lambda md, news, env=None, **kw: MultiAgentTrader(md, news),
    "ddpg":           _rl_factory(DEFAULT_RL_MODEL_DIR / "ddpg_best.zip", "ddpg"),
    "ppo":            _rl_factory(DEFAULT_RL_MODEL_DIR / "ppo_best.zip", "ppo"),
}
```

**Error handling (CLAUDE.md alignment):**

- Missing audit log → empty LLM metrics dict (NOT a crash); log INFO
- Bad JSONL line → skip + log WARNING; never crash aggregation
- Missing parquet for an agent → SKIP that agent in `metrics_table.csv`;
  log WARNING; never crash other agents
- Missing trained model for RL agent → SKIP `ddpg`/`ppo` with WARNING;
  run rest of the suite
- Metric computation on degenerate series (flat / all-NaN) → return 0.0;
  document in docstring

---

## DESIGN DECISIONS — LOCK BEFORE IMPLEMENT

### D1. Pure-function metrics in `src/eval/metrics.py`

Each metric = standalone function. No class. Easy to golden-test.
Aggregator (`compute_all_metrics`) calls each in sequence.

### D2. Daily log-returns canonical input

`np.log(pv[1:] / pv[:-1])` — matches env reward. Avoids divide-by-zero on
flat segments (log of 1 = 0, std propagates correctly).

### D3. Annualization factor = 252

```python
ANNUALIZATION_DAYS: int = 252
```

Standard in equity research. VN actually has ~248 sessions/year but
convention wins. Document in module docstring.

### D4. Turnover = sum |Δw| / N

```python
def compute_turnover(weights: pd.DataFrame) -> float:
    w = weights[[f"w_{t}" for t in config.TICKERS]].to_numpy()
    delta = np.abs(np.diff(w, axis=0)).sum(axis=1)
    return float(delta.mean())
```

Per-period (daily) average. Higher = more churning. Equal-weight ≈ 0.05
when monthly rebalance; PKG-7 single-agentic ≈ similar; multi-agent depends
on portfolio_manager output.

### D5. `total_cost` reconstructed from holdings diff × price × fee

```python
def compute_total_cost(
    holdings_df: pd.DataFrame, market_data: MarketData
) -> float:
    """Sum of (buy_fee × buy_VND + sell_fee × sell_VND) across all periods.

    Uses execution-day close prices to value each trade. Approximation:
    doesn't account for env's ±7% band clamp or affordability fallback;
    those affect FILL price, not the SIZE of the trade. Typically <1%
    discrepancy vs env's accumulated fees.
    """
    h_cols = [f"h_{t}" for t in config.TICKERS]
    h = holdings_df[h_cols].to_numpy(dtype=np.float64)
    delta = np.diff(h, axis=0)
    # Align dates: holdings row at date d reflects post-execution. Trade
    # for row i+1 happens at md_close[md_date_idx(holdings_df.date[i+1])].
    md_dates = [d.date() for d in market_data.dates]
    h_dates = pd.to_datetime(holdings_df["date"]).dt.date.tolist()
    fills_list = []
    for i, d in enumerate(h_dates[1:], start=1):
        if d in md_dates:
            fills_list.append(market_data.close[md_dates.index(d)])
        else:
            fills_list.append(np.zeros(len(config.TICKERS), dtype=np.float32))
    fills = np.asarray(fills_list, dtype=np.float64)
    buy_cost = np.where(delta > 0, delta, 0) * fills * config.BUY_FEE
    sell_cost = np.where(delta < 0, -delta, 0) * fills * config.SELL_FEE
    return float(buy_cost.sum() + sell_cost.sum())
```

### D6. Three LLM-metric readers (per-agent dispatch)

```python
def _read_zero_shot_metrics(agent_dir: Path) -> dict:
    """Zero-shot has no per-decision audit log (only in-process metrics).
    Reads metrics_snapshot.json if PKG-10 saved one during run_all."""
    snapshot = agent_dir / "metrics_snapshot.json"
    if not snapshot.exists():
        return {}
    snap = json.loads(snapshot.read_text())
    return {
        "llm_cost_usd": float(snap.get("estimated_cost_usd", 0.0)),
        "llm_calls": int(snap.get("llm_calls", 0)),
        "parse_failure_rate": float(snap.get("parse_failure_rate", 0.0)),
        "cached_tokens": int(snap.get("total_cached_tokens", 0)),
    }


def _read_single_agentic_metrics(agent_dir: Path) -> dict:
    """Reads tool_calls.jsonl. Computes hallucination_rate from errored
    tool calls; LLM cost from per-iteration usage."""
    log_path = agent_dir / "tool_calls.jsonl"
    rows = read_audit_jsonl(log_path)
    iters = [r for r in rows if r.get("event") == "iteration"]
    decisions = [r for r in rows if r.get("event") == "decision"]
    all_tcs = [tc for r in iters for tc in r.get("tool_calls", [])]
    errored = sum(1 for tc in all_tcs if tc.get("errored"))
    # Cost computation: use the in-process metrics snapshot if available
    snap = json.loads((agent_dir / "metrics_snapshot.json").read_text()) \
        if (agent_dir / "metrics_snapshot.json").exists() else {}
    return {
        "llm_cost_usd": float(snap.get("estimated_cost_usd", 0.0)),
        "llm_calls": sum(r.get("n_tool_calls", 0) for r in iters) + len(iters),
        "avg_iterations_per_decision": (
            sum(r["iterations_used"] for r in decisions) / max(len(decisions), 1)
            if decisions else 0.0
        ),
        "hallucination_rate": errored / max(len(all_tcs), 1),
        "parse_failure_rate": float(snap.get("parse_failure_rate", 0.0)),
        "cap_hit_rate": (
            sum(1 for d in decisions if d.get("cap_hit"))
            / max(len(decisions), 1)
        ),
    }


def _read_multi_agent_metrics(agent_dir: Path) -> dict:
    """Reads decisions.jsonl. Uses cost_delta_usd already accumulated per
    decision."""
    log_path = agent_dir / "decisions.jsonl"
    rows = read_audit_jsonl(log_path)
    if not rows:
        return {}
    n = len(rows)
    return {
        "llm_cost_usd": float(sum(r.get("cost_delta_usd", 0.0) for r in rows)),
        "avg_latency_s": float(sum(r["duration_s"] for r in rows) / n),
        "max_latency_s": float(max(r["duration_s"] for r in rows)),
        "timeout_rate": float(sum(r.get("timed_out", False) for r in rows) / n),
        "node_errors_total": int(sum(r.get("node_errors_count", 0) for r in rows)),
        "avg_debate_rounds": float(sum(r.get("debate_rounds", 0) for r in rows) / n),
        "parse_failure_rate": float(sum(1 for r in rows if not r.get("parse_ok", True)) / n),
        "n_decisions": n,
    }
```

### D7. Per-agent `metrics.json` matches PRD §10

```python
def build_per_agent_payload(
    agent_name: str,
    portfolio_curve: pd.DataFrame,
    holdings_df: pd.DataFrame,
    metrics: dict,
    sample_n: int = 250,  # full year ~248 sessions, keep all
) -> dict:
    """Build the PRD §10 GET /backtest/{agent} response payload."""
    pc = portfolio_curve.copy()
    pc["date"] = pd.to_datetime(pc["date"]).dt.strftime("%Y-%m-%d")
    portfolio_curve_list = [
        {"date": r["date"], "value": int(r["portfolio_value"])}
        for _, r in pc.iterrows()
    ]
    h = holdings_df.copy()
    h["date"] = pd.to_datetime(h["date"]).dt.strftime("%Y-%m-%d")
    holdings_list = []
    for _, r in h.iterrows():
        item = {"date": r["date"]}
        for t in config.TICKERS:
            item[t] = int(r[f"h_{t}"])
        holdings_list.append(item)
    return {
        "agent": agent_name,
        "portfolio_curve": portfolio_curve_list,
        "holdings": holdings_list,
        "metrics": metrics,
        "provenance": {
            "ts": now_iso(),
            "seed": 42,
            "test_window": ["2025-05-05", "2026-04-30"],
        },
    }
```

`portfolio_curve` and `holdings` lists are unbounded (~248 entries) —
acceptable JSON size (~50KB/agent). If PKG-11 needs smaller for SSE
warm-load, add downsampling later.

### D8. `metrics_table.csv` aggregator

```python
def build_metrics_table(results_dir: Path) -> pd.DataFrame:
    rows = []
    for agent_dir in sorted(results_dir.iterdir()):
        if not agent_dir.is_dir():
            continue
        metrics_json = agent_dir / "metrics.json"
        if not metrics_json.exists():
            continue
        payload = json.loads(metrics_json.read_text())
        row = {"agent": payload["agent"]}
        row.update(payload["metrics"])
        rows.append(row)
    df = pd.DataFrame(rows)
    if "cumulative_return" in df.columns:
        df = df.sort_values("cumulative_return", ascending=False)
    return df
```

Output: rows × ~12 cols, NaN where inapplicable. Person 1 reads CSV directly.

### D9. Agent registry in `src/agents/__init__.py`

SERIALIZED file. PKG-10 ships first version with all 8 agents (7 + random).
PKG-S may add `name → display_name`, `is_baseline` flags later. Keep
registry minimal to avoid merge conflicts.

### D10. `--skip-existing` CLI flag

```python
parser.add_argument(
    "--skip-existing", action="store_true",
    help="Skip agents whose results/{agent}/metrics.json exists",
)
parser.add_argument(
    "--agents", nargs="+", default=None,
    help="Only run these agents (default: all in registry)",
)
```

Combined with `--agents foo bar baz` for surgical re-runs.

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation — metrics module + golden tests

- `src/eval/__init__.py`
- `src/eval/metrics.py` — financial metrics (pure functions)
- `tests/test_metrics.py` — golden values for Sharpe/Sortino/MDD/turnover/total_cost

### Phase 2: LLM-metric readers + aggregate

- `src/eval/aggregate.py` — LLM readers + `metrics_table.csv` builder
- `tests/test_eval_aggregate.py` — JSONL parsing, missing-file tolerance

### Phase 3: Registry + backtest wrapper

- `src/agents/__init__.py` — registry (SERIALIZED — see D9)
- `src/eval/backtest.py` — wrapper combining `run_backtest` + metrics + payload
- `tests/test_agents_registry.py` — every entry returns Agent Protocol

### Phase 4: CLI + run real backtest

- `scripts/run_all.py` — orchestrator
- Run on test split with `--skip-existing` (uses cached agent results from PKG-4/6/7/8/9 + just re-aggregates)
- Verify `metrics_table.csv` looks sane

### Phase 5: Person 2 lookahead audit hook

- `scripts/audit_lookahead.py` — small CLI: reads multi_agent transcripts, scans for "FUTURE" / out-of-window dates
- Optional — out-of-scope if time pressed

---

## STEP-BY-STEP TASKS

### 1. RUN Spike A + B + C

- **VALIDATE:** All 3 print expected numbers.

### 2. CREATE `src/eval/__init__.py`

- **IMPLEMENT:** Empty file (or exports later).

### 3. CREATE `src/eval/metrics.py`

- **IMPLEMENT:**
  ```python
  """Financial + LLM-specific metrics (PKG-10).

  Pure functions taking pd.DataFrame / np.ndarray → scalar / dict.
  Reproducible (no clock, no random). Golden-value tested.

  Annualization = 252 (equity convention; VN has ~248 trading sessions/year
  but 252 is the cross-market standard).
  """
  from __future__ import annotations
  import math
  import numpy as np
  import pandas as pd

  from src import config

  ANNUALIZATION_DAYS: int = 252

  def log_returns(portfolio_value: np.ndarray) -> np.ndarray:
      pv = np.asarray(portfolio_value, dtype=np.float64)
      if len(pv) < 2:
          return np.array([], dtype=np.float64)
      pv = np.maximum(pv, 1e-12)
      return np.log(pv[1:] / pv[:-1])

  def compute_cumulative_return(portfolio_value: np.ndarray) -> float:
      pv = np.asarray(portfolio_value, dtype=np.float64)
      if len(pv) < 2 or pv[0] <= 0:
          return 0.0
      return float(pv[-1] / pv[0] - 1.0)

  def compute_sharpe(
      portfolio_value: np.ndarray, annualization: int = ANNUALIZATION_DAYS
  ) -> float:
      r = log_returns(portfolio_value)
      if r.size == 0 or r.std() < 1e-12:
          return 0.0
      return float(r.mean() / r.std() * math.sqrt(annualization))

  def compute_sortino(
      portfolio_value: np.ndarray, annualization: int = ANNUALIZATION_DAYS
  ) -> float:
      r = log_returns(portfolio_value)
      neg = r[r < 0]
      if r.size == 0 or neg.size == 0 or neg.std() < 1e-12:
          return 0.0
      return float(r.mean() / neg.std() * math.sqrt(annualization))

  def compute_max_drawdown(portfolio_value: np.ndarray) -> float:
      pv = np.asarray(portfolio_value, dtype=np.float64)
      if pv.size == 0:
          return 0.0
      running_max = np.maximum.accumulate(pv)
      dd = (running_max - pv) / np.maximum(running_max, 1e-12)
      return float(dd.max())

  def compute_turnover(portfolio_curve: pd.DataFrame) -> float:
      w_cols = [f"w_{t}" for t in config.TICKERS]
      if not all(c in portfolio_curve.columns for c in w_cols):
          return 0.0
      w = portfolio_curve[w_cols].to_numpy(dtype=np.float64)
      if w.shape[0] < 2:
          return 0.0
      delta = np.abs(np.diff(w, axis=0)).sum(axis=1)
      return float(delta.mean())

  def compute_total_cost(
      holdings_df: pd.DataFrame, market_data
  ) -> float:
      h_cols = [f"h_{t}" for t in config.TICKERS]
      if not all(c in holdings_df.columns for c in h_cols):
          return 0.0
      h = holdings_df[h_cols].to_numpy(dtype=np.float64)
      if h.shape[0] < 2:
          return 0.0
      delta = np.diff(h, axis=0)
      md_dates = [d.date() for d in market_data.dates]
      h_dates = pd.to_datetime(holdings_df["date"]).dt.date.tolist()
      n_tickers = len(config.TICKERS)
      fills_list = []
      for d in h_dates[1:]:
          if d in md_dates:
              fills_list.append(market_data.close[md_dates.index(d)])
          else:
              fills_list.append(np.zeros(n_tickers, dtype=np.float32))
      fills = np.asarray(fills_list, dtype=np.float64)
      buy = np.where(delta > 0, delta, 0) * fills * float(config.BUY_FEE)
      sell = np.where(delta < 0, -delta, 0) * fills * float(config.SELL_FEE)
      return float(buy.sum() + sell.sum())

  def compute_all_financial_metrics(
      portfolio_curve: pd.DataFrame,
      holdings_df: pd.DataFrame,
      market_data,
  ) -> dict[str, float]:
      pv = portfolio_curve["portfolio_value"].to_numpy()
      return {
          "cumulative_return": compute_cumulative_return(pv),
          "sharpe": compute_sharpe(pv),
          "sortino": compute_sortino(pv),
          "max_drawdown": compute_max_drawdown(pv),
          "turnover": compute_turnover(portfolio_curve),
          "total_cost": compute_total_cost(holdings_df, market_data),
          "n_steps": int(len(portfolio_curve) - 1),
      }
  ```
- **GOTCHA #1:** Sharpe of degenerate (flat) curve = 0.0, not NaN.
  Important for baselines where some sub-windows are flat.
- **GOTCHA #2:** `holdings_df.date` may be Timestamp objects from parquet
  — use `pd.to_datetime(...).dt.date` to compare against `md.dates[i].date()`.
- **VALIDATE:** `.venv/bin/python -c "from src.eval.metrics import compute_sharpe; import numpy as np; print(compute_sharpe(np.array([1, 1.01, 1.02, 1.03])))"` — should print a positive Sharpe.

### 4. CREATE `tests/test_metrics.py` (~10 tests)

- **IMPLEMENT:** Golden-value tests using hand-computed expected values.
  1. `test_log_returns_handles_short_series` — len < 2 → empty array
  2. `test_cumulative_return_basic` — [1, 1.1, 1.21] → 0.21
  3. `test_sharpe_positive_for_uptrend` — synthetic 0.1%/day uptrend
  4. `test_sharpe_zero_for_flat_series` — constant pv → 0.0
  5. `test_sortino_only_penalizes_downside` — different from Sharpe on
     mixed series
  6. `test_max_drawdown_basic` — [1, 1.5, 0.5, 1.2] → 1.0 (50% drawdown)
  7. `test_max_drawdown_zero_for_monotonic_uptrend`
  8. `test_turnover_zero_for_buy_and_hold_after_init` — w_t = w_{t-1}
  9. `test_turnover_positive_for_rebalance_pattern` — monthly flip
  10. `test_total_cost_buy_only_uses_buy_fee` — synthetic delta with
      only buys
- **PATTERN:** Pure pytest, no fixtures beyond `synthetic_market_data` for
  `compute_total_cost` test.
- **VALIDATE:** `.venv/bin/pytest tests/test_metrics.py -v`

### 5. CREATE `src/eval/aggregate.py`

- **IMPLEMENT:**
  ```python
  """LLM-specific metric readers + metrics_table.csv aggregator (PKG-10).

  Reads per-agent audit artifacts (tool_calls.jsonl, decisions.jsonl,
  metrics_snapshot.json) and computes LLM cost / latency / failure metrics.
  Tolerant of missing files — non-LLM agents return empty dict.
  """
  from __future__ import annotations
  import json
  import logging
  from pathlib import Path

  import pandas as pd

  log = logging.getLogger(__name__)


  def read_audit_jsonl(path: Path) -> list[dict]:
      if not path.exists():
          return []
      out: list[dict] = []
      for line in path.read_text(encoding="utf-8").splitlines():
          line = line.strip()
          if not line:
              continue
          try:
              out.append(json.loads(line))
          except json.JSONDecodeError as e:
              log.warning("skip bad jsonl line in %s: %s", path, e)
      return out

  def _read_snapshot(agent_dir: Path) -> dict:
      p = agent_dir / "metrics_snapshot.json"
      if not p.exists():
          return {}
      try:
          return json.loads(p.read_text(encoding="utf-8"))
      except (OSError, json.JSONDecodeError) as e:
          log.warning("snapshot read failed: %s", e)
          return {}

  def _read_zero_shot_metrics(agent_dir: Path) -> dict:
      snap = _read_snapshot(agent_dir)
      if not snap:
          return {}
      return {
          "llm_cost_usd": float(snap.get("estimated_cost_usd", 0.0)),
          "llm_calls": int(snap.get("llm_calls", 0)),
          "parse_failure_rate": float(snap.get("parse_failure_rate", 0.0)),
          "cached_tokens": int(snap.get("total_cached_tokens", 0)),
      }

  def _read_single_agentic_metrics(agent_dir: Path) -> dict:
      rows = read_audit_jsonl(agent_dir / "tool_calls.jsonl")
      iters = [r for r in rows if r.get("event") == "iteration"]
      decisions = [r for r in rows if r.get("event") == "decision"]
      all_tcs = [tc for r in iters for tc in r.get("tool_calls", [])]
      errored = sum(1 for tc in all_tcs if tc.get("errored"))
      snap = _read_snapshot(agent_dir)
      out: dict = {}
      if snap:
          out["llm_cost_usd"] = float(snap.get("estimated_cost_usd", 0.0))
          out["llm_calls"] = int(snap.get("llm_calls", 0))
          out["parse_failure_rate"] = float(snap.get("parse_failure_rate", 0.0))
      out["avg_iterations_per_decision"] = (
          sum(d["iterations_used"] for d in decisions) / max(len(decisions), 1)
          if decisions else 0.0
      )
      out["hallucination_rate"] = errored / max(len(all_tcs), 1)
      out["cap_hit_rate"] = (
          sum(1 for d in decisions if d.get("cap_hit")) / max(len(decisions), 1)
          if decisions else 0.0
      )
      out["n_decisions"] = len(decisions)
      return out

  def _read_multi_agent_metrics(agent_dir: Path) -> dict:
      rows = read_audit_jsonl(agent_dir / "decisions.jsonl")
      if not rows:
          return {}
      n = len(rows)
      return {
          "llm_cost_usd": float(sum(r.get("cost_delta_usd", 0.0) for r in rows)),
          "avg_latency_s": float(sum(r["duration_s"] for r in rows) / n),
          "max_latency_s": float(max(r["duration_s"] for r in rows)),
          "timeout_rate": float(sum(r.get("timed_out", False) for r in rows) / n),
          "node_errors_total": int(sum(r.get("node_errors_count", 0) for r in rows)),
          "avg_debate_rounds": float(sum(r.get("debate_rounds", 0) for r in rows) / n),
          "parse_failure_rate": float(sum(1 for r in rows if not r.get("parse_ok", True)) / n),
          "n_decisions": n,
      }

  LLM_AUDIT_READERS = {
      "zero_shot":       _read_zero_shot_metrics,
      "single_agentic":  _read_single_agentic_metrics,
      "multi_agent":     _read_multi_agent_metrics,
  }

  def read_llm_metrics(agent_name: str, agent_dir: Path) -> dict:
      reader = LLM_AUDIT_READERS.get(agent_name)
      return reader(agent_dir) if reader is not None else {}


  def build_metrics_table(results_dir: Path) -> pd.DataFrame:
      rows = []
      for agent_dir in sorted(results_dir.iterdir()):
          if not agent_dir.is_dir():
              continue
          # Skip nested baseline dir; baselines live under results/baselines/*
          metrics_json = agent_dir / "metrics.json"
          if metrics_json.exists():
              payload = json.loads(metrics_json.read_text())
              row = {"agent": payload["agent"]}
              row.update(payload.get("metrics", {}))
              rows.append(row)
          else:
              # Recurse one level (e.g. results/baselines/buy_and_hold/metrics.json)
              for sub in sorted(agent_dir.iterdir()):
                  if sub.is_dir() and (sub / "metrics.json").exists():
                      payload = json.loads((sub / "metrics.json").read_text())
                      row = {"agent": payload["agent"]}
                      row.update(payload.get("metrics", {}))
                      rows.append(row)
      df = pd.DataFrame(rows)
      if "cumulative_return" in df.columns and not df.empty:
          df = df.sort_values("cumulative_return", ascending=False)
      return df
  ```
- **GOTCHA:** Existing `results/baselines/{buy_and_hold,equal_weight,random}/`
  has 1 level of nesting that other agents don't. The `build_metrics_table`
  walker handles both flat and nested.
- **VALIDATE:** Module imports + `read_audit_jsonl` works on existing
  `results/multi_agent/decisions.jsonl`

### 6. CREATE `src/eval/backtest.py`

- **IMPLEMENT:**
  ```python
  """Backtest + metrics + payload — wraps PKG-4 run_backtest with PKG-10
  metric computation and PRD §10 payload assembly."""
  from __future__ import annotations
  import json
  from datetime import UTC, datetime
  from pathlib import Path

  import pandas as pd

  from src import config
  from src.agent_base import Agent, BacktestResult
  from src.baselines import run_backtest
  from src.env_data_loader import MarketData
  from src.eval.aggregate import read_llm_metrics
  from src.eval.metrics import compute_all_financial_metrics
  from src.trading_env import VNTradingEnv


  def run_and_score(
      agent: Agent,
      market_data: MarketData,
      env: VNTradingEnv | None = None,
      seed: int = 42,
  ) -> tuple[BacktestResult, dict]:
      """Run backtest + compute financial metrics. Returns (result, metrics)."""
      env = env or VNTradingEnv(market_data)
      result = run_backtest(env, agent, seed=seed)
      metrics = compute_all_financial_metrics(
          result.portfolio_curve, result.holdings_curve, market_data
      )
      return result, metrics


  def build_payload(
      result: BacktestResult,
      metrics: dict,
      llm_metrics: dict | None = None,
      test_window: tuple[str, str] | None = None,
      seed: int = 42,
  ) -> dict:
      """Build PRD §10 GET /backtest/{agent} payload."""
      full_metrics = dict(metrics)
      if llm_metrics:
          full_metrics.update(llm_metrics)
      pc = result.portfolio_curve.copy()
      pc["date"] = pd.to_datetime(pc["date"]).dt.strftime("%Y-%m-%d")
      portfolio_curve = [
          {"date": r["date"], "value": int(r["portfolio_value"])}
          for _, r in pc.iterrows()
      ]
      h = result.holdings_curve.copy()
      h["date"] = pd.to_datetime(h["date"]).dt.strftime("%Y-%m-%d")
      holdings = []
      for _, r in h.iterrows():
          item = {"date": r["date"]}
          for t in config.TICKERS:
              item[t] = int(r[f"h_{t}"])
          holdings.append(item)
      return {
          "agent": result.agent_name,
          "portfolio_curve": portfolio_curve,
          "holdings": holdings,
          "metrics": full_metrics,
          "provenance": {
              "ts": datetime.now(UTC).isoformat(),
              "seed": int(seed),
              "test_window": list(test_window) if test_window else None,
              "n_steps": int(result.n_steps),
          },
      }


  def save_artifacts(
      payload: dict,
      result: BacktestResult,
      results_root: Path,
  ) -> Path:
      """Write parquets + metrics.json to results/{agent}/."""
      agent_dir = results_root / payload["agent"]
      agent_dir.mkdir(parents=True, exist_ok=True)
      result.portfolio_curve.to_parquet(
          agent_dir / "portfolio_curve.parquet",
          engine="pyarrow", compression="snappy",
      )
      result.holdings_curve.to_parquet(
          agent_dir / "holdings.parquet",
          engine="pyarrow", compression="snappy",
      )
      (agent_dir / "metrics.json").write_text(
          json.dumps(payload, ensure_ascii=False, indent=2, default=str),
          encoding="utf-8",
      )
      return agent_dir
  ```

### 7. CREATE `src/agents/__init__.py` (SERIALIZED — minimal)

- **IMPLEMENT:** As shown in D9 patterns above. Keep alphabetical to
  minimize merge conflicts with PKG-S.
- **GOTCHA:** RL factories capture `model_path` via closure — be careful
  not to share mutable state across calls. Each call returns a NEW `RLAgent`.

### 8. CREATE `tests/test_agents_registry.py` (~3 tests)

- **IMPLEMENT:**
  1. `test_registry_has_all_8_agents` — keys = expected set
  2. `test_every_factory_produces_agent_protocol` — for non-RL entries,
     construct + isinstance check (RL skipped if no model file)
  3. `test_factory_signatures_accept_md_news_env` — call signature uniform
- **GOTCHA:** RL factory needs `results/models/{ddpg,ppo}_best.zip` to test —
  skip those if missing (use `pytest.mark.skipif`).

### 9. CREATE `tests/test_eval_aggregate.py` (~5 tests)

- **IMPLEMENT:**
  1. `test_read_audit_jsonl_handles_missing_file` — empty list, no exception
  2. `test_read_audit_jsonl_skips_bad_lines` — write a file with one good +
     one bad line, expect [good]
  3. `test_multi_agent_reader_aggregates_decisions` — write 2 fake
     decisions, verify n_decisions=2 + avg_latency_s correct
  4. `test_single_agentic_reader_computes_hallucination_rate` — write
     iteration row with 3 tool_calls (1 errored) → rate = 1/3
  5. `test_build_metrics_table_handles_nested_baselines_dir` — tmp_path
     with `agent1/metrics.json` + `baselines/agent2/metrics.json`; verify
     both rows appear

### 10. CREATE `scripts/run_all.py`

- **IMPLEMENT:**
  ```python
  """CLI: run all agents on a split, save artifacts, build metrics_table.csv.

  Usage:
      .venv/bin/python scripts/run_all.py                          # all agents
      .venv/bin/python scripts/run_all.py --agents zero_shot ddpg  # subset
      .venv/bin/python scripts/run_all.py --skip-existing          # only missing
  """
  from __future__ import annotations
  import argparse
  import json
  import logging
  import sys
  from pathlib import Path

  import pandas as pd

  from src import config
  from src.agents import AGENT_REGISTRY
  from src.env_data_loader import load_market_data
  from src.eval.aggregate import build_metrics_table, read_llm_metrics
  from src.eval.backtest import build_payload, run_and_score, save_artifacts
  from src.llm import metrics as llm_metrics_mod
  from src.trading_env import VNTradingEnv

  RESULTS_DIR = config.PROJECT_ROOT / "results"
  NEWS_PATH = config.PROJECT_ROOT / "data" / "processed" / "news.parquet"
  TEST_WINDOW = (
      str(config.TEST_START)[:10], str(config.TEST_END)[:10]
  )


  def _has_results(agent_name: str) -> bool:
      agent_dir = RESULTS_DIR / agent_name
      return (
          (agent_dir / "metrics.json").exists()
          and (agent_dir / "portfolio_curve.parquet").exists()
      )


  def main() -> int:
      logging.basicConfig(
          level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
      )
      p = argparse.ArgumentParser()
      p.add_argument("--split", default="test", choices=["train", "val", "test"])
      p.add_argument("--seed", type=int, default=42)
      p.add_argument(
          "--agents", nargs="+", default=None,
          help=f"Subset to run; default ALL: {list(AGENT_REGISTRY)}",
      )
      p.add_argument(
          "--skip-existing", action="store_true",
          help="Skip agents whose metrics.json + parquet already exist",
      )
      args = p.parse_args()

      md = load_market_data(args.split)
      news = pd.read_parquet(NEWS_PATH) if NEWS_PATH.exists() else pd.DataFrame()
      print(f"split={args.split}  sessions={len(md.dates)}  news_rows={len(news)}")

      agents_to_run = args.agents or list(AGENT_REGISTRY.keys())
      for name in agents_to_run:
          if name not in AGENT_REGISTRY:
              print(f"WARN: unknown agent {name!r}; skip")
              continue
          if args.skip_existing and _has_results(name):
              print(f"  skip {name} (results exist)")
              continue
          print(f"\n=== {name} ===")
          factory = AGENT_REGISTRY[name]
          env = VNTradingEnv(md)
          try:
              agent = factory(md, news, env=env)
          except FileNotFoundError as e:
              print(f"  WARN: cannot construct {name}: {e}")
              continue
          # Reset LLM metrics so we capture per-agent cost
          llm_metrics_mod.reset()
          result, fin_metrics = run_and_score(
              agent, market_data=md, env=env, seed=args.seed
          )
          # Save in-process LLM metrics snapshot for this agent
          agent_dir = RESULTS_DIR / name
          agent_dir.mkdir(parents=True, exist_ok=True)
          snap = llm_metrics_mod.get_snapshot()
          (agent_dir / "metrics_snapshot.json").write_text(
              json.dumps(snap, default=str, indent=2), encoding="utf-8"
          )
          llm_extra = read_llm_metrics(name, agent_dir)
          payload = build_payload(
              result, fin_metrics, llm_metrics=llm_extra,
              test_window=TEST_WINDOW, seed=args.seed,
          )
          save_artifacts(payload, result, RESULTS_DIR)
          cum = fin_metrics.get("cumulative_return", 0.0)
          print(f"  cum_return={cum:+.2%}  sharpe={fin_metrics.get('sharpe', 0):.2f}  steps={result.n_steps}")

      # Build cross-agent table
      table = build_metrics_table(RESULTS_DIR)
      table_path = RESULTS_DIR / "metrics_table.csv"
      table.to_csv(table_path, index=False)
      print(f"\n=== Aggregated metrics_table.csv ===\nrows: {len(table)}\nsaved: {table_path}")
      if not table.empty:
          print(table.to_string(index=False))
      return 0


  if __name__ == "__main__":
      sys.exit(main())
  ```
- **GOTCHA #1:** `llm_metrics_mod.reset()` BEFORE each agent — otherwise
  costs accumulate across agents and you can't distinguish them.
- **GOTCHA #2:** `--skip-existing` short-circuits training, but we STILL
  need to call `build_metrics_table` at the end so the CSV reflects all
  agents. Done unconditionally in the final block.
- **GOTCHA #3:** RL agents require trained models. If `results/models/ddpg_best.zip`
  missing, factory raises `FileNotFoundError` — caught in the loop, print
  WARN, continue.

### 11. RUN `run_all` with `--skip-existing` (uses cached results)

- **IMPLEMENT:**
  ```bash
  .venv/bin/python scripts/run_all.py --skip-existing
  ```
- **EXPECTED:** Skips agents with existing parquets, computes metrics on
  cached data, writes `metrics_table.csv`. Should complete in < 30s with
  no LLM cost (re-uses existing artifacts).

### 12. RUN `run_all` on a single missing agent (smoke real spend)

- **IMPLEMENT:**
  ```bash
  .venv/bin/python scripts/run_all.py --agents zero_shot --split test
  ```
  Only if zero_shot needs re-run; otherwise pick another.
- **EXPECTED:** Completes with real LLM spend; metrics.json appears in
  `results/zero_shot/`.

### 13. Final ruff + pytest

```bash
.venv/bin/ruff check src/ tests/ scripts/
.venv/bin/pytest tests/ -v 2>&1 | tail -5
# Expected: ruff clean, ~208 tests pass (190 + ~18 new)
```

---

## TESTING STRATEGY

### Unit Tests (~18 new across 3 files)

| File | Count | Focus |
|------|------:|-------|
| `test_metrics.py` | 10 | Sharpe/Sortino/MDD/turnover/total_cost golden values |
| `test_eval_aggregate.py` | 5 | JSONL reader, LLM-metric dispatchers, table aggregation |
| `test_agents_registry.py` | 3 | Registry shape, factory contracts |

Total after PKG-10: **190 (current) + ~18 = ~208 tests**.

### Integration smoke (manual, in PR description)

```bash
.venv/bin/python scripts/run_all.py --skip-existing
cat results/metrics_table.csv
```

Expected `metrics_table.csv` rows (using existing cached artifacts from
PKG-4 through PKG-9 — no new LLM cost):
- `buy_and_hold` ~+103%
- `ppo` ~+40%
- `equal_weight` ~+53%
- `ddpg` ~+1%
- `multi_agent` (from 1-decision smoke; small sample) ~0%
- `single_agentic` (from earlier smoke) ~+1%
- `zero_shot` (from earlier smoke) — depends on what's cached
- `random` ~-37%

### Edge Cases Explicitly Covered

| # | Case | Test |
|---|------|------|
| 1 | Empty portfolio curve | metrics #1 (log_returns short series) |
| 2 | Flat constant pv | metrics #4 (Sharpe = 0.0) |
| 3 | All-negative returns | metrics #5 (Sortino vs Sharpe) |
| 4 | Missing audit JSONL file | aggregate #1 |
| 5 | Bad JSONL line | aggregate #2 |
| 6 | Non-LLM agent (no readers) | aggregate via `read_llm_metrics("random", ...)` returns {} |
| 7 | RL model missing | registry test skipped + `run_all` catches FileNotFoundError |
| 8 | metrics_table with nested baselines dir | aggregate #5 |

---

## VALIDATION COMMANDS

### Level 1: Syntax & Style
```bash
.venv/bin/ruff check src/ tests/ scripts/
```

### Level 2: Unit tests
```bash
.venv/bin/pytest tests/test_metrics.py tests/test_eval_aggregate.py tests/test_agents_registry.py -v
```

### Level 3: Full regression
```bash
.venv/bin/pytest tests/ 2>&1 | tail -5
```

### Level 4: CLI mocked smoke
```bash
.venv/bin/python scripts/run_all.py --help
.venv/bin/python scripts/run_all.py --skip-existing --agents buy_and_hold
```

### Level 5: Real run (no LLM spend, uses cached artifacts)
```bash
.venv/bin/python scripts/run_all.py --skip-existing
cat results/metrics_table.csv
```

### Level 6: Schema sanity vs PRD §10
```bash
.venv/bin/python <<'PY'
import json
p = "results/multi_agent/metrics.json"
import pathlib
if pathlib.Path(p).exists():
    payload = json.loads(open(p).read())
    required = {"agent", "portfolio_curve", "holdings", "metrics"}
    assert required <= set(payload.keys()), f"missing: {required - set(payload.keys())}"
    print(f"OK schema match; metrics keys: {list(payload['metrics'].keys())}")
PY
```

---

## ACCEPTANCE CRITERIA

Issue #11:
- [ ] `python -m src.eval.run_all` / `scripts/run_all.py` runs all agents
  (or all available — skips with WARN for missing models/artifacts)
- [ ] Reproducibility: 2 runs WITH `--skip-existing` produce identical
  `metrics.json` (LLM cache deferred to PKG-S; document residual drift
  in provenance block per agent)
- [ ] Person 2 lookahead audit hookable via transcripts (PKG-15 UI
  surfaces the same data; CLI script optional)
- [ ] `metrics.json` schema matches PRD §10 `GET /backtest/{agent}` payload
  (verified by Level 6 sanity)
- [ ] ~18 new tests pass; 190 prior still pass; ruff clean

---

## COMPLETION CHECKLIST

- [ ] Spike A/B/C run, outputs captured in PR description
- [ ] 3 new files in `src/eval/` + 1 in `src/agents/`
- [ ] CLI `scripts/run_all.py` works with `--help`, `--skip-existing`,
      `--agents subset`
- [ ] ~18 new tests pass; ruff clean
- [ ] `metrics_table.csv` generated; rows sorted by cum_return desc
- [ ] At least one per-agent `metrics.json` validated against PRD §10
      shape (Level 6)
- [ ] PR opened `PKG-10: Backtest engine + metrics`, body `Closes #11`
- [ ] CLAUDE.md commit attribution rule followed (no AI co-author)
- [ ] PKG-11 unblocked (`results/{agent}/metrics.json` is FastAPI's source)

---

## NOTES

### Design decisions worth flagging in PR

1. **Pure-function metrics module** — testable in isolation; golden-value
   tests pin behaviour without env coupling
2. **`total_cost` reconstructed from holdings diff** — slight
   approximation vs env's accumulated fees, but env doesn't expose
   accumulated fees and we can't change env (PKG-3 lock)
3. **`metrics_snapshot.json` per agent** — bridges the in-process
   `src.llm.metrics` singleton (PKG-5) and the persistent
   `metrics_table.csv` aggregator
4. **Per-agent reader dispatch** — single-agentic, multi-agent, zero-shot
   each have different audit shapes; central `LLM_AUDIT_READERS` dict
5. **`src/agents/__init__.py` as SERIALIZED minimal registry** —
   alphabetical entries minimize PKG-S merge friction
6. **`--skip-existing` for dev iteration** — prevents accidental $10
   re-spend when iterating on one agent
7. **PRD §10 payload assembled in `eval/backtest.py:build_payload`** —
   single source of truth for the API response shape; PKG-11 reads file

### Risks specific to PKG-10

| # | Risk | Mitigation |
|---|------|-----------|
| 1 | Existing per-agent artifacts have schema drift PKG-10 doesn't handle | Verified via parquet inspection during planning; columns are uniform |
| 2 | `--skip-existing` users miss new metrics added later | Document: re-run without flag once after metric schema changes |
| 3 | RL model files missing on PR reviewer's machine | Registry handles `FileNotFoundError`; tests use `pytest.skip` |
| 4 | metrics.json grows too large with full holdings list | ~50KB/agent for 248 sessions; acceptable for localhost; downsample in PKG-11 if SSE needs smaller |
| 5 | Multi-agent has only 1 cached decision from smoke | `metrics.json` will reflect a 1-sample average — accurate but tiny sample; full run before PKG-11 |
| 6 | `compute_total_cost` mis-aligns dates on `holdings_df` | Spike B verifies; defensive: skip rows whose date isn't in market_data |

### Khi gặp blocker

- `compute_total_cost` returns 0 for an agent that obviously traded →
  check holdings_df date format vs `market_data.dates`
- `metrics_table.csv` missing an agent → check `_has_results` logic and
  whether `metrics.json` was written
- `read_audit_jsonl` returns empty for multi_agent → check
  `results/multi_agent/decisions.jsonl` exists; smoke writes it
- Sharpe = NaN → flat portfolio_value (degenerate); fix in metric =
  return 0.0 not NaN
- RL agent constructor fails → check `results/models/{ddpg,ppo}_best.zip`
  exists; rerun PKG-9 train if missing

### Phase 3 status after PKG-10

| PKG | Status |
|-----|--------|
| PKG-5..9 | ✅ merged |
| **PKG-10 backtest + metrics (this PR)** | 🟡 ready after impl |
| PKG-11 FastAPI shell | unblocked (reads `metrics.json` directly) |
| PKG-12 SSE live route | unblocked (consumes `app.stream` from PKG-8) |
| PKG-13-16 Next.js UI | unblocked once PKG-11 serves data |
| PKG-S serialized integration | reads `metrics_table.csv` + registry |

---

## Confidence Score

**8.5/10** for one-pass implementation.

Subtract:
- −0.5 multi-source LLM-metric dispatch is N+1 plumbing; first integration
  always reveals at least one schema mismatch
- −0.5 `compute_total_cost` date-alignment is the only piece with
  off-by-one risk
- −0.5 `--skip-existing` + freshness logic could surprise a user who
  expects re-runs to overwrite

Add back:
- +1.5 Metrics math is well-trodden; golden tests catch errors instantly
- +0.5 All input artifacts (parquets, JSONLs) already exist on disk —
  PKG-10 is just a reader, not a producer

PKG-10 is the lowest-risk package since PKG-5/6/7/8/9. The work is
**aggregation, not generation** — every input is already a tested
parquet/JSONL on disk.
