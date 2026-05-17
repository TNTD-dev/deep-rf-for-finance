"use client";

import { DecisionPanel } from "@/components/DecisionPanel";
import { RoleBadge } from "@/components/RoleBadge";
import type { DebateEntry as Entry } from "@/lib/types";

interface Props {
  entry: Entry;
  round?: number;
}

function fmtTime(iso: string | undefined | null): string {
  if (!iso) return "";
  // Trim "YYYY-MM-DDTHH:MM:SS" → "HH:MM:SS"
  return iso.slice(11, 19);
}

export function DebateEntry({ entry, round }: Props) {
  const hasDecision = entry.decision !== undefined;
  const hasContent = !!entry.content && entry.content.trim().length > 0;

  return (
    <article className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <header className="flex flex-wrap items-center gap-3">
        <RoleBadge role={entry.role} round={round} />
        {entry.model && (
          <span className="text-xs text-gray-500">{String(entry.model)}</span>
        )}
        <span className="text-xs text-gray-400">{fmtTime(entry.ts)}</span>
      </header>
      <div className="mt-3">
        {hasDecision && !hasContent ? (
          <DecisionPanel decision={entry.decision!} />
        ) : (
          <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-gray-800">
            {entry.content}
          </pre>
        )}
        {hasDecision && hasContent && (
          <div className="mt-4 border-t pt-3">
            <DecisionPanel decision={entry.decision!} />
          </div>
        )}
      </div>
    </article>
  );
}
