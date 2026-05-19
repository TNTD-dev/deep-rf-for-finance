"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { DatePicker } from "@/components/DatePicker";
import { DebateEntry } from "@/components/DebateEntry";
import { DebateGraph } from "@/components/DebateGraph";
import { ScrollFade } from "@/components/ScrollFade";
import { GlassPanel, Kicker } from "@/components/ui/glass";
import { BACKEND_URL, getDebate, getDebateDates } from "@/lib/api";
import { roleColor } from "@/lib/colors";
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
    <main className="container mx-auto max-w-6xl px-6 pt-8 pb-16 space-y-6">
      <ScrollFade>
        <header className="flex flex-wrap items-end justify-between gap-4">
          <div className="space-y-2">
            <Kicker>Multi-agent replay</Kicker>
            <h1
              className="text-3xl sm:text-4xl font-bold tracking-tight text-white"
              style={{ fontFamily: "var(--font-grotesk)" }}
            >
              Debate transcripts
            </h1>
            <p className="text-xs text-zinc-500 font-mono max-w-xl">
              10 turns · 8 roles · 1 decision · use ← → to step through
            </p>
          </div>
          <div>
            {datesLoading ? (
              <p className="font-mono text-sm text-zinc-400">Loading dates…</p>
            ) : datesError ? null : dates.length === 0 ? null : (
              <DatePicker dates={dates} value={date} onChange={setDate} />
            )}
          </div>
        </header>
      </ScrollFade>

      {/* Surface error / empty state inline if the date list fetch failed. */}
      {datesError && <DatesError message={datesError} />}
      {!datesLoading && !datesError && dates.length === 0 && <EmptyDates />}

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

/** Walk the transcript; assign 1-based round numbers to bull/bear pairs.
 *  Mirrors DebateStream's old helper so we can label NavStrip pills + the
 *  active DebateEntry with R1 / R2 markers. Pure function, no React. */
function assignDebateRounds(
  entries: DebateTranscript["transcript"],
): (number | undefined)[] {
  const out: (number | undefined)[] = new Array(entries.length).fill(undefined);
  let round = 0;
  for (let i = 0; i < entries.length; i++) {
    const r = entries[i].role;
    if (r === "bullish_researcher") {
      round += 1;
      out[i] = round;
    } else if (r === "bearish_researcher") {
      out[i] = round;
    }
  }
  return out;
}

function DebateInner({ date }: { date: string }) {
  const [transcript, setTranscript] = useState<DebateTranscript | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  // Single-active-entry model: instead of scrolling through 10 stacked
  // entries we render exactly one at a time. activeIdx is the index into
  // transcript.transcript[]; nav strip + keyboard + graph all converge on it.
  const [activeIdx, setActiveIdx] = useState(0);

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

  // Reset to first entry on date change.
  useEffect(() => setActiveIdx(0), [date]);

  const entries = transcript?.transcript ?? [];
  const total = entries.length;
  const rounds = useMemo(() => assignDebateRounds(entries), [entries]);
  const activeEntry = entries[activeIdx];

  const go = useCallback(
    (idx: number) => {
      if (idx < 0 || idx >= total) return;
      setActiveIdx(idx);
    },
    [total],
  );

  // Keyboard navigation — ← / → step through entries. Ignored when the user
  // is typing in an input (defensive; debate page has only a <select>).
  useEffect(() => {
    if (total === 0) return;
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === "INPUT" || target.tagName === "TEXTAREA")
      ) {
        return;
      }
      if (e.key === "ArrowRight") {
        e.preventDefault();
        setActiveIdx((i) => Math.min(i + 1, total - 1));
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        setActiveIdx((i) => Math.max(i - 1, 0));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [total]);

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
  if (!transcript || total === 0) {
    return <p className="text-zinc-300">No transcript for {date}.</p>;
  }

  // Clicking a role node in the graph: find the first entry of that role at
  // or after the current index (so successive clicks step through bull R1 →
  // bull R2 etc). If none after, wrap to the first occurrence.
  const onSelectRole = (role: string) => {
    let idx = entries.findIndex((e, i) => i > activeIdx && e.role === role);
    if (idx === -1) idx = entries.findIndex((e) => e.role === role);
    if (idx !== -1) setActiveIdx(idx);
  };

  return (
    <div className="space-y-6">
      {/* Pipeline graph — sticks to the top of the column while the entry
          scrolls beneath, but only on lg+ (mobile has limited height). */}
      <ScrollFade>
        <GlassPanel>
          <div className="p-6">
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <Kicker>Decision flow · click any role</Kicker>
              <p className="font-mono text-[11px] text-zinc-500">
                <kbd className="rounded border border-cyan-400/20 bg-cyan-400/5 px-1.5 py-0.5 text-cyan-300">
                  ←
                </kbd>{" "}
                <kbd className="rounded border border-cyan-400/20 bg-cyan-400/5 px-1.5 py-0.5 text-cyan-300">
                  →
                </kbd>{" "}
                to step through
              </p>
            </div>
            <div className="mt-5">
              <DebateGraph
                transcript={transcript}
                activeRole={activeEntry?.role ?? null}
                onSelect={onSelectRole}
              />
            </div>
          </div>
        </GlassPanel>
      </ScrollFade>

      {/* Compact nav strip — horizontally scrollable, every entry as a pill
          with role color, round marker, and active glow. */}
      <NavStrip
        entries={entries}
        rounds={rounds}
        activeIdx={activeIdx}
        onSelect={setActiveIdx}
      />

      {/* Active entry — exactly one at a time, no scroll-through. */}
      {activeEntry && (
        <div className="relative">
          <DebateEntry
            entry={activeEntry}
            round={rounds[activeIdx]}
            active
          />
          <NavControls
            activeIdx={activeIdx}
            total={total}
            onPrev={() => go(activeIdx - 1)}
            onNext={() => go(activeIdx + 1)}
          />
        </div>
      )}
    </div>
  );
}

/* ───────────────────────── NavStrip + NavControls ──────────────────────── */

function NavStrip({
  entries,
  rounds,
  activeIdx,
  onSelect,
}: {
  entries: DebateTranscript["transcript"];
  rounds: (number | undefined)[];
  activeIdx: number;
  onSelect: (i: number) => void;
}) {
  // Friendly short labels — full role names take too much horizontal space
  // when 10 pills sit side by side.
  const SHORT: Record<string, string> = {
    technical_analyst: "Technical",
    news_sentiment_analyst: "News",
    fundamental_analyst: "Fundamental",
    bullish_researcher: "Bull",
    bearish_researcher: "Bear",
    trader: "Trader",
    risk_manager: "Risk",
    portfolio_manager: "Portfolio",
  };
  return (
    <div className="-mx-2 px-2 overflow-x-auto">
      <ol className="flex items-stretch gap-1.5 min-w-max py-1">
        {entries.map((e, i) => {
          const isActive = i === activeIdx;
          const isPast = i < activeIdx;
          const color = roleColor(e.role);
          const label = SHORT[e.role] ?? e.role;
          const round = rounds[i];
          return (
            <li key={i}>
              <button
                type="button"
                onClick={() => onSelect(i)}
                className={`group flex items-center gap-2 rounded-md px-3 py-2 font-mono text-[11px] uppercase tracking-[0.08em] transition-all ${
                  isActive
                    ? "bg-cyan-400/10 ring-1 ring-cyan-400/45 text-white"
                    : isPast
                      ? "text-zinc-500 hover:text-cyan-300"
                      : "text-zinc-400 hover:text-cyan-300"
                }`}
                style={
                  isActive ? { boxShadow: "0 0 16px rgba(34,211,238,0.18)" } : undefined
                }
              >
                <span className="text-zinc-500 tabular-nums">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <span
                  className="h-1.5 w-1.5 rounded-full"
                  style={{
                    background: color,
                    boxShadow: isActive ? `0 0 6px ${color}` : undefined,
                  }}
                />
                <span>{label}</span>
                {round !== undefined && (
                  <span className="rounded bg-black/40 px-1 text-[9px] text-cyan-300">
                    R{round}
                  </span>
                )}
              </button>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function NavControls({
  activeIdx,
  total,
  onPrev,
  onNext,
}: {
  activeIdx: number;
  total: number;
  onPrev: () => void;
  onNext: () => void;
}) {
  const atStart = activeIdx === 0;
  const atEnd = activeIdx === total - 1;
  return (
    <div className="mt-4 flex items-center justify-between gap-3">
      <button
        type="button"
        onClick={onPrev}
        disabled={atStart}
        className={`inline-flex items-center gap-2 rounded-md border border-cyan-400/25 px-4 py-2 font-mono text-[11px] uppercase tracking-[0.12em] transition-all ${
          atStart
            ? "opacity-30 cursor-not-allowed text-zinc-500"
            : "text-cyan-200 hover:bg-cyan-400/10 hover:border-cyan-400/50"
        }`}
      >
        <svg width="12" height="12" viewBox="0 0 14 14" fill="none" aria-hidden>
          <path
            d="M11 7H3m0 0l3.5-3.5M3 7l3.5 3.5"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        Prev
      </button>
      <p className="font-mono text-xs text-zinc-500 tabular-nums">
        <span className="text-cyan-300">{String(activeIdx + 1).padStart(2, "0")}</span>{" "}
        <span className="text-zinc-700">/</span> {String(total).padStart(2, "0")}
      </p>
      <button
        type="button"
        onClick={onNext}
        disabled={atEnd}
        className={`inline-flex items-center gap-2 rounded-md border px-4 py-2 font-mono text-[11px] uppercase tracking-[0.12em] transition-all ${
          atEnd
            ? "opacity-30 cursor-not-allowed text-zinc-500 border-cyan-400/25"
            : "bg-cyan-400/10 border-cyan-400/40 text-cyan-100 hover:bg-cyan-400/20 hover:border-cyan-400"
        }`}
      >
        Next
        <svg width="12" height="12" viewBox="0 0 14 14" fill="none" aria-hidden>
          <path
            d="M3 7h8m0 0L7.5 3.5M11 7l-3.5 3.5"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>
    </div>
  );
}
