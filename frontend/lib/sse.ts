// PKG-16 SSE client wrapper.
//
// EventSource is GET-only (web API constraint). PKG-12 ships
// `GET /live/run` (added in PKG-16) alongside POST for this reason.
//
// Returns the underlying EventSource so the caller can `.close()` on
// unmount. We auto-close on terminal events (decision OR error) so
// EventSource's built-in auto-reconnect doesn't re-trigger an LLM run
// (= $0.05 per click).

import { BACKEND_URL } from "@/lib/api";
import type { LiveEvent } from "@/lib/types";

interface Handlers {
  onEvent: (event: LiveEvent) => void;
  onClose: () => void; // fires after decision OR error OR network drop
}

export function streamLive(handlers: Handlers): EventSource {
  const es = new EventSource(`${BACKEND_URL}/live/run`);

  const safeClose = () => {
    es.close();
    handlers.onClose();
  };

  es.addEventListener("agent_start", (e) => {
    const data = JSON.parse((e as MessageEvent).data) as { role: string };
    handlers.onEvent({ type: "agent_start", role: data.role });
  });

  es.addEventListener("agent_complete", (e) => {
    const data = JSON.parse((e as MessageEvent).data) as {
      role: string;
      summary: string;
    };
    handlers.onEvent({
      type: "agent_complete",
      role: data.role,
      summary: data.summary,
    });
  });

  es.addEventListener("decision", (e) => {
    const data = JSON.parse((e as MessageEvent).data) as {
      weights: Record<string, number>;
      rationale: string;
    };
    handlers.onEvent({
      type: "decision",
      weights: data.weights,
      rationale: data.rationale,
    });
    safeClose();
  });

  // EventSource's built-in "error" event fires for BOTH:
  //   - app-level errors (backend emits `event: error data: {...}`)
  //   - transport errors (network drop, server gone). MessageEvent.data
  //     presence distinguishes — app errors carry data; transport doesn't.
  es.addEventListener("error", (e) => {
    if (e instanceof MessageEvent && e.data) {
      try {
        const data = JSON.parse(e.data) as { message: string };
        handlers.onEvent({ type: "error", message: data.message });
      } catch {
        handlers.onEvent({ type: "error", message: "Malformed error event" });
      }
    } else {
      handlers.onEvent({
        type: "error",
        message:
          es.readyState === EventSource.CLOSED ? "Connection closed" : "Network error",
      });
    }
    safeClose();
  });

  return es;
}
