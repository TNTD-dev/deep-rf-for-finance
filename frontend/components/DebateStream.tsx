"use client";

import { DebateEntry } from "@/components/DebateEntry";
import type { DebateTranscript } from "@/lib/types";

interface Props {
  transcript: DebateTranscript;
}

// Walk the transcript; for each bull/bear pair, assign a 1-based round
// number. Non-debate roles → undefined. Helper kept outside the component
// so the mutable accumulator (round counter) isn't flagged by
// react-hooks/immutability.
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
      out[i] = round; // mirror the round number from the preceding bull
    }
  }
  return out;
}

export function DebateStream({ transcript }: Props) {
  const rounds = assignDebateRounds(transcript.transcript);
  return (
    <div className="space-y-3">
      {transcript.transcript.map((entry, i) => (
        <DebateEntry key={i} entry={entry} round={rounds[i]} />
      ))}
    </div>
  );
}
