"use client";

import { LiveEntry } from "@/components/LiveEntry";
import type { LiveEvent } from "@/lib/types";

interface Props {
  events: LiveEvent[];
}

export function SSEStream({ events }: Props) {
  if (events.length === 0) {
    return (
      <p className="text-sm text-gray-500">
        Press &quot;Run for today&quot; to start a live multi-agent decision.
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
