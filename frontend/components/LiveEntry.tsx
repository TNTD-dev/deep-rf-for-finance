"use client";

import { DecisionPanel } from "@/components/DecisionPanel";
import { RoleBadge } from "@/components/RoleBadge";
import { TranscriptContent } from "@/components/TranscriptContent";
import type { LiveEvent } from "@/lib/types";

interface Props {
  event: LiveEvent;
}

export function LiveEntry({ event }: Props) {
  switch (event.type) {
    case "agent_start":
      return (
        <article className="rounded-md border border-cyan-400/20 bg-cyan-400/5 backdrop-blur-sm p-4">
          <header className="flex items-center gap-3">
            <RoleBadge role={event.role} />
            <span className="font-mono text-[11px] uppercase tracking-[0.08em] text-cyan-300/80">
              starting…
            </span>
            <span className="ml-auto h-2 w-2 animate-pulse rounded-full bg-cyan-400 shadow-[0_0_8px_rgba(34,211,238,0.8)]" />
          </header>
        </article>
      );
    case "agent_complete":
      return (
        <article className="rounded-md border border-cyan-400/15 bg-black/40 backdrop-blur-sm p-4">
          <header className="flex items-center gap-3">
            <RoleBadge role={event.role} />
            <span className="font-mono text-[11px] uppercase tracking-[0.08em] text-zinc-500">
              done
            </span>
          </header>
          <div className="mt-3">
            <TranscriptContent content={event.summary} />
          </div>
        </article>
      );
    case "decision":
      return (
        <article className="rounded-md border-2 border-cyan-400/50 bg-cyan-400/8 backdrop-blur-sm p-5 glow-cyan">
          <header className="mb-3 flex items-center gap-3">
            <RoleBadge role="portfolio_manager" />
            <span className="font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-cyan-200">
              Final decision
            </span>
          </header>
          <DecisionPanel decision={event.weights} />
          {event.rationale && (
            <details className="mt-3 text-xs text-zinc-400">
              <summary className="cursor-pointer font-mono uppercase tracking-[0.08em] text-cyan-300/80 hover:text-cyan-200">
                Rationale
              </summary>
              <pre className="mt-2 whitespace-pre-wrap rounded bg-black/50 border border-cyan-400/15 p-3 text-zinc-300">
                {event.rationale}
              </pre>
            </details>
          )}
        </article>
      );
    case "error":
      return (
        <article className="rounded-md border border-rose-400/40 bg-rose-500/10 backdrop-blur-sm p-4">
          <p className="font-mono text-sm font-semibold text-rose-300">
            ⚠ {event.message}
          </p>
        </article>
      );
  }
}
