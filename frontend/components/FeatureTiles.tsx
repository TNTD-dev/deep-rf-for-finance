"use client";

/**
 * FeatureTiles — landing "Four layers, one comparison".
 *
 * Layout per tile is now strictly stacked: SVG mini-visualization in a
 * bounded top region (fixed 160px height, its own gradient background),
 * text section below. No overlap, no underlay — the previous attempt
 * floated the viz beneath the text at 50 % opacity which read as messy
 * (user feedback: "ảnh đè chữ").
 *
 * Each viz is a hand-rolled SVG with @keyframes — no extra deps.
 * preserveAspectRatio + transform-box make the animations align in the
 * frame regardless of card width.
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
      <div className="flex flex-col h-full">
        {/* VIZ — bounded top region with its own subtle gradient background.
            overflow-hidden clips anything that leaks past the viewBox so
            bars/lines can't bleed into the text section. */}
        <div className="relative h-44 overflow-hidden border-b border-cyan-400/10 bg-gradient-to-br from-cyan-400/[0.04] to-transparent">
          {feature.viz}
        </div>

        {/* TEXT — clean, no underlay. */}
        <div className="p-6 sm:p-7 flex-1">
          <p className="label-mono">{feature.tag}</p>
          <h3
            className="mt-3 text-xl font-bold text-white"
            style={{ fontFamily: "var(--font-grotesk)" }}
          >
            {feature.title}
          </h3>
          <p className="mt-3 text-sm leading-relaxed text-zinc-400">
            {feature.body}
          </p>
        </div>
      </div>
    </GlassPanel>
  );
}

/* ────────────────────────────────────────────────────────────────────────── */
/*  Shared SVG animation style — transform-box: fill-box is the magic that    */
/*  makes CSS transform-origin actually mean "center of this SVG element"     */
/*  instead of "(0,0) of the SVG canvas". Without it, scaled circles drift.   */
/* ────────────────────────────────────────────────────────────────────────── */

const FILL_BOX: React.CSSProperties = {
  transformBox: "fill-box",
  transformOrigin: "center",
};

/* ───────────────────────── 01 · RL sparkline ───────────────────────────── */

function RlViz() {
  return (
    <svg
      viewBox="0 0 400 160"
      preserveAspectRatio="xMidYMid meet"
      className="w-full h-full"
      aria-hidden
    >
      <defs>
        <linearGradient id="rl-fill" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#22d3ee" stopOpacity="0.25" />
          <stop offset="100%" stopColor="#22d3ee" stopOpacity="0" />
        </linearGradient>
      </defs>
      {/* baseline */}
      <line x1="30" y1="130" x2="370" y2="130" stroke="rgba(34,211,238,0.18)" strokeDasharray="2 4" />
      {/* area */}
      <path
        d="M 30 120 L 70 116 L 110 105 L 150 100 L 190 82 L 230 84 L 270 60 L 310 48 L 350 28 L 350 130 L 30 130 Z"
        fill="url(#rl-fill)"
      />
      {/* curve */}
      <path
        className="rl-curve"
        d="M 30 120 L 70 116 L 110 105 L 150 100 L 190 82 L 230 84 L 270 60 L 310 48 L 350 28"
        fill="none"
        stroke="#22d3ee"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* endpoint glow */}
      <circle cx="350" cy="28" r="10" fill="rgba(34,211,238,0.25)" className="rl-pulse" style={FILL_BOX} />
      <circle cx="350" cy="28" r="3.5" fill="#22d3ee" style={{ filter: "drop-shadow(0 0 5px #22d3ee)" }} />
      <text
        x="346"
        y="20"
        textAnchor="end"
        fontSize="10"
        fontFamily="var(--font-jbm)"
        fill="#67e8f9"
        letterSpacing="1"
        fontWeight="600"
      >
        +40.29%
      </text>
      <text
        x="30"
        y="148"
        fontSize="9"
        fontFamily="var(--font-jbm)"
        fill="rgba(161,161,170,0.65)"
        letterSpacing="1.5"
      >
        PPO · TEST WINDOW
      </text>
      <style>{`
        .rl-curve {
          stroke-dasharray: 600;
          stroke-dashoffset: 600;
          animation: rl-draw 3.5s ease-out 0.3s forwards;
        }
        .rl-pulse { animation: rl-halo 2.4s ease-out infinite; }
        @keyframes rl-draw { to { stroke-dashoffset: 0; } }
        @keyframes rl-halo {
          0%   { transform: scale(0.6); opacity: 0.8; }
          80%, 100% { transform: scale(2.4); opacity: 0; }
        }
        @media (prefers-reduced-motion: reduce) {
          .rl-curve, .rl-pulse { animation: none; }
          .rl-curve { stroke-dashoffset: 0; }
        }
      `}</style>
    </svg>
  );
}

/* ───────────────────────── 02 · LLM evolution ──────────────────────────── */

function LlmViz() {
  return (
    <svg
      viewBox="0 0 400 160"
      preserveAspectRatio="xMidYMid meet"
      className="w-full h-full"
      aria-hidden
    >
      <defs>
        <marker id="llm-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto">
          <path d="M0 0 L10 5 L0 10z" fill="rgba(34,211,238,0.55)" />
        </marker>
      </defs>

      {/* Stage 1: zero-shot — single dot */}
      <g className="llm-stage" style={FILL_BOX} transform="translate(70, 75)">
        <circle r="14" fill="rgba(34,211,238,0.12)" stroke="#22d3ee" strokeWidth="1.4" />
        <circle r="5" fill="#22d3ee" />
        <text y="36" textAnchor="middle" fontSize="9" fontFamily="var(--font-jbm)" fill="#67e8f9" letterSpacing="1.2" fontWeight="600">
          ZERO-SHOT
        </text>
      </g>

      {/* Stage 2: hub+spoke */}
      <g className="llm-stage" style={{ ...FILL_BOX, animationDelay: "1.4s" } as React.CSSProperties} transform="translate(200, 75)">
        {[0, 90, 180, 270].map((deg) => {
          // Round so SSR / CSR floats serialize identically — Math.cos at
          // 90° / 270° produces tiny epsilon values that differ across V8
          // builds and trip Next 16's hydration check.
          const r = 22;
          const rad = (deg * Math.PI) / 180;
          const x = Math.round(r * Math.cos(rad) * 100) / 100;
          const y = Math.round(r * Math.sin(rad) * 100) / 100;
          return (
            <g key={deg}>
              <line x1="0" y1="0" x2={x} y2={y} stroke="rgba(34,211,238,0.45)" strokeWidth="1" />
              <circle cx={x} cy={y} r="3" fill="#67e8f9" />
            </g>
          );
        })}
        <circle r="14" fill="rgba(34,211,238,0.18)" stroke="#22d3ee" strokeWidth="1.4" />
        <circle r="5" fill="#22d3ee" />
        <text y="50" textAnchor="middle" fontSize="9" fontFamily="var(--font-jbm)" fill="#67e8f9" letterSpacing="1.2" fontWeight="600">
          AGENTIC
        </text>
      </g>

      {/* Stage 3: multi-agent mini graph */}
      <g className="llm-stage" style={{ ...FILL_BOX, animationDelay: "2.8s" } as React.CSSProperties} transform="translate(330, 75)">
        <g stroke="rgba(34,211,238,0.45)" strokeWidth="0.8" fill="none">
          <line x1="-22" y1="-14" x2="-4" y2="-7" />
          <line x1="-22" y1="0" x2="-4" y2="-7" />
          <line x1="-22" y1="14" x2="-4" y2="7" />
          <line x1="-4" y1="-7" x2="12" y2="0" />
          <line x1="-4" y1="7" x2="12" y2="0" />
          <line x1="12" y1="0" x2="22" y2="0" />
          <line x1="22" y1="0" x2="32" y2="0" />
        </g>
        {[
          [-22, -14], [-22, 0], [-22, 14],
          [-4, -7], [-4, 7],
          [12, 0], [22, 0], [32, 0],
        ].map(([x, y], i) => (
          <circle key={i} cx={x} cy={y} r="2.8" fill="#22d3ee" opacity={i === 7 ? 1 : 0.75} />
        ))}
        <text y="34" textAnchor="middle" fontSize="9" fontFamily="var(--font-jbm)" fill="#67e8f9" letterSpacing="1.2" fontWeight="600">
          MULTI-AGENT
        </text>
      </g>

      {/* arrows between stages */}
      <line x1="96" y1="75" x2="170" y2="75" stroke="rgba(34,211,238,0.35)" strokeWidth="1" strokeDasharray="3 3" markerEnd="url(#llm-arrow)" />
      <line x1="232" y1="75" x2="294" y2="75" stroke="rgba(34,211,238,0.35)" strokeWidth="1" strokeDasharray="3 3" markerEnd="url(#llm-arrow)" />

      <style>{`
        .llm-stage {
          opacity: 0.55;
          animation: llm-cycle 4.2s ease-in-out infinite;
        }
        @keyframes llm-cycle {
          0%, 35%, 100% { opacity: 0.55; filter: none; }
          10%, 25% {
            opacity: 1;
            filter: drop-shadow(0 0 6px #22d3ee);
          }
        }
        @media (prefers-reduced-motion: reduce) {
          .llm-stage { animation: none; opacity: 0.8; }
        }
      `}</style>
    </svg>
  );
}

/* ───────────────────────── 03 · Live SSE pulse ─────────────────────────── */

function LiveViz() {
  // 8 dots in a row. A pulse sweeps left-to-right, lighting each in turn.
  return (
    <svg
      viewBox="0 0 400 160"
      preserveAspectRatio="xMidYMid meet"
      className="w-full h-full"
      aria-hidden
    >
      {/* baseline */}
      <line x1="30" y1="80" x2="370" y2="80" stroke="rgba(34,211,238,0.18)" strokeDasharray="2 6" />
      {Array.from({ length: 8 }, (_, i) => {
        const x = 50 + i * 40;
        return (
          <g key={i}>
            <circle cx={x} cy="80" r="6" fill="rgba(34,211,238,0.08)" stroke="rgba(34,211,238,0.35)" strokeWidth="1" />
            <circle
              cx={x}
              cy="80"
              r="4"
              fill="#22d3ee"
              className="live-dot"
              style={{ ...FILL_BOX, animationDelay: `${i * 0.45}s` } as React.CSSProperties}
            />
          </g>
        );
      })}
      <text
        x="200"
        y="130"
        textAnchor="middle"
        fontSize="10"
        fontFamily="var(--font-jbm)"
        fill="#67e8f9"
        letterSpacing="2"
        fontWeight="600"
      >
        SSE · 8 ROLES
      </text>
      <style>{`
        .live-dot {
          opacity: 0;
          animation: live-fire 3.6s ease-in-out infinite;
        }
        @keyframes live-fire {
          0%, 60%, 100% { opacity: 0; transform: scale(0.5); }
          5% { opacity: 1; transform: scale(1.45); filter: drop-shadow(0 0 6px #22d3ee); }
          22% { opacity: 0.55; transform: scale(1); filter: none; }
        }
        @media (prefers-reduced-motion: reduce) {
          .live-dot { animation: none; opacity: 0.6; }
        }
      `}</style>
    </svg>
  );
}

/* ───────────────────────── 04 · Honest comparison ──────────────────────── */

function CompareViz() {
  // 8 bars converging on a shared T=0 axis. The axis sits at x=80 within
  // the 400-wide viewBox; bars are clipped to viewBox so they never bleed
  // into the text section.
  const bars = [
    { y: 28, len: 200, color: "#22d3ee" },
    { y: 42, len: 168, color: "#67e8f9" },
    { y: 56, len: 198, color: "#94a3b8" },
    { y: 70, len: 140, color: "#06b6d4" },
    { y: 84, len: 110, color: "#94a3b8" },
    { y: 98, len: 88, color: "#ea580c" },
    { y: 112, len: 70, color: "#16a34a" },
    { y: 126, len: 32, color: "#52525b" },
  ];
  return (
    <svg
      viewBox="0 0 400 160"
      preserveAspectRatio="xMidYMid meet"
      className="w-full h-full"
      aria-hidden
    >
      <line x1="80" y1="18" x2="80" y2="138" stroke="rgba(34,211,238,0.55)" strokeWidth="1.4" />
      <text x="80" y="12" textAnchor="middle" fontSize="8" fontFamily="var(--font-jbm)" fill="#67e8f9" letterSpacing="1.5" fontWeight="600">
        T=0
      </text>
      {bars.map((b, i) => (
        <g key={i}>
          <rect x="80" y={b.y - 3} width={b.len} height="6" fill={b.color} opacity="0.18" rx="1.5" />
          <rect
            className="cmp-bar"
            x="80"
            y={b.y - 3}
            width={b.len}
            height="6"
            fill={b.color}
            rx="1.5"
            style={{
              transformBox: "fill-box",
              transformOrigin: "left center",
              animationDelay: `${i * 0.12}s`,
            } as React.CSSProperties}
          />
          <circle cx={80 + b.len} cy={b.y} r="2.5" fill={b.color} style={{ filter: `drop-shadow(0 0 4px ${b.color})` }} />
        </g>
      ))}
      <text x="200" y="155" textAnchor="middle" fontSize="9" fontFamily="var(--font-jbm)" fill="rgba(161,161,170,0.65)" letterSpacing="1.5">
        SAME ENV · 8 AGENTS
      </text>
      <style>{`
        .cmp-bar {
          transform: scaleX(0);
          animation: cmp-grow 2.4s ease-out forwards;
        }
        @keyframes cmp-grow { to { transform: scaleX(1); } }
        @media (prefers-reduced-motion: reduce) {
          .cmp-bar { transform: scaleX(1); animation: none; }
        }
      `}</style>
    </svg>
  );
}
