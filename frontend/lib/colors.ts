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
