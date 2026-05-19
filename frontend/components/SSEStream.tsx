"use client";

import { LiveEntry } from "@/components/LiveEntry";
import type { LiveEvent } from "@/lib/types";

interface Props {
  events: LiveEvent[];
}

export function SSEStream({ events }: Props) {
  if (events.length === 0) {
    return (
      <p className="font-mono text-sm text-zinc-500">
        Press <span className="text-cyan-300">Run for today</span> to start a
        live multi-agent decision. Events stream here.
      </p>
    );
  }
  return (
    <div className="space-y-3">
      {events.map((ev, i) => (
        <LiveEntry key={i} event={ev} />
      ))}
    </div>
  );
}
