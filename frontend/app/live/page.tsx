"use client";

import { useEffect, useRef, useState } from "react";

import { LiveFlow } from "@/components/LiveFlow";
import { LiveSidecar } from "@/components/LiveSidecar";
import { RunButton } from "@/components/RunButton";
import { ScrollFade } from "@/components/ScrollFade";
import { GlassPanel, Kicker } from "@/components/ui/glass";
import { streamLive } from "@/lib/sse";
import type { LiveEvent } from "@/lib/types";

type LiveState = "idle" | "streaming" | "done" | "error";

export default function LivePage() {
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [state, setState] = useState<LiveState>("idle");
  const esRef = useRef<EventSource | null>(null);

  // Cleanup on unmount — if user navigates away mid-stream, close
  // EventSource so backend's is_disconnected() fires and the LLM stops.
  useEffect(() => {
    return () => {
      esRef.current?.close();
    };
  }, []);

  const start = () => {
    setEvents([]);
    setState("streaming");
    esRef.current = streamLive({
      onEvent: (ev) => {
        setEvents((prev) => [...prev, ev]);
        if (ev.type === "error") setState("error");
      },
      onClose: () => {
        // Only flip to "done" if we didn't already go to "error".
        setState((s) => (s === "streaming" ? "done" : s));
      },
    });
  };

  return (
    <main className="container mx-auto max-w-7xl px-6 pt-8 pb-16 space-y-6">
      {/* Header band — title left, run button right (always reachable). */}
      <ScrollFade>
        <header className="flex flex-wrap items-end justify-between gap-4">
          <div className="space-y-2">
            <Kicker>Live · multi-agent</Kicker>
            <h1
              className="text-3xl sm:text-4xl font-bold tracking-tight text-white"
              style={{ fontFamily: "var(--font-grotesk)" }}
            >
              Watch 8 roles deliberate
            </h1>
            <p className="text-xs text-zinc-500 font-mono max-w-xl">
              SSE stream · ≈ $0.05 per run · 60s timeout · 8 roles fire sequentially
            </p>
          </div>
          <div className="flex flex-col items-end gap-2">
            <RunButton state={state} onClick={start} />
            <p className="font-mono text-[10px] text-zinc-500 uppercase tracking-[0.12em]">
              real OpenAI call
            </p>
          </div>
        </header>
      </ScrollFade>

      {/* Split-pane: pipeline canvas on the left, status sidecar on the right.
          minmax(0,1fr) so the left col can shrink below its intrinsic width
          (otherwise the SVG pushes the grid past the container). */}
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_28rem]">
        <div className="space-y-5">
          <ScrollFade>
            <GlassPanel>
              <div className="p-6">
                <Kicker>Pipeline · 8 roles</Kicker>
                <div className="mt-5">
                  <LiveFlow events={events} />
                </div>
              </div>
            </GlassPanel>
          </ScrollFade>
        </div>

        <LiveSidecar events={events} state={state} />
      </div>
    </main>
  );
}
