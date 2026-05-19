"use client";

import { DecisionPanel } from "@/components/DecisionPanel";
import { RoleBadge } from "@/components/RoleBadge";
import { TranscriptContent } from "@/components/TranscriptContent";
import type { DebateEntry as Entry } from "@/lib/types";

interface Props {
  entry: Entry;
  round?: number;
  /** Highlight this entry — the parent's DebateGraph just selected it. */
  active?: boolean;
}

function fmtTime(iso: string | undefined | null): string {
  if (!iso) return "";
  // Trim "YYYY-MM-DDTHH:MM:SS" → "HH:MM:SS"
  return iso.slice(11, 19);
}

export function DebateEntry({ entry, round, active }: Props) {
  const hasDecision = entry.decision !== undefined;
  const hasContent = !!entry.content && entry.content.trim().length > 0;

  return (
    <article
      data-role={entry.role}
      className={`rounded-md border bg-black/40 backdrop-blur-sm p-4 transition-all ${
        active
          ? "border-cyan-400/70 ring-1 ring-cyan-400/30 glow-cyan"
          : "border-cyan-400/15 hover:border-cyan-400/30"
      }`}
    >
      <header className="flex flex-wrap items-center gap-3">
        <RoleBadge role={entry.role} round={round} />
        {entry.model && (
          <span className="font-mono text-[11px] text-zinc-500">
            {String(entry.model)}
          </span>
        )}
        <span className="font-mono text-[11px] text-zinc-600">
          {fmtTime(entry.ts)}
        </span>
      </header>
      <div className="mt-4">
        {hasDecision && !hasContent ? (
          <DecisionPanel decision={entry.decision!} />
        ) : (
          <TranscriptContent content={entry.content} />
        )}
        {hasDecision && hasContent && (
          <div className="mt-5 border-t border-cyan-400/10 pt-4">
            <DecisionPanel decision={entry.decision!} />
          </div>
        )}
      </div>
    </article>
  );
}
