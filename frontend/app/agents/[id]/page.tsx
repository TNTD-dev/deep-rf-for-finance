"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";

import { AgentBadge } from "@/components/AgentBadge";
import { AgentMetricsDetail } from "@/components/AgentMetricsDetail";
import { DrawdownChart } from "@/components/DrawdownChart";
import { HoldingsHeatmap } from "@/components/HoldingsHeatmap";
import { PortfolioChart } from "@/components/PortfolioChart";
import { ScrollFade } from "@/components/ScrollFade";
import { GlassPanel, Kicker } from "@/components/ui/glass";
import { BACKEND_URL, getBacktest } from "@/lib/api";
import { colorFor } from "@/lib/colors";
import type { BacktestPayload } from "@/lib/types";

export default function AgentDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  // key={id} forces remount on id change → fresh initial state. Lets us
  // avoid synchronous setState-in-effect (banned by react-hooks rule).
  return <AgentDetailInner key={id} id={id} />;
}

function AgentDetailInner({ id }: { id: string }) {
  const [payload, setPayload] = useState<BacktestPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        setPayload(await getBacktest(id));
      } catch (e) {
        setError(String(e));
      } finally {
        setLoading(false);
      }
    })();
  }, [id]);

  if (loading) {
    return (
      <main className="container mx-auto max-w-7xl px-6 py-16">
        <p className="font-mono text-sm text-zinc-400">Loading {id}…</p>
      </main>
    );
  }
  if (error) {
    return (
      <main className="container mx-auto max-w-7xl px-6 py-16">
        <GlassPanel>
          <div className="p-7">
            <Kicker className="text-rose-300">Error</Kicker>
            <p className="mt-3 font-mono text-sm text-zinc-200">{error}</p>
            <p className="mt-3 text-sm text-zinc-400">
              Backend at{" "}
              <code className="rounded bg-cyan-400/10 px-1.5 py-0.5 font-mono text-cyan-300">
                {BACKEND_URL}
              </code>{" "}
              may be down, or agent <code className="text-cyan-300">{id}</code>{" "}
              is unknown.
            </p>
            <Link
              href="/dashboard"
              className="mt-5 inline-flex font-mono text-xs uppercase tracking-[0.12em] text-cyan-300 link-glow"
            >
              ← Back to dashboard
            </Link>
          </div>
        </GlassPanel>
      </main>
    );
  }
  if (!payload) {
    return (
      <main className="container mx-auto max-w-7xl px-6 py-16">
        <p className="text-zinc-300">No data for {id}.</p>
        <Link
          href="/dashboard"
          className="mt-4 inline-flex font-mono text-xs uppercase tracking-[0.12em] text-cyan-300 link-glow"
        >
          ← Back to dashboard
        </Link>
      </main>
    );
  }

  const single = { [id]: payload };
  const visible = new Set([id]);
  const cum = payload.metrics.cumulative_return;
  const color = colorFor(id);

  return (
    <main className="container mx-auto max-w-7xl px-6 pt-10 pb-16 space-y-8">
      <ScrollFade>
        <div>
          <Link
            href="/dashboard"
            className="font-mono text-xs uppercase tracking-[0.12em] text-zinc-500 link-glow"
          >
            ← Back to dashboard
          </Link>
          <div className="mt-4 flex flex-wrap items-end gap-4">
            <div className="flex items-center gap-3">
              <span
                className="h-4 w-4 rounded-full ring-2 ring-black/20"
                style={{ background: color, boxShadow: `0 0 16px ${color}88` }}
              />
              <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight text-white">
                {id}
              </h1>
            </div>
            <AgentBadge name={id} />
            <div className="ml-auto text-right">
              <p className="label-mono">Cumulative return</p>
              <p
                className={`mt-1 text-3xl font-semibold tabular-nums ${
                  cum >= 0 ? "text-cyan-300" : "text-rose-400"
                }`}
              >
                {cum >= 0 ? "+" : ""}
                {(cum * 100).toFixed(2)}%
              </p>
            </div>
          </div>
          <p className="mt-3 text-sm text-zinc-400 font-mono">
            {payload.metrics.n_steps} sessions
            {payload.provenance.test_window && (
              <>
                {" · "}
                {payload.provenance.test_window[0]} →{" "}
                {payload.provenance.test_window[1]}
              </>
            )}
          </p>
        </div>
      </ScrollFade>

      <ScrollFade delayMs={80}>
        <GlassPanel>
          <div className="p-6">
            <Kicker>Portfolio curve</Kicker>
            <div className="mt-4">
              <PortfolioChart payloads={single} visible={visible} />
            </div>
          </div>
        </GlassPanel>
      </ScrollFade>

      <ScrollFade delayMs={140}>
        <GlassPanel>
          <div className="p-6">
            <Kicker>Drawdown</Kicker>
            <div className="mt-4">
              <DrawdownChart payload={payload} />
            </div>
          </div>
        </GlassPanel>
      </ScrollFade>

      <ScrollFade delayMs={200}>
        <GlassPanel>
          <div className="p-6">
            <Kicker>Holdings heatmap</Kicker>
            <div className="mt-4">
              <HoldingsHeatmap payload={payload} />
            </div>
          </div>
        </GlassPanel>
      </ScrollFade>

      <ScrollFade delayMs={260}>
        <GlassPanel>
          <div className="p-6">
            <Kicker>Metrics detail</Kicker>
            <div className="mt-4">
              <AgentMetricsDetail metrics={payload.metrics} />
            </div>
          </div>
        </GlassPanel>
      </ScrollFade>
    </main>
  );
}
