"use client";

/**
 * DebateGraph — node-graph visualization of one multi-agent decision.
 *
 * Layout: 3 columns (analysts → debate → execution) with the portfolio
 * manager as the terminal node. Connection lines show information flow.
 * Clicking a node scrolls to / highlights the matching transcript entry.
 *
 * The transcript prop is the same DebateTranscript the existing list view
 * consumes — the graph is a *navigation overlay*, the existing entries below
 * are still the source of truth for content. This keeps each component
 * single-purpose: graph = topology, list = text.
 */

import { useEffect, useState } from "react";

import { roleColor } from "@/lib/colors";
import type { DebateTranscript } from "@/lib/types";

type NodeDef = {
  role: string;
  x: number;
  y: number;
  label: string;
};

// Layout — 6 columns × 4 rows of "slots", 8 nodes placed by hand.
const NODES: NodeDef[] = [
  { role: "technical_analyst", x: 80, y: 80, label: "Technical" },
  { role: "news_sentiment_analyst", x: 80, y: 200, label: "News" },
  { role: "fundamental_analyst", x: 80, y: 320, label: "Fundamental" },
  { role: "bullish_researcher", x: 280, y: 140, label: "Bull" },
  { role: "bearish_researcher", x: 280, y: 260, label: "Bear" },
  { role: "trader", x: 480, y: 200, label: "Trader" },
  { role: "risk_manager", x: 660, y: 200, label: "Risk" },
  { role: "portfolio_manager", x: 840, y: 200, label: "Portfolio" },
];

// Edges encode the actual LangGraph topology (PKG-8 src/llm/multi_agent/graph.py).
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

const NODE_R = 36;
const VIEWBOX_W = 920;
const VIEWBOX_H = 400;

export function DebateGraph({
  transcript,
  activeRole,
  onSelect,
}: {
  transcript: DebateTranscript;
  activeRole: string | null;
  onSelect: (role: string) => void;
}) {
  // Which roles actually fired in this transcript (some smoke runs may skip).
  const present = new Set(transcript.transcript.map((e) => e.role));

  // Auto-play visit order so on first mount the eye walks through the graph.
  const [visited, setVisited] = useState<Set<string>>(new Set());
  useEffect(() => {
    const seq = NODES.map((n) => n.role);
    let i = 0;
    const id = window.setInterval(() => {
      if (i >= seq.length) {
        window.clearInterval(id);
        return;
      }
      const r = seq[i++];
      setVisited((prev) => new Set(prev).add(r));
    }, 220);
    return () => window.clearInterval(id);
  }, [transcript.date]);

  const nodeFor = (role: string) => NODES.find((n) => n.role === role);

  return (
    <div className="relative w-full overflow-x-auto">
      <svg
        viewBox={`0 0 ${VIEWBOX_W} ${VIEWBOX_H}`}
        className="w-full min-w-[820px] h-auto"
      >
        <defs>
          <marker
            id="arrow"
            viewBox="0 0 10 10"
            refX="8"
            refY="5"
            markerWidth="6"
            markerHeight="6"
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" fill="rgba(34,211,238,0.5)" />
          </marker>
          <filter id="node-glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="3" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Column dividers (decorative) */}
        {[180, 380, 580, 760].map((x) => (
          <line
            key={x}
            x1={x}
            y1={20}
            x2={x}
            y2={VIEWBOX_H - 40}
            stroke="rgba(34,211,238,0.06)"
            strokeWidth="1"
            strokeDasharray="2 6"
          />
        ))}

        {/* Column labels */}
        {[
          { x: 80, label: "Analysts" },
          { x: 280, label: "Debate" },
          { x: 480, label: "Trader" },
          { x: 660, label: "Risk" },
          { x: 840, label: "Decision" },
        ].map((c) => (
          <text
            key={c.x}
            x={c.x}
            y={VIEWBOX_H - 12}
            textAnchor="middle"
            fontSize="10"
            fontFamily="var(--font-jbm)"
            fill="rgba(34,211,238,0.6)"
            letterSpacing="2"
          >
            {c.label.toUpperCase()}
          </text>
        ))}

        {/* Edges */}
        {EDGES.map(([from, to], i) => {
          const a = nodeFor(from);
          const b = nodeFor(to);
          if (!a || !b) return null;
          const active = visited.has(to);
          return (
            <line
              key={i}
              x1={a.x + NODE_R - 2}
              y1={a.y}
              x2={b.x - NODE_R + 2}
              y2={b.y}
              stroke={active ? "rgba(34,211,238,0.55)" : "rgba(34,211,238,0.15)"}
              strokeWidth={active ? 1.4 : 1}
              markerEnd="url(#arrow)"
              style={{ transition: "stroke 600ms ease, stroke-width 600ms ease" }}
            />
          );
        })}

        {/* Nodes */}
        {NODES.map((n) => {
          const color = roleColor(n.role);
          const isPresent = present.has(n.role);
          const isActive = activeRole === n.role;
          const isVisited = visited.has(n.role);
          const opacity = isPresent ? 1 : 0.35;
          return (
            <g
              key={n.role}
              transform={`translate(${n.x}, ${n.y})`}
              style={{
                cursor: isPresent ? "pointer" : "default",
                opacity,
                transition: "opacity 600ms ease",
              }}
              onClick={() => isPresent && onSelect(n.role)}
            >
              {/* Halo on active / pulsing on hover */}
              {(isActive || isVisited) && (
                <circle
                  r={NODE_R + 6}
                  fill="none"
                  stroke={color}
                  strokeOpacity={isActive ? 0.7 : 0.3}
                  strokeWidth={isActive ? 2 : 1}
                />
              )}
              <circle
                r={NODE_R}
                fill="rgba(8,10,12,0.85)"
                stroke={color}
                strokeWidth={isActive ? 2.2 : 1.4}
                filter={isActive ? "url(#node-glow)" : undefined}
                style={{
                  transition:
                    "stroke-width 200ms ease, filter 200ms ease",
                }}
              />
              <circle r={5} cx={0} cy={-NODE_R + 8} fill={color} />
              <text
                x={0}
                y={2}
                textAnchor="middle"
                fontSize="11"
                fontFamily="var(--font-jbm)"
                fill={isActive ? color : "#e4e4e7"}
                fontWeight={600}
              >
                {n.label}
              </text>
              <text
                x={0}
                y={16}
                textAnchor="middle"
                fontSize="8"
                fontFamily="var(--font-jbm)"
                fill="rgba(161,161,170,0.7)"
                letterSpacing="1"
              >
                {n.role.toUpperCase().replace("_ANALYST", "")}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
