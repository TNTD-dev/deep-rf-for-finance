"use client";

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { colorFor, isBaseline } from "@/lib/colors";
import { formatVND } from "@/lib/format";
import type { BacktestPayload } from "@/lib/types";

interface Props {
  payloads: Record<string, BacktestPayload>;
  visible: Set<string>;
}

export function PortfolioChart({ payloads, visible }: Props) {
  // Wide-format merge: each row = one date with one column per agent.
  // Recharts plots multiple <Line dataKey={agent_name}> from the same dataset.
  const dateSet = new Set<string>();
  Object.values(payloads).forEach((p) =>
    p.portfolio_curve.forEach((pt) => dateSet.add(pt.date)),
  );
  const dates = Array.from(dateSet).sort();

  const merged = dates.map((date) => {
    const row: Record<string, number | string | null> = { date };
    for (const [name, p] of Object.entries(payloads)) {
      const pt = p.portfolio_curve.find((x) => x.date === date);
      // null lets Recharts skip vs 0 which would render as a drop.
      row[name] = pt ? pt.value : null;
    }
    return row;
  });

  const visibleAgents = Object.keys(payloads).filter((n) => visible.has(n));

  // Dark-theme tuned for the Intelligence Core design — recharts doesn't read
  // CSS variables so colors are inlined here. Keep them close to the cyan
  // accent palette so the chart blends with the rest of the page.
  const axisTickStyle = { fontSize: 11, fill: "#a1a1aa" };
  return (
    <ResponsiveContainer width="100%" height={420}>
      <LineChart data={merged} margin={{ top: 10, right: 20, left: 20, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(34,211,238,0.12)" />
        <XAxis
          dataKey="date"
          tick={axisTickStyle}
          minTickGap={40}
          stroke="rgba(34,211,238,0.3)"
        />
        <YAxis
          tickFormatter={(v) => formatVND(v)}
          tick={axisTickStyle}
          domain={["auto", "auto"]}
          width={70}
          stroke="rgba(34,211,238,0.3)"
        />
        <Tooltip
          formatter={(value: number, name: string) => [formatVND(value), name]}
          labelFormatter={(label) => `Date: ${label}`}
          contentStyle={{
            fontSize: 12,
            background: "rgba(8,10,12,0.92)",
            border: "1px solid rgba(34,211,238,0.3)",
            borderRadius: 6,
            color: "#e4e4e7",
          }}
          labelStyle={{ color: "#67e8f9", fontFamily: "var(--font-jbm)" }}
          itemStyle={{ color: "#e4e4e7" }}
        />
        <Legend
          wrapperStyle={{ fontSize: 11, color: "#a1a1aa" }}
          iconType="line"
        />
        {visibleAgents.map((name) => (
          <Line
            key={name}
            type="monotone"
            dataKey={name}
            stroke={colorFor(name)}
            strokeWidth={2}
            strokeDasharray={isBaseline(name) ? "5 5" : undefined}
            dot={false}
            connectNulls
            isAnimationActive={false}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
