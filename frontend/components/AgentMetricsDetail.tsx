"use client";

import { formatDecimal, formatPercent, formatUSD, formatVND } from "@/lib/format";
import type { Metrics } from "@/lib/types";

interface Props {
  metrics: Metrics;
}

function formatMetric(key: string, value: number | undefined): string {
  if (value === undefined) return "—";
  if (
    key.endsWith("_return") ||
    key.endsWith("_drawdown") ||
    key.endsWith("_rate")
  ) {
    return formatPercent(value, 2);
  }
  if (key === "total_cost") return formatVND(value);
  if (key === "llm_cost_usd") return formatUSD(value);
  if (
    key === "n_steps" ||
    key === "n_decisions" ||
    key === "node_errors_total" ||
    key === "cached_tokens" ||
    key === "llm_calls"
  ) {
    return value.toLocaleString();
  }
  if (key.endsWith("_s")) return `${formatDecimal(value)}s`;
  return formatDecimal(value, 3);
}

function prettyKey(key: string): string {
  return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function AgentMetricsDetail({ metrics }: Props) {
  const entries = Object.entries(metrics).filter(
    ([, v]) => v !== undefined && v !== null,
  );
  return (
    <dl className="grid grid-cols-1 gap-px bg-cyan-400/10 sm:grid-cols-2 lg:grid-cols-3">
      {entries.map(([k, v]) => (
        <div key={k} className="bg-black/50 px-4 py-3">
          <dt className="label-mono text-zinc-500">{prettyKey(k)}</dt>
          <dd className="mt-1.5 font-mono text-sm font-medium text-zinc-100 tabular-nums">
            {formatMetric(k, v as number | undefined)}
          </dd>
        </div>
      ))}
    </dl>
  );
}
