"use client";

/**
 * LiveSidecar — sticky sidebar that pairs with the LiveFlow canvas.
 *
 * Layout (sticky on lg, stacked on mobile):
 *   ┌─ STATUS header (state pill + step counter)
 *   ├─ DECISION card (pinned when present, full DecisionPanel)
 *   ├─ NOW PLAYING (latest agent_complete summary)
 *   └─ EVENT LOG (reverse-chronological list, scrollable)
 *
 * Pure projection from the events[] stream — no state of its own. Stateless
 * is intentional so re-renders on every new event are cheap; we just
 * recompute the latest events on each pass.
 */

import { DecisionPanel } from "@/components/DecisionPanel";
import { RoleBadge } from "@/components/RoleBadge";
import { TranscriptContent } from "@/components/TranscriptContent";
import type { LiveEvent } from "@/lib/types";

type StreamState = "idle" | "streaming" | "done" | "error";

const ROLE_LABEL: Record<string, string> = {
  technical_analyst: "Technical analyst",
  news_sentiment_analyst: "News sentiment",
  fundamental_analyst: "Fundamental analyst",
  bullish_researcher: "Bull researcher",
  bearish_researcher: "Bear researcher",
  trader: "Trader",
  risk_manager: "Risk manager",
  portfolio_manager: "Portfolio manager",
};

export function LiveSidecar({
  events,
  state,
}: {
  events: LiveEvent[];
  state: StreamState;
}) {
  const decision = events.find(
    (e): e is Extract<LiveEvent, { type: "decision" }> => e.type === "decision",
  );
  const errorEv = events.find(
    (e): e is Extract<LiveEvent, { type: "error" }> => e.type === "error",
  );
  const completes = events.filter(
    (e): e is Extract<LiveEvent, { type: "agent_complete" }> =>
      e.type === "agent_complete",
  );
  const latestComplete = completes[completes.length - 1];
  const totalSteps = 8; // 8 roles total in the pipeline
  const stepsDone = completes.length;

  return (
    <aside className="sidecar">
      <div className="glass-shell h-full">
        <div className="glass-inner h-full flex flex-col">
          {/* STATUS HEADER */}
          <div className="border-b border-cyan-400/15 px-5 py-4 shrink-0">
            <div className="flex items-center justify-between gap-3">
              <StatusPill state={state} />
              <p className="font-mono text-xs text-zinc-500 tabular-nums">
                <span className="text-cyan-300">
                  {String(stepsDone).padStart(2, "0")}
                </span>{" "}
                <span className="text-zinc-700">/</span>{" "}
                {String(totalSteps).padStart(2, "0")} roles
              </p>
            </div>
            <Progress done={stepsDone} total={totalSteps} state={state} />
          </div>

          {/* SCROLLABLE BODY */}
          <div className="sidecar-scroll px-5 py-5 space-y-5">
            {decision && (
              <section>
                <p className="label-mono mb-3">Final decision</p>
                <div
                  className="rounded-md border-2 border-cyan-400/45 bg-cyan-400/8 p-4 glow-cyan"
                  key={`dec-${decision.weights ? Object.keys(decision.weights).join("") : ""}`}
                >
                  <DecisionPanel decision={decision.weights} />
                </div>
              </section>
            )}

            {!decision && latestComplete && (
              <section>
                <div className="flex items-center justify-between gap-2 mb-3">
                  <p className="label-mono">Now playing</p>
                  <p className="font-mono text-[10px] uppercase tracking-[0.1em] text-cyan-300/70">
                    {ROLE_LABEL[latestComplete.role] ?? latestComplete.role}
                  </p>
                </div>
                <div
                  className="rounded-md border border-cyan-400/25 bg-black/40 p-4"
                  key={`now-${latestComplete.role}-${stepsDone}`}
                >
                  <RoleBadge role={latestComplete.role} />
                  <div className="mt-3">
                    <TranscriptContent content={latestComplete.summary} />
                  </div>
                </div>
              </section>
            )}

            {errorEv && (
              <section className="rounded-md border border-rose-400/40 bg-rose-500/10 p-4">
                <p className="font-mono text-sm font-semibold text-rose-300">
                  ⚠ {errorEv.message}
                </p>
              </section>
            )}

            {!decision && !latestComplete && !errorEv && (
              <EmptyState state={state} />
            )}

            <section>
              <p className="label-mono mb-3">Event log · newest first</p>
              <EventLog events={events} />
            </section>
          </div>
        </div>
      </div>
    </aside>
  );
}

/* ───────────────────────── pieces ──────────────────────────────────────── */

function StatusPill({ state }: { state: StreamState }) {
  const cfg: Record<StreamState, { label: string; cls: string; dot: string }> = {
    idle: {
      label: "Idle",
      cls: "bg-zinc-500/15 ring-zinc-500/30 text-zinc-300",
      dot: "bg-zinc-400",
    },
    streaming: {
      label: "Streaming",
      cls: "bg-cyan-400/15 ring-cyan-400/45 text-cyan-100 glow-cyan",
      dot: "bg-cyan-300 animate-pulse",
    },
    done: {
      label: "Done",
      cls: "bg-cyan-400/20 ring-cyan-400/55 text-cyan-100",
      dot: "bg-cyan-300",
    },
    error: {
      label: "Error",
      cls: "bg-rose-500/15 ring-rose-400/55 text-rose-200",
      dot: "bg-rose-400",
    },
  };
  const c = cfg[state];
  return (
    <span
      className={`inline-flex items-center gap-2 rounded-md px-2.5 py-1 font-mono text-[10px] font-semibold uppercase tracking-[0.14em] ring-1 ${c.cls}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${c.dot}`} />
      {c.label}
    </span>
  );
}

function Progress({
  done,
  total,
  state,
}: {
  done: number;
  total: number;
  state: StreamState;
}) {
  const pct = Math.min(100, Math.round((done / total) * 100));
  return (
    <div className="mt-3 h-1 w-full overflow-hidden rounded bg-cyan-400/10">
      <div
        className={`h-full transition-all duration-500 ${
          state === "error"
            ? "bg-rose-400/80"
            : "bg-gradient-to-r from-cyan-400 to-cyan-300"
        }`}
        style={{
          width: `${pct}%`,
          boxShadow: state === "streaming" ? "0 0 8px #22d3ee" : undefined,
        }}
      />
    </div>
  );
}

function EmptyState({ state }: { state: StreamState }) {
  return (
    <div className="rounded-md border border-cyan-400/15 bg-black/30 px-4 py-8 text-center">
      <p className="font-mono text-sm text-zinc-400">
        {state === "idle"
          ? "Press Run to start a live multi-agent decision."
          : "Waiting for events…"}
      </p>
      <p className="mt-2 font-mono text-[11px] text-zinc-500">
        Events stream here as roles fire.
      </p>
    </div>
  );
}

function EventLog({ events }: { events: LiveEvent[] }) {
  if (events.length === 0) {
    return (
      <p className="font-mono text-xs text-zinc-500">
        No events yet.
      </p>
    );
  }
  // Reverse so newest sits on top — natural for live trading dashboards.
  const reversed = [...events].reverse();
  return (
    <ol className="space-y-1.5">
      {reversed.map((ev, i) => (
        <li
          key={events.length - i}
          className="flex items-center gap-3 rounded border border-cyan-400/10 bg-black/30 px-3 py-2 font-mono text-[11px]"
        >
          <span className="text-zinc-600 tabular-nums shrink-0 w-6 text-right">
            {String(events.length - i).padStart(2, "0")}
          </span>
          <EventBadge ev={ev} />
        </li>
      ))}
    </ol>
  );
}

function EventBadge({ ev }: { ev: LiveEvent }) {
  switch (ev.type) {
    case "agent_start":
      return (
        <span className="flex items-center gap-2 flex-1 min-w-0">
          <span className="rounded bg-cyan-400/10 px-1.5 py-0.5 text-cyan-300 uppercase tracking-[0.08em] text-[9px]">
            START
          </span>
          <span className="text-zinc-300 truncate">{ev.role}</span>
        </span>
      );
    case "agent_complete":
      return (
        <span className="flex items-center gap-2 flex-1 min-w-0">
          <span className="rounded bg-cyan-400/20 px-1.5 py-0.5 text-cyan-200 uppercase tracking-[0.08em] text-[9px]">
            DONE
          </span>
          <span className="text-zinc-100 truncate">{ev.role}</span>
        </span>
      );
    case "decision":
      return (
        <span className="flex items-center gap-2 flex-1 min-w-0">
          <span className="rounded bg-cyan-400 px-1.5 py-0.5 text-black font-bold uppercase tracking-[0.08em] text-[9px]">
            FINAL
          </span>
          <span className="text-cyan-200">portfolio decision</span>
        </span>
      );
    case "error":
      return (
        <span className="flex items-center gap-2 flex-1 min-w-0">
          <span className="rounded bg-rose-500/30 px-1.5 py-0.5 text-rose-200 uppercase tracking-[0.08em] text-[9px]">
            ERROR
          </span>
          <span className="text-rose-300 truncate">{ev.message}</span>
        </span>
      );
  }
}
