"use client";

import { useEffect, useState } from "react";

import { AgentToggle } from "@/components/AgentToggle";
import { MetricsTable } from "@/components/MetricsTable";
import { PortfolioChart } from "@/components/PortfolioChart";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { BACKEND_URL, getAgents, getBacktest } from "@/lib/api";
import type { BacktestPayload } from "@/lib/types";

export default function HomePage() {
  const [payloads, setPayloads] = useState<Record<string, BacktestPayload>>({});
  const [visible, setVisible] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const list = await getAgents();
        const all = [...list.baselines, ...list.agents].sort();
        const results = await Promise.allSettled(all.map(getBacktest));
        const ok: Record<string, BacktestPayload> = {};
        results.forEach((r, i) => {
          if (r.status === "fulfilled") ok[all[i]] = r.value;
        });
        setPayloads(ok);
        setVisible(new Set(Object.keys(ok)));
      } catch (e) {
        setError(String(e));
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) {
    return <p className="p-8 text-gray-600">Loading…</p>;
  }
  if (error) {
    return (
      <div className="p-8">
        <p className="text-red-700 font-semibold">Error: {error}</p>
        <p className="text-sm text-gray-600 mt-2">
          Is the backend running at <code>{BACKEND_URL}</code>? Start with{" "}
          <code>.venv/bin/uvicorn backend.main:app --port 8000</code>.
        </p>
      </div>
    );
  }
  if (Object.keys(payloads).length === 0) {
    return (
      <p className="p-8">
        No agents have backtest data yet. Run{" "}
        <code>.venv/bin/python scripts/run_all.py --skip-existing</code> first.
      </p>
    );
  }

  return (
    <main className="container mx-auto max-w-7xl space-y-6 px-4 py-6">
      <header className="border-b border-gray-200 pb-4">
        <h1 className="text-2xl font-bold tracking-tight">
          DRL vs LLM/Agentic Trading — VN30
        </h1>
        <p className="mt-1 text-sm text-gray-600">
          Test period 2025-05-05 → 2026-04-29 · 248 sessions ·{" "}
          {Object.keys(payloads).length} agents
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold text-gray-700">
            Show / Hide Agents
          </CardTitle>
        </CardHeader>
        <CardContent>
          <AgentToggle
            agents={Object.keys(payloads).sort()}
            visible={visible}
            onChange={setVisible}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold text-gray-700">
            Portfolio Curve Overlay
          </CardTitle>
        </CardHeader>
        <CardContent>
          <PortfolioChart payloads={payloads} visible={visible} />
          <p className="mt-2 text-xs text-gray-500">
            Baselines render dashed (background context). RL agents = cool blues.
            LLM agents = warm reds/orange. LLM curves have only 5-11 points (smoke
            runs); chart connects across gaps.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold text-gray-700">Metrics</CardTitle>
        </CardHeader>
        <CardContent>
          <MetricsTable payloads={payloads} visible={visible} />
        </CardContent>
      </Card>

      <footer className="border-t border-gray-200 pt-4 text-xs text-gray-500">
        Backend (PKG-11) <code className="rounded bg-gray-100 px-1">{BACKEND_URL}</code>
        {" · "}Next.js 16 + Tailwind v4 + shadcn/ui + Recharts
      </footer>
    </main>
  );
}
