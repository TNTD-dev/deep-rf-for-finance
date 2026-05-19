"use client";

import Link from "next/link";
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
      className="cursor-pointer select-none label-mono text-zinc-500 hover:text-cyan-300 transition-colors"
    >
      {label} {sortKey === key ? (sortDesc ? "↓" : "↑") : ""}
    </TableHead>
  );

  return (
    <Table>
      <TableHeader>
        <TableRow className="border-cyan-400/15 hover:bg-transparent">
          <TableHead className="label-mono text-zinc-500">Agent</TableHead>
          {headerCell("Cum Return", "cumulative_return")}
          {headerCell("Sharpe", "sharpe")}
          {headerCell("Sortino", "sortino")}
          {headerCell("Max DD", "max_drawdown")}
          {headerCell("Total Cost", "total_cost")}
          <TableHead className="text-right label-mono text-zinc-500">
            LLM Cost
          </TableHead>
          <TableHead className="text-right label-mono text-zinc-500">
            Steps
          </TableHead>
        </TableRow>
      </TableHeader>
      <TableBody className="font-mono text-[13px]">
        {rows.map(({ name, m }) => (
          <TableRow
            key={name}
            className="border-cyan-400/8 hover:bg-cyan-400/5 transition-colors"
          >
            <TableCell className="font-medium">
              {/* PKG-14: wrap agent name in Link to enable /agents/{id} navigation. */}
              <Link
                href={`/agents/${name}`}
                className="inline-flex items-center gap-2 text-zinc-100 hover:text-cyan-300 transition-colors"
              >
                <span
                  className="inline-block h-3 w-3 rounded-sm ring-1 ring-black/30"
                  style={{
                    backgroundColor: colorFor(name),
                    boxShadow: `0 0 8px ${colorFor(name)}55`,
                  }}
                />
                {name}
              </Link>
            </TableCell>
            <TableCell
              className={`tabular-nums ${
                m.cumulative_return >= 0 ? "text-cyan-300" : "text-rose-400"
              }`}
            >
              {formatPercent(m.cumulative_return)}
            </TableCell>
            <TableCell className="tabular-nums text-zinc-200">
              {formatDecimal(m.sharpe)}
            </TableCell>
            <TableCell className="tabular-nums text-zinc-200">
              {formatDecimal(m.sortino)}
            </TableCell>
            <TableCell className="tabular-nums text-rose-400">
              {formatPercent(m.max_drawdown)}
            </TableCell>
            <TableCell className="tabular-nums text-zinc-400">
              {formatVND(m.total_cost)}
            </TableCell>
            <TableCell className="text-right tabular-nums text-zinc-300">
              {m.llm_cost_usd !== undefined ? formatUSD(m.llm_cost_usd) : "—"}
            </TableCell>
            <TableCell className="text-right tabular-nums text-zinc-500">
              {m.n_steps}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
