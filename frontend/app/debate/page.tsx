"use client";

import { useEffect, useState } from "react";

import { DatePicker } from "@/components/DatePicker";
import { DebateStream } from "@/components/DebateStream";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
    <main className="container mx-auto max-w-5xl space-y-6 px-4 py-6">
      <header className="border-b border-gray-200 pb-4">
        <h1 className="text-2xl font-bold tracking-tight">
          Multi-Agent Debate Replay
        </h1>
        <p className="mt-1 text-sm text-gray-600">
          One decision = 10 turns across 8 roles (3 analysts → 2 debate rounds →
          trader → risk manager → portfolio manager). Dates discovered from
          backend; pick any to replay.
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold text-gray-700">
            Select date
          </CardTitle>
        </CardHeader>
        <CardContent>
          {datesLoading ? (
            <p className="text-sm text-gray-600">Đang load danh sách ngày…</p>
          ) : datesError ? (
            <DatesError message={datesError} />
          ) : dates.length === 0 ? (
            <EmptyDates />
          ) : (
            <DatePicker dates={dates} value={date} onChange={setDate} />
          )}
        </CardContent>
      </Card>

      {/* key={date} forces remount on date change → fresh initial state,
          avoiding synchronous setState-in-effect (same pattern as PKG-14). */}
      {date && <DebateInner key={date} date={date} />}
    </main>
  );
}

function DatesError({ message }: { message: string }) {
  return (
    <div className="rounded border border-red-200 bg-red-50 p-4">
      <p className="font-semibold text-red-700">Error loading dates: {message}</p>
      <p className="mt-2 text-sm text-gray-600">
        Is the backend running at <code>{BACKEND_URL}</code>? Try{" "}
        <code>.venv/bin/uvicorn backend.main:app --port 8000</code>.
      </p>
    </div>
  );
}

function EmptyDates() {
  return (
    <div className="rounded border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
      <p className="font-semibold">Chưa có transcripts.</p>
      <p className="mt-1">
        Run <code>.venv/bin/python scripts/run_multi_agent.py</code> để sinh
        transcripts. Mỗi decision ≈ 30s và sẽ xuất hiện ở đây sau khi script
        hoàn tất.
      </p>
    </div>
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
