"use client";

import { useEffect, useRef, useState } from "react";

import { RunButton } from "@/components/RunButton";
import { SSEStream } from "@/components/SSEStream";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
    <main className="container mx-auto max-w-5xl space-y-6 px-4 py-6">
      <header className="border-b border-gray-200 pb-4">
        <h1 className="text-2xl font-bold tracking-tight">Live Multi-Agent Run</h1>
        <p className="mt-1 text-sm text-gray-600">
          Triggers a real multi-agent decision against the latest available
          market data. Streams per-role progress until the portfolio_manager
          emits final weights.
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold text-gray-700">Controls</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <RunButton state={state} onClick={start} />
          <p className="text-xs text-gray-500">
            ≈ <span className="font-medium">$0.05</span> per run (real OpenAI
            call). 60s timeout. 8 roles fire sequentially.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold text-gray-700">
            Event Stream
          </CardTitle>
        </CardHeader>
        <CardContent>
          <SSEStream events={events} />
        </CardContent>
      </Card>
    </main>
  );
}
