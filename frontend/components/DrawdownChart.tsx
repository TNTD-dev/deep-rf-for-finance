"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatPercent } from "@/lib/format";
import type { BacktestPayload } from "@/lib/types";

interface Props {
  payload: BacktestPayload;
}

function computeDrawdownSeries(
  curve: BacktestPayload["portfolio_curve"],
): { date: string; dd: number }[] {
  // Port of src/eval/metrics.py:compute_max_drawdown — dd_t = (rm - pv) / rm.
  // Negate so chart plots BELOW zero (visually intuitive — losses are down).
  // Helper lives outside the component so the running-max accumulator is
  // not flagged by react-hooks/immutability on render.
  const out: { date: string; dd: number }[] = [];
  let runningMax = -Infinity;
  for (const pt of curve) {
    if (pt.value > runningMax) runningMax = pt.value;
    const dd = runningMax > 0 ? -(runningMax - pt.value) / runningMax : 0;
    out.push({ date: pt.date, dd });
  }
  return out;
}

export function DrawdownChart({ payload }: Props) {
  const data = computeDrawdownSeries(payload.portfolio_curve);

  return (
    <ResponsiveContainer width="100%" height={300}>
      <AreaChart data={data} margin={{ top: 10, right: 20, left: 20, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
        <XAxis dataKey="date" tick={{ fontSize: 11 }} minTickGap={40} />
        <YAxis
          tickFormatter={(v) => formatPercent(v, 0)}
          tick={{ fontSize: 11 }}
          domain={["auto", 0]}
          width={60}
        />
        <Tooltip
          formatter={(value: number) => [formatPercent(value, 2), "Drawdown"]}
          labelFormatter={(label) => `Date: ${label}`}
          contentStyle={{ fontSize: 12 }}
        />
        <Area
          type="monotone"
          dataKey="dd"
          stroke="#dc2626"
          fill="#ef4444"
          fillOpacity={0.2}
          isAnimationActive={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
