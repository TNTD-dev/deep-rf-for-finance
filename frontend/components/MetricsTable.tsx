"use client";

import { useState } from "react";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { colorFor } from "@/lib/colors";
import { formatDecimal, formatPercent, formatUSD, formatVND } from "@/lib/format";
import type { BacktestPayload } from "@/lib/types";

type Col = "cumulative_return" | "sharpe" | "sortino" | "max_drawdown" | "total_cost";

interface Props {
  payloads: Record<string, BacktestPayload>;
  visible: Set<string>;
}

export function MetricsTable({ payloads, visible }: Props) {
  const [sortKey, setSortKey] = useState<Col>("cumulative_return");
  const [sortDesc, setSortDesc] = useState(true);

  const rows = Object.values(payloads)
    .filter((p) => visible.has(p.agent))
    .map((p) => ({ name: p.agent, m: p.metrics }));

  rows.sort((a, b) => {
    const av = a.m[sortKey] ?? 0;
    const bv = b.m[sortKey] ?? 0;
    return sortDesc ? bv - av : av - bv;
  });

  const headerCell = (label: string, key: Col) => (
    <TableHead
      onClick={() => {
        if (sortKey === key) setSortDesc(!sortDesc);
        else {
          setSortKey(key);
          setSortDesc(true);
        }
      }}
      className="cursor-pointer select-none"
    >
      {label} {sortKey === key ? (sortDesc ? "↓" : "↑") : ""}
    </TableHead>
  );

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Agent</TableHead>
          {headerCell("Cum Return", "cumulative_return")}
          {headerCell("Sharpe", "sharpe")}
          {headerCell("Sortino", "sortino")}
          {headerCell("Max DD", "max_drawdown")}
          {headerCell("Total Cost", "total_cost")}
          <TableHead className="text-right">LLM Cost</TableHead>
          <TableHead className="text-right">Steps</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map(({ name, m }) => (
          <TableRow key={name}>
            <TableCell className="font-medium">
              <span className="inline-flex items-center gap-2">
                <span
                  className="inline-block h-3 w-3 rounded-sm"
                  style={{ backgroundColor: colorFor(name) }}
                />
                {name}
              </span>
            </TableCell>
            <TableCell
              className={
                m.cumulative_return >= 0 ? "text-emerald-700" : "text-red-700"
              }
            >
              {formatPercent(m.cumulative_return)}
            </TableCell>
            <TableCell>{formatDecimal(m.sharpe)}</TableCell>
            <TableCell>{formatDecimal(m.sortino)}</TableCell>
            <TableCell className="text-red-700">{formatPercent(m.max_drawdown)}</TableCell>
            <TableCell>{formatVND(m.total_cost)}</TableCell>
            <TableCell className="text-right">
              {m.llm_cost_usd !== undefined ? formatUSD(m.llm_cost_usd) : "—"}
            </TableCell>
            <TableCell className="text-right">{m.n_steps}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
