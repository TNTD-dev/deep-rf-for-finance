// TypeScript mirror of backend/models.py — keep in sync when Pydantic changes.

export interface Provenance {
  ts: string;
  seed: number;
  test_window: string[] | null;
  n_steps: number;
}

export interface PortfolioPoint {
  date: string; // "YYYY-MM-DD"
  value: number; // int VND
}

// HoldingsPoint = {date: string, [ticker: string]: number | string}
// date is the first key; other keys are tickers (VCB, FPT, ...) mapping to int counts.
export type HoldingsPoint = { date: string } & { [ticker: string]: number | string };

export interface Metrics {
  // Required (always present from PKG-10 build_payload)
  cumulative_return: number;
  sharpe: number;
  sortino: number;
  max_drawdown: number;
  turnover: number;
  total_cost: number;
  n_steps: number;
  // LLM extras — present only on LLM / multi_agent rows
  llm_cost_usd?: number;
  avg_latency_s?: number;
  max_latency_s?: number;
  timeout_rate?: number;
  node_errors_total?: number;
  avg_debate_rounds?: number;
  parse_failure_rate?: number;
  n_decisions?: number;
  avg_iterations_per_decision?: number;
  hallucination_rate?: number;
  cap_hit_rate?: number;
  cached_tokens?: number;
  llm_calls?: number;
  // Index signature for extras Pydantic 'extra="allow"' may surface
  [key: string]: number | undefined;
}

export interface BacktestPayload {
  agent: string;
  portfolio_curve: PortfolioPoint[];
  holdings: HoldingsPoint[];
  metrics: Metrics;
  provenance: Provenance;
}

export interface AgentList {
  agents: string[];
  baselines: string[];
}

// Mirror of backend/models.py DebateEntry + DebateTranscript (PKG-11).
// content may be empty (portfolio_manager's text is replaced by a
// structured `decision` dict — see backend/routes/debate.py:53-66).

export interface DebateEntry {
  role: string; // one of ROLE_NAMES from src/llm/multi_agent/state.py
  content: string;
  model?: string | null;
  ts?: string;
  decision?: Record<string, number>;
  [key: string]: unknown;
}

export interface DebateTranscript {
  date: string;
  transcript: DebateEntry[];
}

// PKG-16: SSE event shape emitted by backend/routes/live.py.
// Discriminated union — TypeScript narrows on `type`.

export type LiveEvent =
  | { type: "agent_start"; role: string }
  | { type: "agent_complete"; role: string; summary: string }
  | { type: "decision"; weights: Record<string, number>; rationale: string }
  | { type: "error"; message: string };
