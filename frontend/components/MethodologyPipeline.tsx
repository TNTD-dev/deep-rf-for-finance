"use client";

/**
 * MethodologyPipeline — "Three steps, no hand-waving".
 *
 * Previous attempt had a separate pipeline SVG above the cards with
 * misaligned halos (transform-origin bug in SVG: CSS scale was rotating
 * around (0,0) of the SVG canvas, not the circle's center). Easy fix:
 * use transform-box: fill-box. Easier fix: skip the separate pipeline
 * SVG entirely and embed the node + number directly inside each card.
 *
 * Layout:
 *   [Card 01]  →→→  [Card 02]  →→→  [Card 03]
 *
 * The connector arrows live in a single overlay SVG on top of the grid;
 * they only render on md+ where the cards sit side by side. Each card
 * carries its own glowing node + step number + icon + copy.
 */

import { ScrollFade } from "@/components/ScrollFade";
import { Kicker } from "@/components/ui/glass";

const STEPS = [
  {
    n: "01",
    title: "Train",
    body: "5 years of VN30 prices (2019-01 → 2024-12). DDPG + PPO via stable-baselines3 on a custom gymnasium env enforcing HOSE rules. LLM agents use gpt-4o + gpt-4o-mini, locked at the Oct 2023 cutoff so the test window stays out-of-distribution.",
    icon: <IconTrain />,
  },
  {
    n: "02",
    title: "Backtest",
    body: "Test window 2025-05 → 2026-04, 248 daily sessions on five tickers (VCB, FPT, HPG, VIC, VNM). RL decides daily; LLM agents decide weekly to control cost. Decisions emit target weights; the env handles ±7% clamping, 100-share lot rounding, and asymmetric 0.15% / 0.25% fees.",
    icon: <IconBacktest />,
  },
  {
    n: "03",
    title: "Compare",
    body: "Every agent produces a portfolio curve, holdings parquet, and metrics JSON. metrics_table.csv aggregates all 8 into one wide row. Same seed → identical trajectory. Multi-agent transcripts cached per (date, ticker_set, prompt_hash) so reruns are free.",
    icon: <IconCompare />,
  },
];

export function MethodologyPipeline() {
  return (
    <section className="container mx-auto max-w-7xl px-6 py-20">
      <ScrollFade>
        <Kicker>How it works</Kicker>
        <h2
          className="mt-4 text-4xl sm:text-5xl font-bold tracking-tight text-white"
          style={{ fontFamily: "var(--font-grotesk)" }}
        >
          Three steps, no hand-waving
        </h2>
      </ScrollFade>

      {/* The grid is the actual layout. Arrows are siblings that occupy
          empty space between cards — see ArrowBetween below. */}
      <div className="relative mt-12 grid gap-6 md:grid-cols-3">
        {STEPS.map((s, i) => (
          <ScrollFade key={s.n} delayMs={i * 140}>
            <StepCard step={s} index={i} />
          </ScrollFade>
        ))}

        {/* Connector arrows — only render on md+, positioned absolutely
            between cards 1↔2 and 2↔3. Pure decoration over the gap. */}
        <ArrowBetween position={1} />
        <ArrowBetween position={2} />
      </div>
    </section>
  );
}

function StepCard({
  step,
  index,
}: {
  step: (typeof STEPS)[number];
  index: number;
}) {
  return (
    <div className="relative h-full rounded-lg border border-cyan-400/15 bg-gradient-to-b from-cyan-400/[0.05] to-transparent p-7">
      {/* Big numbered node — fills the visual role the broken pipeline
          tried to play. Halo + core pulse, properly centered now. */}
      <NodeHeader n={step.n} icon={step.icon} delay={index * 0.7} />

      <h3
        className="mt-6 text-2xl font-bold text-white"
        style={{ fontFamily: "var(--font-grotesk)" }}
      >
        {step.title}
      </h3>
      <p className="mt-4 text-sm leading-relaxed text-zinc-400">{step.body}</p>
    </div>
  );
}

function NodeHeader({
  n,
  icon,
  delay,
}: {
  n: string;
  icon: React.ReactNode;
  delay: number;
}) {
  return (
    <div className="flex items-center gap-4">
      <div className="relative">
        {/* Halo */}
        <div
          className="absolute -inset-3 rounded-full"
          style={{
            background:
              "radial-gradient(circle, rgba(34,211,238,0.35), transparent 65%)",
            animation: "mp-halo 2.8s ease-in-out infinite",
            animationDelay: `${delay}s`,
          }}
        />
        {/* Core */}
        <div
          className="relative h-14 w-14 rounded-full border border-cyan-400 bg-black flex items-center justify-center text-cyan-300"
          style={{
            boxShadow: "inset 0 0 12px rgba(34,211,238,0.25), 0 0 18px rgba(34,211,238,0.2)",
            animation: "mp-core 2.8s ease-in-out infinite",
            animationDelay: `${delay}s`,
          }}
        >
          {icon}
        </div>
      </div>

      <span
        className="rounded bg-black/70 px-2.5 py-1 font-mono text-xs uppercase tracking-[0.2em] text-cyan-300 ring-1 ring-cyan-400/35"
        style={{ boxShadow: "0 0 12px rgba(34,211,238,0.25)" }}
      >
        {n}
      </span>

      <style jsx>{`
        @keyframes mp-halo {
          0%, 100% { transform: scale(1); opacity: 0.7; }
          50%      { transform: scale(1.18); opacity: 1; }
        }
        @keyframes mp-core {
          0%, 100% { box-shadow: inset 0 0 12px rgba(34,211,238,0.25), 0 0 18px rgba(34,211,238,0.2); }
          50%      { box-shadow: inset 0 0 18px rgba(34,211,238,0.45), 0 0 30px rgba(34,211,238,0.45); }
        }
        @media (prefers-reduced-motion: reduce) {
          div { animation: none !important; }
        }
      `}</style>
    </div>
  );
}

/** Inline arrow rendered absolutely over the grid gap. position=1 means
 *  between cards 1 and 2; position=2 means between cards 2 and 3.
 *  Hidden below md so the layout collapses cleanly on mobile. */
function ArrowBetween({ position }: { position: 1 | 2 }) {
  // Each card spans 1/3 of the row. Gap between cards is `gap-6` = 1.5rem.
  // The arrow sits centered in the gutter at the vertical position of the
  // node header (~52px from the top of the card). Computing exact pixels
  // is fragile across breakpoints, so we anchor by % and tune vertically.
  const leftPercent = position === 1 ? "33.333%" : "66.666%";
  return (
    <div
      aria-hidden
      className="pointer-events-none hidden md:flex absolute z-10 items-center justify-center"
      style={{
        left: leftPercent,
        top: "52px",
        width: "1.5rem",
        height: "1.5rem",
        transform: "translateX(-50%)",
      }}
    >
      <svg viewBox="0 0 60 24" className="w-full h-auto" aria-hidden>
        <defs>
          <marker
            id={`mp-arrow-${position}`}
            viewBox="0 0 10 10"
            refX="9"
            refY="5"
            markerWidth="6"
            markerHeight="6"
            orient="auto"
          >
            <path d="M0 0 L10 5 L0 10z" fill="#22d3ee" />
          </marker>
        </defs>
        <line
          x1="0"
          y1="12"
          x2="48"
          y2="12"
          stroke="rgba(34,211,238,0.45)"
          strokeWidth="1.4"
          strokeDasharray="5 4"
          markerEnd={`url(#mp-arrow-${position})`}
        />
        <circle
          className="mp-packet"
          cx="0"
          cy="12"
          r="3"
          fill="#22d3ee"
          style={{
            filter: "drop-shadow(0 0 6px #22d3ee)",
            animationDelay: position === 2 ? "1.2s" : "0s",
          } as React.CSSProperties}
        />
        <style>{`
          .mp-packet {
            opacity: 0;
            animation: mp-fly 2.4s linear infinite;
          }
          @keyframes mp-fly {
            0%   { opacity: 0; transform: translateX(0); }
            10%  { opacity: 1; }
            70%  { opacity: 1; transform: translateX(46px); }
            85%, 100% { opacity: 0; transform: translateX(46px); }
          }
          @media (prefers-reduced-motion: reduce) {
            .mp-packet { animation: none; opacity: 0.6; }
          }
        `}</style>
      </svg>
    </div>
  );
}

/* ───────────────────────── icons ───────────────────────────────────────── */

const STROKE: React.SVGProps<SVGSVGElement> = {
  width: 22,
  height: 22,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.6,
  strokeLinecap: "round",
  strokeLinejoin: "round",
};

function IconTrain() {
  return (
    <svg {...STROKE}>
      <path d="M3 18l5-6 4 4 6-9" />
      <circle cx="3" cy="18" r="1.5" fill="currentColor" />
      <circle cx="12" cy="16" r="1.5" fill="currentColor" />
      <circle cx="18" cy="7" r="1.5" fill="currentColor" />
    </svg>
  );
}
function IconBacktest() {
  return (
    <svg {...STROKE}>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M3 9h18M8 4v16M14 12l3 3" />
    </svg>
  );
}
function IconCompare() {
  return (
    <svg {...STROKE}>
      <path d="M4 6h7M4 12h12M4 18h9" />
      <circle cx="14" cy="6" r="1.5" fill="currentColor" />
      <circle cx="19" cy="12" r="1.5" fill="currentColor" />
      <circle cx="16" cy="18" r="1.5" fill="currentColor" />
    </svg>
  );
}
