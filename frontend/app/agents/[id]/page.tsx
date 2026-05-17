"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";

import { AgentBadge } from "@/components/AgentBadge";
import { AgentMetricsDetail } from "@/components/AgentMetricsDetail";
import { DrawdownChart } from "@/components/DrawdownChart";
import { HoldingsHeatmap } from "@/components/HoldingsHeatmap";
import { PortfolioChart } from "@/components/PortfolioChart";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { BACKEND_URL, getBacktest } from "@/lib/api";
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
    return <p className="p-8 text-gray-600">Loading {id}…</p>;
  }
  if (error) {
    return (
      <div className="p-8">
        <p className="text-red-700 font-semibold">Error: {error}</p>
        <p className="mt-2 text-sm text-gray-600">
          Backend at <code>{BACKEND_URL}</code> may be down, or the agent name
          {" "}<code>{id}</code> is unknown.
        </p>
        <Link href="/" className="mt-4 inline-block text-blue-600 underline">
          ← Back to dashboard
        </Link>
      </div>
    );
  }
  if (!payload) {
    return (
      <div className="p-8">
        <p>No data for {id}.</p>
        <Link href="/" className="mt-4 inline-block text-blue-600 underline">
          ← Back to dashboard
        </Link>
      </div>
    );
  }

  const single = { [id]: payload };
  const visible = new Set([id]);

  return (
    <main className="container mx-auto max-w-7xl space-y-6 px-4 py-6">
      <header className="border-b border-gray-200 pb-4">
        <Link href="/" className="text-sm text-blue-600 hover:underline">
          ← Back to dashboard
        </Link>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-bold tracking-tight">{id}</h1>
          <AgentBadge name={id} />
          <span className="text-sm text-gray-600">
            {payload.metrics.n_steps} sessions
          </span>
          {payload.provenance.test_window && (
            <span className="text-xs text-gray-500">
              {payload.provenance.test_window[0]} → {payload.provenance.test_window[1]}
            </span>
          )}
        </div>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold text-gray-700">
            Portfolio Curve
          </CardTitle>
        </CardHeader>
        <CardContent>
          <PortfolioChart payloads={single} visible={visible} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold text-gray-700">
            Drawdown
          </CardTitle>
        </CardHeader>
        <CardContent>
          <DrawdownChart payload={payload} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold text-gray-700">
            Holdings Heatmap
          </CardTitle>
        </CardHeader>
        <CardContent>
          <HoldingsHeatmap payload={payload} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold text-gray-700">
            Metrics Detail
          </CardTitle>
        </CardHeader>
        <CardContent>
          <AgentMetricsDetail metrics={payload.metrics} />
        </CardContent>
      </Card>
    </main>
  );
}
