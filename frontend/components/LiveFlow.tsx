"use client";

/**
 * LiveFlow — real-time flow chart for the /live page.
 *
 * 8 role nodes laid out as a DAG (matches the LangGraph topology in PKG-8 +
 * DebateGraph). As SSE events arrive from the backend, each node transitions
 * through: idle → pending (started, not yet complete) → done. The arrow into
 * the portfolio_manager node carries the final decision badge.
 *
 * Source of truth for status is the events[] array — the parent passes the
 * full stream of LiveEvent items in order, and this component projects them
 * onto the graph. Stateless w.r.t. its own animation: re-deriving on every
 * render is cheap (8 nodes).
 */

import { roleColor } from "@/lib/colors";
import type { LiveEvent } from "@/lib/types";

type NodeDef = {
  role: string;
  x: number;
  y: number;
  label: string;
};

const NODES: NodeDef[] = [
  { role: "technical_analyst", x: 90, y: 70, label: "Technical" },
  { role: "news_sentiment_analyst", x: 90, y: 200, label: "News" },
  { role: "fundamental_analyst", x: 90, y: 330, label: "Fundamental" },
  { role: "bullish_researcher", x: 290, y: 130, label: "Bull" },
  { role: "bearish_researcher", x: 290, y: 270, label: "Bear" },
  { role: "trader", x: 490, y: 200, label: "Trader" },
  { role: "risk_manager", x: 670, y: 200, label: "Risk" },
  { role: "portfolio_manager", x: 850, y: 200, label: "Portfolio" },
];

const EDGES: [string, string][] = [
  ["technical_analyst", "bullish_researcher"],
  ["technical_analyst", "bearish_researcher"],
  ["news_sentiment_analyst", "bullish_researcher"],
  ["news_sentiment_analyst", "bearish_researcher"],
  ["fundamental_analyst", "bullish_researcher"],
  ["fundamental_analyst", "bearish_researcher"],
  ["bullish_researcher", "trader"],
  ["bearish_researcher", "trader"],
  ["trader", "risk_manager"],
  ["risk_manager", "portfolio_manager"],
];

const NODE_R = 38;
const VIEWBOX_W = 940;
const VIEWBOX_H = 420;

type NodeStatus = "idle" | "pending" | "done";

function statusFor(role: string, events: LiveEvent[]): NodeStatus {
  let s: NodeStatus = "idle";
  for (const ev of events) {
    if (ev.type === "agent_start" && ev.role === role) s = "pending";
    else if (ev.type === "agent_complete" && ev.role === role) s = "done";
  }
  return s;
}

export function LiveFlow({ events }: { events: LiveEvent[] }) {
  const decision = events.find((e) => e.type === "decision");
  const errored = events.find((e) => e.type === "error");
  const nodeFor = (role: string) => NODES.find((n) => n.role === role);

  return (
    <div className="relative w-full overflow-x-auto">
      <svg
        viewBox={`0 0 ${VIEWBOX_W} ${VIEWBOX_H}`}
        // Scale freely with the column; min-width was forcing the grid to
        // overflow when paired with the sidecar.
        className="w-full h-auto"
      >
        <defs>
          <marker
            id="arrow-live"
            viewBox="0 0 10 10"
            refX="8"
            refY="5"
            markerWidth="6"
            markerHeight="6"
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" fill="rgba(34,211,238,0.6)" />
          </marker>
          <filter id="node-glow-live" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="4" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <linearGradient id="active-edge" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#22d3ee" stopOpacity="0.3" />
            <stop offset="50%" stopColor="#22d3ee" stopOpacity="0.95" />
            <stop offset="100%" stopColor="#22d3ee" stopOpacity="0.4" />
          </linearGradient>
        </defs>

        {/* Column dividers */}
        {[190, 390, 590, 770].map((x) => (
          <line
            key={x}
            x1={x}
            y1={30}
            x2={x}
            y2={VIEWBOX_H - 40}
            stroke="rgba(34,211,238,0.06)"
            strokeWidth="1"
            strokeDasharray="2 6"
          />
        ))}

        {/* Edges */}
        {EDGES.map(([from, to], i) => {
          const a = nodeFor(from);
          const b = nodeFor(to);
          if (!a || !b) return null;
          const sFrom = statusFor(from, events);
          const sTo = statusFor(to, events);
          const lit = sFrom === "done" && sTo !== "idle";
          return (
            <line
              key={i}
              x1={a.x + NODE_R - 2}
              y1={a.y}
              x2={b.x - NODE_R + 2}
              y2={b.y}
              stroke={lit ? "url(#active-edge)" : "rgba(34,211,238,0.12)"}
              strokeWidth={lit ? 1.6 : 1}
              markerEnd="url(#arrow-live)"
              style={{ transition: "stroke 400ms ease, stroke-width 400ms ease" }}
            />
          );
        })}

        {/* Nodes */}
        {NODES.map((n) => {
          const color = roleColor(n.role);
          const status = statusFor(n.role, events);
          const isPending = status === "pending";
          const isDone = status === "done";
          const isIdle = status === "idle";
          return (
            <g key={n.role} transform={`translate(${n.x}, ${n.y})`}>
              {isPending && (
                <circle
                  className="live-pulse"
                  r={NODE_R + 10}
                  fill="none"
                  stroke={color}
                  strokeWidth={1.4}
                  strokeOpacity={0.6}
                />
              )}
              <circle
                r={NODE_R}
                fill={isDone ? `${color}1a` : "rgba(8,10,12,0.85)"}
                stroke={color}
                strokeWidth={isIdle ? 1 : 1.8}
                strokeOpacity={isIdle ? 0.35 : 1}
                filter={isPending ? "url(#node-glow-live)" : undefined}
              />
              <circle
                r={5}
                cx={0}
                cy={-NODE_R + 8}
                fill={color}
                opacity={isIdle ? 0.4 : 1}
              />
              <text
                x={0}
                y={2}
                textAnchor="middle"
                fontSize="11"
                fontWeight={600}
                fontFamily="var(--font-jbm)"
                fill={isIdle ? "rgba(228,228,231,0.4)" : "#e4e4e7"}
              >
                {n.label}
              </text>
              <text
                x={0}
                y={17}
                textAnchor="middle"
                fontSize="8"
                fontFamily="var(--font-jbm)"
                fill={isIdle ? "rgba(161,161,170,0.25)" : "rgba(34,211,238,0.7)"}
                letterSpacing="1"
              >
                {status.toUpperCase()}
              </text>
            </g>
          );
        })}

        {/* Final-decision badge near portfolio manager */}
        {decision && decision.type === "decision" && (
          <g transform={`translate(${850}, ${315})`}>
            <rect
              x={-72}
              y={-16}
              width={144}
              height={32}
              rx={6}
              fill="rgba(34,211,238,0.15)"
              stroke="#22d3ee"
              strokeWidth={1.2}
              style={{ filter: "drop-shadow(0 0 12px rgba(34,211,238,0.55))" }}
            />
            <text
              x={0}
              y={4}
              textAnchor="middle"
              fontSize="11"
              fontWeight={700}
              fontFamily="var(--font-jbm)"
              fill="#67e8f9"
              letterSpacing="1.5"
            >
              FINAL DECISION
            </text>
          </g>
        )}

        {/* Error banner */}
        {errored && errored.type === "error" && (
          <g transform={`translate(${VIEWBOX_W / 2}, 380)`}>
            <text
              textAnchor="middle"
              fontSize="11"
              fontWeight={600}
              fontFamily="var(--font-jbm)"
              fill="#f87171"
              letterSpacing="1.5"
            >
              ⚠ STREAM ERROR — see log below
            </text>
          </g>
        )}

        <style>{`
          .live-pulse {
            animation: live-pulse 1.4s ease-out infinite;
            transform-origin: center;
          }
          @keyframes live-pulse {
            0% { opacity: 0.7; transform: scale(0.85); }
            100% { opacity: 0; transform: scale(1.2); }
          }
          @media (prefers-reduced-motion: reduce) {
            .live-pulse { animation: none; opacity: 0.5; }
          }
        `}</style>
      </svg>
    </div>
  );
}
