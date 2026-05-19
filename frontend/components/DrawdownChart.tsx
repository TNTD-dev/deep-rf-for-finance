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

  const axisTickStyle = { fontSize: 11, fill: "#a1a1aa" };
  return (
    <ResponsiveContainer width="100%" height={300}>
      <AreaChart data={data} margin={{ top: 10, right: 20, left: 20, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(34,211,238,0.12)" />
        <XAxis
          dataKey="date"
          tick={axisTickStyle}
          minTickGap={40}
          stroke="rgba(34,211,238,0.3)"
        />
        <YAxis
          tickFormatter={(v) => formatPercent(v, 0)}
          tick={axisTickStyle}
          domain={["auto", 0]}
          width={60}
          stroke="rgba(34,211,238,0.3)"
        />
        <Tooltip
          formatter={(value: number) => [formatPercent(value, 2), "Drawdown"]}
          labelFormatter={(label) => `Date: ${label}`}
          contentStyle={{
            fontSize: 12,
            background: "rgba(8,10,12,0.92)",
            border: "1px solid rgba(248,113,113,0.4)",
            borderRadius: 6,
            color: "#e4e4e7",
          }}
          labelStyle={{ color: "#f87171", fontFamily: "var(--font-jbm)" }}
          itemStyle={{ color: "#e4e4e7" }}
        />
        <Area
          type="monotone"
          dataKey="dd"
          stroke="#f87171"
          fill="#dc2626"
          fillOpacity={0.25}
          isAnimationActive={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
