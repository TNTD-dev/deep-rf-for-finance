"use client";

import { useEffect, useState } from "react";

import { AgentToggle } from "@/components/AgentToggle";
import { MetricsTable } from "@/components/MetricsTable";
import { PortfolioChart } from "@/components/PortfolioChart";
import { ScrollFade } from "@/components/ScrollFade";
import { GlassPanel, Kicker } from "@/components/ui/glass";
import { BACKEND_URL, getAgents, getBacktest } from "@/lib/api";
import type { BacktestPayload } from "@/lib/types";

export default function DashboardPage() {
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
    return (
      <main className="container mx-auto max-w-7xl px-6 py-16">
        <p className="font-mono text-sm text-zinc-400">
          Polling backend at <code className="text-cyan-300">{BACKEND_URL}</code>…
        </p>
      </main>
    );
  }

  if (error) {
    return (
      <main className="container mx-auto max-w-7xl px-6 py-16">
        <GlassPanel>
          <div className="p-7">
            <Kicker className="text-rose-300">Backend unreachable</Kicker>
            <p className="mt-3 text-zinc-200 font-mono text-sm">{error}</p>
            <p className="mt-4 text-sm text-zinc-400">
              Is the backend running at{" "}
              <code className="rounded bg-cyan-400/10 px-1.5 py-0.5 font-mono text-cyan-300">
                {BACKEND_URL}
              </code>
              ? Start with{" "}
              <code className="rounded bg-cyan-400/10 px-1.5 py-0.5 font-mono text-cyan-300">
                .venv/bin/uvicorn backend.main:app --port 8000
              </code>
              .
            </p>
          </div>
        </GlassPanel>
      </main>
    );
  }

  if (Object.keys(payloads).length === 0) {
    return (
      <main className="container mx-auto max-w-7xl px-6 py-16">
        <GlassPanel>
          <div className="p-7">
            <Kicker>Empty</Kicker>
            <p className="mt-3 text-zinc-300">
              No agents have backtest data yet. Run{" "}
              <code className="rounded bg-cyan-400/10 px-1.5 py-0.5 font-mono text-cyan-300">
                .venv/bin/python scripts/run_all.py --skip-existing
              </code>{" "}
              first.
            </p>
          </div>
        </GlassPanel>
      </main>
    );
  }

  return (
    <main className="container mx-auto max-w-7xl px-6 pt-10 pb-16 space-y-8">
      <ScrollFade>
        <header className="space-y-3">
          <Kicker>Comparison · full test window</Kicker>
          <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight text-white">
            Eight agents, one chart
          </h1>
          <p className="text-sm text-zinc-400 max-w-2xl">
            Test period 2025-05-05 → 2026-04-29 · 248 sessions ·{" "}
            <span className="text-cyan-300">{Object.keys(payloads).length} agents loaded</span>
          </p>
        </header>
      </ScrollFade>

      <ScrollFade delayMs={80}>
        <GlassPanel>
          <div className="p-6">
            <Kicker>Show / Hide</Kicker>
            <div className="mt-4">
              <AgentToggle
                agents={Object.keys(payloads).sort()}
                visible={visible}
                onChange={setVisible}
              />
            </div>
          </div>
        </GlassPanel>
      </ScrollFade>

      <ScrollFade delayMs={140}>
        <GlassPanel>
          <div className="p-6">
            <Kicker>Portfolio curve overlay</Kicker>
            <div className="mt-4">
              <PortfolioChart payloads={payloads} visible={visible} />
            </div>
            <p className="mt-3 text-xs text-zinc-500">
              Baselines render dashed (background context). RL agents = cool
              blues. LLM agents = warm reds/orange. Smoke-only LLM curves have
              5–11 points; chart connects across gaps.
            </p>
          </div>
        </GlassPanel>
      </ScrollFade>

      <ScrollFade delayMs={200}>
        <GlassPanel>
          <div className="p-6">
            <Kicker>Metrics</Kicker>
            <div className="mt-4 overflow-x-auto">
              <MetricsTable payloads={payloads} visible={visible} />
            </div>
          </div>
        </GlassPanel>
      </ScrollFade>
    </main>
  );
}
