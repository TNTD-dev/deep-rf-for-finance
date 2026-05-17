import type {
  AgentList,
  BacktestPayload,
  DebateDatesResponse,
  DebateTranscript,
} from "@/lib/types";

// Hardcoded for localhost demo. To change for a moving demo, edit this line.
export const BACKEND_URL = "http://localhost:8000";

export async function getAgents(): Promise<AgentList> {
  const r = await fetch(`${BACKEND_URL}/agents`);
  if (!r.ok) throw new Error(`GET /agents failed: ${r.status}`);
  return r.json();
}

export async function getBacktest(agent: string): Promise<BacktestPayload> {
  const r = await fetch(`${BACKEND_URL}/backtest/${agent}`);
  if (!r.ok) throw new Error(`GET /backtest/${agent} failed: ${r.status}`);
  return r.json();
}

export async function getDebate(
  agent: string,
  date: string,
): Promise<DebateTranscript> {
  const r = await fetch(`${BACKEND_URL}/debate/${agent}/${date}`);
  if (!r.ok) throw new Error(`GET /debate/${agent}/${date} failed: ${r.status}`);
  return r.json();
}

export async function getDebateDates(
  agent: string,
): Promise<DebateDatesResponse> {
  const r = await fetch(`${BACKEND_URL}/debate/${agent}`);
  if (!r.ok) throw new Error(`GET /debate/${agent} failed: ${r.status}`);
  return r.json();
}
