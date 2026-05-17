"use client";

import { DecisionPanel } from "@/components/DecisionPanel";
import { RoleBadge } from "@/components/RoleBadge";
import type { LiveEvent } from "@/lib/types";

interface Props {
  event: LiveEvent;
}

export function LiveEntry({ event }: Props) {
  switch (event.type) {
    case "agent_start":
      return (
        <article className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
          <header className="flex items-center gap-3">
            <RoleBadge role={event.role} />
            <span className="text-xs text-gray-500">starting…</span>
            <span className="ml-auto h-2 w-2 animate-pulse rounded-full bg-blue-500" />
          </header>
        </article>
      );
    case "agent_complete":
      return (
        <article className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
          <header className="flex items-center gap-3">
            <RoleBadge role={event.role} />
            <span className="text-xs text-gray-500">done</span>
          </header>
          <pre className="mt-3 whitespace-pre-wrap font-sans text-sm leading-relaxed text-gray-800">
            {event.summary}
          </pre>
        </article>
      );
    case "decision":
      return (
        <article className="rounded-lg border-2 border-violet-300 bg-violet-50 p-4 shadow-sm">
          <header className="mb-3 flex items-center gap-3">
            <RoleBadge role="portfolio_manager" />
            <span className="text-xs font-semibold text-violet-700">FINAL DECISION</span>
          </header>
          <DecisionPanel decision={event.weights} />
          {event.rationale && (
            <details className="mt-3 text-xs text-gray-600">
              <summary className="cursor-pointer">Rationale</summary>
              <pre className="mt-1 whitespace-pre-wrap rounded bg-white/60 p-2">
                {event.rationale}
              </pre>
            </details>
          )}
        </article>
      );
    case "error":
      return (
        <article className="rounded-lg border border-red-200 bg-red-50 p-4 shadow-sm">
          <p className="text-sm font-semibold text-red-700">⚠ {event.message}</p>
        </article>
      );
  }
}
