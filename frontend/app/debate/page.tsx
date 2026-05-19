"use client";

import { useEffect, useState } from "react";

import { DatePicker } from "@/components/DatePicker";
import { DebateGraph } from "@/components/DebateGraph";
import { DebateStream } from "@/components/DebateStream";
import { ScrollFade } from "@/components/ScrollFade";
import { GlassPanel, Kicker } from "@/components/ui/glass";
import { BACKEND_URL, getDebate, getDebateDates } from "@/lib/api";
import type { DebateTranscript } from "@/lib/types";

// PKG-S S5b: dates are fetched from `GET /debate/multi_agent` on mount instead
// of a hardcoded list. Frontend/backend coupling on filesystem paths is gone.
const DEFAULT_AGENT = "multi_agent";

export default function DebatePage() {
  const [dates, setDates] = useState<string[]>([]);
  const [date, setDate] = useState<string>("");
  const [datesError, setDatesError] = useState<string | null>(null);
  const [datesLoading, setDatesLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const res = await getDebateDates(DEFAULT_AGENT);
        setDates(res.dates);
        if (res.dates.length > 0) setDate(res.dates[res.dates.length - 1]);
      } catch (e) {
        setDatesError(String(e));
      } finally {
        setDatesLoading(false);
      }
    })();
  }, []);

  return (
    <main className="container mx-auto max-w-5xl px-6 pt-10 pb-16 space-y-8">
      <ScrollFade>
        <header className="space-y-3">
          <Kicker>Multi-agent replay</Kicker>
          <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight text-white">
            Debate transcripts
          </h1>
          <p className="text-sm text-zinc-400 max-w-2xl">
            One decision = 10 turns across 8 roles (3 analysts → 2 debate rounds
            → trader → risk manager → portfolio manager). Pick a date to replay
            the full deliberation that produced that day's portfolio weights.
          </p>
        </header>
      </ScrollFade>

      <ScrollFade delayMs={80}>
        <GlassPanel>
          <div className="p-6">
            <Kicker>Select date</Kicker>
            <div className="mt-4">
              {datesLoading ? (
                <p className="font-mono text-sm text-zinc-400">
                  Đang load danh sách ngày…
                </p>
              ) : datesError ? (
                <DatesError message={datesError} />
              ) : dates.length === 0 ? (
                <EmptyDates />
              ) : (
                <DatePicker dates={dates} value={date} onChange={setDate} />
              )}
            </div>
          </div>
        </GlassPanel>
      </ScrollFade>

      {/* key={date} forces remount on date change → fresh initial state,
          avoiding synchronous setState-in-effect (same pattern as PKG-14). */}
      {date && <DebateInner key={date} date={date} />}
    </main>
  );
}

function DatesError({ message }: { message: string }) {
  return (
    <div className="rounded-md border border-rose-400/30 bg-rose-500/10 p-4">
      <p className="font-mono text-sm font-semibold text-rose-300">
        Error loading dates: {message}
      </p>
      <p className="mt-2 text-sm text-zinc-400">
        Is the backend running at{" "}
        <code className="rounded bg-cyan-400/10 px-1.5 py-0.5 font-mono text-cyan-300">
          {BACKEND_URL}
        </code>
        ? Try{" "}
        <code className="rounded bg-cyan-400/10 px-1.5 py-0.5 font-mono text-cyan-300">
          .venv/bin/uvicorn backend.main:app --port 8000
        </code>
        .
      </p>
    </div>
  );
}

function EmptyDates() {
  return (
    <div className="rounded-md border border-amber-400/30 bg-amber-400/10 p-4 text-sm text-amber-200">
      <p className="font-semibold">Chưa có transcripts.</p>
      <p className="mt-1 text-amber-100/80">
        Run{" "}
        <code className="rounded bg-amber-400/10 px-1.5 py-0.5 font-mono text-amber-200">
          .venv/bin/python scripts/run_multi_agent.py
        </code>{" "}
        để sinh transcripts. Mỗi decision ≈ 30s và sẽ xuất hiện ở đây sau khi
        script hoàn tất.
      </p>
    </div>
  );
}

function DebateInner({ date }: { date: string }) {
  const [transcript, setTranscript] = useState<DebateTranscript | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeRole, setActiveRole] = useState<string | null>(null);

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
    return (
      <p className="font-mono text-sm text-zinc-400">Loading {date}…</p>
    );
  }
  if (error) {
    return (
      <GlassPanel>
        <div className="p-6">
          <Kicker className="text-rose-300">Error</Kicker>
          <p className="mt-3 font-mono text-sm text-zinc-200">{error}</p>
          <p className="mt-3 text-sm text-zinc-400">
            Is the backend running at{" "}
            <code className="rounded bg-cyan-400/10 px-1.5 py-0.5 font-mono text-cyan-300">
              {BACKEND_URL}
            </code>
            ?
          </p>
        </div>
      </GlassPanel>
    );
  }
  if (!transcript) {
    return <p className="text-zinc-300">No transcript for {date}.</p>;
  }

  const onSelect = (role: string) => {
    setActiveRole(role);
    // Smooth-scroll the matching entry into view.
    const el = document.querySelector(`[data-role="${role}"]`);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  return (
    <div className="space-y-8">
      <GlassPanel>
        <div className="p-6">
          <Kicker>Decision flow · click a role to jump</Kicker>
          <div className="mt-5">
            <DebateGraph
              transcript={transcript}
              activeRole={activeRole}
              onSelect={onSelect}
            />
          </div>
        </div>
      </GlassPanel>
      <div>
        <Kicker>Transcript</Kicker>
        <div className="mt-4">
          <DebateStream transcript={transcript} activeRole={activeRole} />
        </div>
      </div>
    </div>
  );
}
