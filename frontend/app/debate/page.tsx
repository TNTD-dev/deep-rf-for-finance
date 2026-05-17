"use client";

import { useEffect, useState } from "react";

import { DatePicker } from "@/components/DatePicker";
import { DebateStream } from "@/components/DebateStream";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { BACKEND_URL, getDebate } from "@/lib/api";
import type { DebateTranscript } from "@/lib/types";

// MVP — only 1 transcript cached from PKG-8 smoke. PKG-S can add a
// backend endpoint to list available dates when more decisions accumulate.
const AVAILABLE_DEBATE_DATES = ["2025-05-05"];
const DEFAULT_AGENT = "multi_agent";

export default function DebatePage() {
  const [date, setDate] = useState<string>(AVAILABLE_DEBATE_DATES[0] ?? "");

  return (
    <main className="container mx-auto max-w-5xl space-y-6 px-4 py-6">
      <header className="border-b border-gray-200 pb-4">
        <h1 className="text-2xl font-bold tracking-tight">
          Multi-Agent Debate Replay
        </h1>
        <p className="mt-1 text-sm text-gray-600">
          One decision = 10 turns across 8 roles (3 analysts → 2 debate rounds →
          trader → risk manager → portfolio manager). Demo uses PKG-8 smoke
          transcript; more dates accumulate after PKG-S full backtest.
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold text-gray-700">
            Select date
          </CardTitle>
        </CardHeader>
        <CardContent>
          <DatePicker
            dates={AVAILABLE_DEBATE_DATES}
            value={date}
            onChange={setDate}
          />
        </CardContent>
      </Card>

      {/* key={date} forces remount on date change → fresh initial state,
          avoiding synchronous setState-in-effect (same pattern as PKG-14). */}
      <DebateInner key={date} date={date} />
    </main>
  );
}

function DebateInner({ date }: { date: string }) {
  const [transcript, setTranscript] = useState<DebateTranscript | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        setTranscript(await getDebate(DEFAULT_AGENT, date));
      } catch (e) {
        setError(String(e));
      } finally {
        setLoading(false);
      }
    })();
  }, [date]);

  if (loading) {
    return <p className="p-4 text-gray-600">Loading {date}…</p>;
  }
  if (error) {
    return (
      <div className="rounded border border-red-200 bg-red-50 p-4">
        <p className="font-semibold text-red-700">Error: {error}</p>
        <p className="mt-2 text-sm text-gray-600">
          Is the backend running at <code>{BACKEND_URL}</code>? Try{" "}
          <code>.venv/bin/uvicorn backend.main:app --port 8000</code>.
        </p>
      </div>
    );
  }
  if (!transcript) {
    return <p className="p-4">No transcript for {date}.</p>;
  }
  return <DebateStream transcript={transcript} />;
}
