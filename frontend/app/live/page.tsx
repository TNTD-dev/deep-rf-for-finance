"use client";

import { useEffect, useRef, useState } from "react";

import { LiveFlow } from "@/components/LiveFlow";
import { RunButton } from "@/components/RunButton";
import { ScrollFade } from "@/components/ScrollFade";
import { SSEStream } from "@/components/SSEStream";
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
    <main className="container mx-auto max-w-5xl px-6 pt-10 pb-16 space-y-8">
      <ScrollFade>
        <header className="space-y-3">
          <Kicker>Live · multi-agent</Kicker>
          <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight text-white">
            Watch 8 roles deliberate
          </h1>
          <p className="text-sm text-zinc-400 max-w-2xl">
            Click run. The multi-agent system streams{" "}
            <code className="rounded bg-cyan-400/10 px-1.5 py-0.5 font-mono text-[11px] text-cyan-300">
              agent_start
            </code>
            ,{" "}
            <code className="rounded bg-cyan-400/10 px-1.5 py-0.5 font-mono text-[11px] text-cyan-300">
              agent_complete
            </code>
            , and{" "}
            <code className="rounded bg-cyan-400/10 px-1.5 py-0.5 font-mono text-[11px] text-cyan-300">
              decision
            </code>{" "}
            events via SSE — 8 role cards light up sequentially, then the
            portfolio_manager emits final weights.
          </p>
        </header>
      </ScrollFade>

      <ScrollFade delayMs={80}>
        <GlassPanel glow="soft">
          <div className="p-6 space-y-3">
            <Kicker>Controls</Kicker>
            <RunButton state={state} onClick={start} />
            <p className="text-xs text-zinc-500 font-mono">
              ≈{" "}
              <span className="font-semibold text-cyan-300">$0.05</span> per run
              (real OpenAI call) · 60s timeout · 8 roles fire sequentially
            </p>
          </div>
        </GlassPanel>
      </ScrollFade>

      <ScrollFade delayMs={140}>
        <GlassPanel>
          <div className="p-6">
            <Kicker>Pipeline · 8 roles</Kicker>
            <div className="mt-5">
              <LiveFlow events={events} />
            </div>
          </div>
        </GlassPanel>
      </ScrollFade>

      <ScrollFade delayMs={200}>
        <GlassPanel>
          <div className="p-6">
            <Kicker>Event log</Kicker>
            <div className="mt-4">
              <SSEStream events={events} />
            </div>
          </div>
        </GlassPanel>
      </ScrollFade>
    </main>
  );
}
