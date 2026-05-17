// Deterministic name → color. Baselines desaturated (background context);
// agents distinct hues (foreground signal). PortfolioChart + MetricsTable +
// AgentToggle all read from this map so the visual story stays consistent.

export const AGENT_COLORS: Record<string, string> = {
  // Baselines — grays, dashed in chart
  buy_and_hold: "#9ca3af", // slate-400
  equal_weight: "#6b7280", // gray-500
  random: "#d1d5db", // gray-300

  // RL agents — cool blues
  ddpg: "#3b82f6", // blue-500
  ppo: "#0ea5e9", // sky-500

  // LLM agents — warm reds/oranges
  zero_shot: "#f59e0b", // amber-500
  single_agentic: "#ef4444", // red-500
  multi_agent: "#dc2626", // red-600 (the headline agent)
};

export const BASELINE_NAMES = new Set(["buy_and_hold", "equal_weight", "random"]);

export const isBaseline = (name: string): boolean => BASELINE_NAMES.has(name);

export const colorFor = (name: string): string => AGENT_COLORS[name] ?? "#94a3b8";

// Agent category (used by AgentBadge + future grouping). Kept here so the
// taxonomy lives next to the color palette — both encode the same logical
// grouping (baselines = grays, RL = blues, LLM = warm).
const RL_NAMES = new Set(["ddpg", "ppo"]);
const LLM_NAMES = new Set(["zero_shot", "single_agentic", "multi_agent"]);

export type AgentCategory = "baseline" | "rl" | "llm";

export function agentCategory(name: string): AgentCategory {
  if (BASELINE_NAMES.has(name)) return "baseline";
  if (RL_NAMES.has(name)) return "rl";
  if (LLM_NAMES.has(name)) return "llm";
  return "baseline";
}
