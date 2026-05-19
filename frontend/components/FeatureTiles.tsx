"use client";

/**
 * FeatureTiles — landing "Four layers, one comparison" section.
 *
 * Each tile carries a hand-drawn SVG mini-visualization that animates on
 * hover and on scroll-into-view. The four viz are domain-specific:
 *
 *   01 RL          → ascending policy-return sparkline with a glowing tip
 *   02 LLM         → three-stage evolution (zero-shot → agentic → multi-agent)
 *   03 Live        → eight pulse dots that light up sequentially (SSE)
 *   04 Comparison  → eight horizontal bars converging on a center axis
 *
 * All SVG + CSS — no canvas, no JS animation loop, no extra dep.
 * Respects prefers-reduced-motion.
 */

import { ScrollFade } from "@/components/ScrollFade";
import { GlassPanel, Kicker } from "@/components/ui/glass";

type Feature = {
  tag: string;
  title: string;
  body: string;
  viz: React.ReactNode;
};

const FEATURES: Feature[] = [
  {
    tag: "01 · Reinforcement",
    title: "DDPG + PPO on a custom VN env",
    body: "Stable-baselines3 trained on 5 years of VN30 prices with HOSE rules baked in: ±7% price band, 100-share lots, asymmetric 0.15% / 0.25% fees. PPO is the headline RL agent at +40.29%.",
    viz: <RlViz />,
  },
  {
    tag: "02 · LLM Trading",
    title: "Zero-shot → agentic → multi-agent",
    body: "Three increasingly capable LLM patterns. Multi-agent runs an 8-role LangGraph: three analysts, a bull/bear debate, trader, risk manager, portfolio manager. Weekly cadence, replayable, cached.",
    viz: <LlmViz />,
  },
  {
    tag: "03 · Live Mode",
    title: "Watch agents reason in real time",
    body: "Click run. The multi-agent system streams agent_start / agent_complete / decision events via SSE — 8 role cards light up sequentially, ~30-60 seconds total, ~$0.05 per click.",
    viz: <LiveViz />,
  },
  {
    tag: "04 · Honest Comparison",
    title: "Same env, same fees, same window",
    body: "Every agent runs through the same gymnasium env. No lookahead — news on day D is only visible from D+1 close. Reproducible: same seed → identical trajectory.",
    viz: <CompareViz />,
  },
];

export function FeatureTiles() {
  return (
    <section className="container mx-auto max-w-7xl px-6 py-20">
      <ScrollFade>
        <Kicker>System overview</Kicker>
        <h2
          className="mt-4 text-4xl sm:text-5xl font-bold tracking-tight text-white"
          style={{ fontFamily: "var(--font-grotesk)" }}
        >
          Four layers, one comparison
        </h2>
      </ScrollFade>

      <div className="mt-12 grid gap-6 sm:grid-cols-2">
        {FEATURES.map((f, i) => (
          <ScrollFade key={f.title} delayMs={i * 80}>
            <FeatureTile feature={f} />
          </ScrollFade>
        ))}
      </div>
    </section>
  );
}

function FeatureTile({ feature }: { feature: Feature }) {
  return (
    <GlassPanel className="h-full group">
      <div className="relative overflow-hidden">
        {/* Background viz — sits behind the text at low opacity, lights up
            on hover. Each viz handles its own animation. */}
        <div className="pointer-events-none absolute inset-0 opacity-50 group-hover:opacity-100 transition-opacity duration-500">
          {feature.viz}
        </div>

        {/* Foreground: tag, title, body */}
        <div className="relative p-7 sm:p-8 min-h-[260px] flex flex-col">
          <p className="label-mono">{feature.tag}</p>
          <h3
            className="mt-3 text-xl font-bold text-white max-w-sm"
            style={{ fontFamily: "var(--font-grotesk)" }}
          >
            {feature.title}
          </h3>
          <p className="mt-4 text-sm leading-relaxed text-zinc-400 max-w-md">
            {feature.body}
          </p>
        </div>
      </div>
    </GlassPanel>
  );
}

/* ───────────────────────── 01 · RL sparkline ───────────────────────────── */

function RlViz() {
  // A zig-zag ascending line that "draws" on hover (stroke-dashoffset trick).
  // The end-point dot pulses with a cyan halo.
  return (
    <svg
      viewBox="0 0 400 260"
      preserveAspectRatio="xMaxYMid slice"
      className="absolute inset-0 w-full h-full"
      aria-hidden
    >
      <defs>
        <linearGradient id="rl-fill" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#22d3ee" stopOpacity="0.25" />
          <stop offset="100%" stopColor="#22d3ee" stopOpacity="0" />
        </linearGradient>
      </defs>
      {/* horizontal baseline at y=210 */}
      <line
        x1="40"
        y1="210"
        x2="380"
        y2="210"
        stroke="rgba(34,211,238,0.15)"
        strokeDasharray="2 4"
      />
      {/* area under curve */}
      <path
        d="M 40 200 L 80 195 L 120 180 L 160 175 L 200 145 L 240 150 L 280 110 L 320 95 L 360 60 L 360 210 L 40 210 Z"
        fill="url(#rl-fill)"
      />
      {/* main curve */}
      <path
        className="rl-curve"
        d="M 40 200 L 80 195 L 120 180 L 160 175 L 200 145 L 240 150 L 280 110 L 320 95 L 360 60"
        fill="none"
        stroke="#22d3ee"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* end-point glow */}
      <circle cx="360" cy="60" r="10" fill="rgba(34,211,238,0.25)" className="rl-pulse" />
      <circle
        cx="360"
        cy="60"
        r="3.5"
        fill="#22d3ee"
        style={{ filter: "drop-shadow(0 0 6px #22d3ee)" }}
      />
      <text
        x="358"
        y="44"
        textAnchor="end"
        fontSize="9"
        fontFamily="var(--font-jbm)"
        fill="#67e8f9"
        letterSpacing="1"
      >
        +40.29%
      </text>
      <style>{`
        .rl-curve {
          stroke-dasharray: 600;
          stroke-dashoffset: 600;
          animation: rl-draw 4s ease-out 0.3s forwards;
        }
        .rl-pulse {
          transform-origin: 360px 60px;
          animation: rl-halo 2.4s ease-out infinite;
        }
        @keyframes rl-draw { to { stroke-dashoffset: 0; } }
        @keyframes rl-halo {
          0%   { transform: scale(0.6); opacity: 0.8; }
          80%  { transform: scale(2.4); opacity: 0; }
          100% { transform: scale(2.4); opacity: 0; }
        }
        @media (prefers-reduced-motion: reduce) {
          .rl-curve { stroke-dashoffset: 0; animation: none; }
          .rl-pulse { animation: none; opacity: 0.4; }
        }
      `}</style>
    </svg>
  );
}

/* ───────────────────────── 02 · LLM evolution ──────────────────────────── */

function LlmViz() {
  // Three mini-graphs side-by-side showing the progression: single dot
  // (zero-shot), hub-and-spoke (agentic with tools), full mini-graph
  // (multi-agent debate). Each highlights in sequence on a 4-second loop.
  return (
    <svg
      viewBox="0 0 400 260"
      preserveAspectRatio="xMaxYMid slice"
      className="absolute inset-0 w-full h-full"
      aria-hidden
    >
      {/* Stage 1 — zero-shot */}
      <g className="llm-stage llm-stage-0" transform="translate(80, 130)">
        <circle r="14" fill="rgba(34,211,238,0.12)" stroke="#22d3ee" strokeWidth="1.4" />
        <circle r="5" fill="#22d3ee" />
        <text y="38" textAnchor="middle" fontSize="9" fontFamily="var(--font-jbm)" fill="#67e8f9" letterSpacing="1">ZERO-SHOT</text>
      </g>

      {/* Stage 2 — single agentic with tools */}
      <g className="llm-stage llm-stage-1" transform="translate(200, 130)">
        {[0, 90, 180, 270].map((deg) => {
          const r = 22;
          const rad = (deg * Math.PI) / 180;
          const x = r * Math.cos(rad);
          const y = r * Math.sin(rad);
          return (
            <g key={deg}>
              <line x1="0" y1="0" x2={x} y2={y} stroke="rgba(34,211,238,0.4)" strokeWidth="1" />
              <circle cx={x} cy={y} r="3" fill="#67e8f9" />
            </g>
          );
        })}
        <circle r="14" fill="rgba(34,211,238,0.18)" stroke="#22d3ee" strokeWidth="1.4" />
        <circle r="5" fill="#22d3ee" />
        <text y="58" textAnchor="middle" fontSize="9" fontFamily="var(--font-jbm)" fill="#67e8f9" letterSpacing="1">AGENTIC</text>
      </g>

      {/* Stage 3 — multi-agent debate */}
      <g className="llm-stage llm-stage-2" transform="translate(330, 130)">
        {/* 8 nodes in a small graph */}
        {[
          [-22, -14], [-22, 0], [-22, 14],   // analysts (left col)
          [-4, -8], [-4, 8],                  // bull/bear (middle col)
          [12, 0],                            // trader
          [24, 0],                            // risk
          [34, 0],                            // portfolio
        ].map(([x, y], i) => (
          <circle key={i} cx={x} cy={y} r="2.6" fill="#22d3ee" opacity={i === 7 ? 1 : 0.7} />
        ))}
        {/* a few edges */}
        <g stroke="rgba(34,211,238,0.4)" strokeWidth="0.8" fill="none">
          <line x1="-22" y1="-14" x2="-4" y2="-8" />
          <line x1="-22" y1="0" x2="-4" y2="-8" />
          <line x1="-22" y1="14" x2="-4" y2="8" />
          <line x1="-4" y1="-8" x2="12" y2="0" />
          <line x1="-4" y1="8" x2="12" y2="0" />
          <line x1="12" y1="0" x2="24" y2="0" />
          <line x1="24" y1="0" x2="34" y2="0" />
        </g>
        <text y="38" textAnchor="middle" fontSize="9" fontFamily="var(--font-jbm)" fill="#67e8f9" letterSpacing="1">MULTI-AGENT</text>
      </g>

      {/* connecting arrows */}
      <line x1="100" y1="130" x2="172" y2="130" stroke="rgba(34,211,238,0.3)" strokeWidth="1" strokeDasharray="3 3" markerEnd="url(#llm-arrow)" />
      <line x1="232" y1="130" x2="294" y2="130" stroke="rgba(34,211,238,0.3)" strokeWidth="1" strokeDasharray="3 3" markerEnd="url(#llm-arrow)" />
      <defs>
        <marker id="llm-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto">
          <path d="M0 0 L10 5 L0 10z" fill="rgba(34,211,238,0.5)" />
        </marker>
      </defs>

      <style>{`
        .llm-stage {
          opacity: 0.55;
          transition: opacity 250ms ease;
        }
        .llm-stage-0 { animation: llm-cycle 4.5s ease-in-out 0s infinite; }
        .llm-stage-1 { animation: llm-cycle 4.5s ease-in-out 1.5s infinite; }
        .llm-stage-2 { animation: llm-cycle 4.5s ease-in-out 3s infinite; }
        @keyframes llm-cycle {
          0%, 33%, 100% { opacity: 0.55; filter: none; }
          12%, 22% {
            opacity: 1;
            filter: drop-shadow(0 0 6px #22d3ee);
          }
        }
        @media (prefers-reduced-motion: reduce) {
          .llm-stage, .llm-stage-0, .llm-stage-1, .llm-stage-2 {
            animation: none;
            opacity: 0.7;
          }
        }
      `}</style>
    </svg>
  );
}

/* ───────────────────────── 03 · Live SSE pulse ─────────────────────────── */

function LiveViz() {
  // 8 dots in a row; a pulse "packet" sweeps left-to-right repeatedly,
  // lighting each dot as it passes. Mirrors the SSE event stream visually.
  const dots = Array.from({ length: 8 }, (_, i) => 40 + i * 42);
  return (
    <svg
      viewBox="0 0 400 260"
      preserveAspectRatio="xMaxYMid slice"
      className="absolute inset-0 w-full h-full"
      aria-hidden
    >
      {/* baseline */}
      <line x1="30" y1="170" x2="380" y2="170" stroke="rgba(34,211,238,0.18)" strokeDasharray="2 6" />
      {dots.map((x, i) => (
        <g key={i}>
          <circle cx={x} cy="170" r="6" fill="rgba(34,211,238,0.1)" stroke="rgba(34,211,238,0.35)" strokeWidth="1" />
          <circle
            cx={x}
            cy="170"
            r="4"
            fill="#22d3ee"
            className="live-dot"
            style={{ animationDelay: `${i * 0.45}s` } as React.CSSProperties}
          />
        </g>
      ))}
      <text x="200" y="210" textAnchor="middle" fontSize="9" fontFamily="var(--font-jbm)" fill="#67e8f9" letterSpacing="1.5">
        SSE · 8 ROLES
      </text>
      <style>{`
        .live-dot {
          opacity: 0;
          transform-origin: center;
          animation: live-fire 3.6s ease-in-out infinite;
        }
        @keyframes live-fire {
          0%, 60%, 100% { opacity: 0; transform: scale(0.5); }
          5% { opacity: 1; transform: scale(1.4); filter: drop-shadow(0 0 6px #22d3ee); }
          20% { opacity: 0.6; transform: scale(1); filter: none; }
        }
        @media (prefers-reduced-motion: reduce) {
          .live-dot { animation: none; opacity: 0.7; }
        }
      `}</style>
    </svg>
  );
}

/* ───────────────────────── 04 · Honest comparison ──────────────────────── */

function CompareViz() {
  // 8 horizontal bars of varying lengths terminate at a shared vertical axis
  // — visually argues "same yardstick, same finish line". Bars cycle a
  // soft fill animation.
  const bars = [
    { y: 50, len: 220, color: "#22d3ee" },   // multi_agent
    { y: 72, len: 190, color: "#67e8f9" },   // ppo
    { y: 94, len: 245, color: "#a1a1aa" },   // baseline 1
    { y: 116, len: 165, color: "#06b6d4" },  // ddpg
    { y: 138, len: 145, color: "#a1a1aa" },  // baseline 2
    { y: 160, len: 130, color: "#ea580c" },  // single
    { y: 182, len: 115, color: "#16a34a" },  // zero
    { y: 204, len: 70, color: "#52525b" },   // random
  ];
  return (
    <svg
      viewBox="0 0 400 260"
      preserveAspectRatio="xMaxYMid slice"
      className="absolute inset-0 w-full h-full"
      aria-hidden
    >
      {/* center axis */}
      <line x1="70" y1="32" x2="70" y2="222" stroke="rgba(34,211,238,0.55)" strokeWidth="1.4" />
      <text x="70" y="22" textAnchor="middle" fontSize="9" fontFamily="var(--font-jbm)" fill="#67e8f9" letterSpacing="1.5">
        T=0
      </text>
      {bars.map((b, i) => (
        <g key={i}>
          <rect
            x="70"
            y={b.y - 4}
            width={b.len}
            height="8"
            fill={b.color}
            opacity="0.18"
            rx="2"
          />
          <rect
            className="cmp-bar"
            x="70"
            y={b.y - 4}
            width={b.len}
            height="8"
            fill={b.color}
            rx="2"
            style={{
              transformOrigin: "70px center",
              animationDelay: `${i * 0.15}s`,
            } as React.CSSProperties}
          />
          <circle cx={70 + b.len} cy={b.y} r="3" fill={b.color}
            style={{ filter: `drop-shadow(0 0 4px ${b.color})` }}
          />
        </g>
      ))}
      <style>{`
        .cmp-bar {
          transform: scaleX(0);
          animation: cmp-grow 3s ease-out forwards;
        }
        @keyframes cmp-grow { to { transform: scaleX(1); } }
        @media (prefers-reduced-motion: reduce) {
          .cmp-bar { transform: scaleX(1); animation: none; }
        }
      `}</style>
    </svg>
  );
}
