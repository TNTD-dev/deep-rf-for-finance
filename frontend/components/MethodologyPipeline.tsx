"use client";

/**
 * MethodologyPipeline — "Three steps, no hand-waving" as a connected
 * pipeline. Three large nodes (Train → Backtest → Compare) joined by
 * dashed cyan arrows with a "packet" dot that flows continuously between
 * them. Each node has a domain icon, big step number, headline, and copy.
 *
 * Replaces the previous flat 3-card grid: same content, much more visual
 * energy. Each node also runs a subtle pulse on its own delay so the
 * pipeline reads as alive.
 */

import { ScrollFade } from "@/components/ScrollFade";
import { Kicker } from "@/components/ui/glass";

const STEPS = [
  {
    n: "01",
    title: "Train",
    body: "5 years of VN30 prices (2019-01 → 2024-12). DDPG + PPO via stable-baselines3 on a custom gymnasium env that enforces HOSE rules. LLM agents use gpt-4o + gpt-4o-mini, locked at the Oct 2023 cutoff so the test window stays out-of-distribution.",
    icon: <IconTrain />,
  },
  {
    n: "02",
    title: "Backtest",
    body: "Test window 2025-05 → 2026-04, 248 daily sessions on five tickers (VCB, FPT, HPG, VIC, VNM). RL decides daily; LLM agents decide weekly to control cost. Decisions emit target weights; the env handles ±7% clamping, 100-share lot rounding, and 0.15% / 0.25% fees.",
    icon: <IconBacktest />,
  },
  {
    n: "03",
    title: "Compare",
    body: "Every agent produces a portfolio curve, holdings parquet, and metrics JSON. metrics_table.csv aggregates all 8 into one wide row. Same seed → identical trajectory. Multi-agent transcripts are cached per (date, ticker_set, prompt_hash) so reruns are free.",
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

      {/* Pipeline — desktop only. Renders a 3-node SVG flow with animated
          dashed connectors and a traveling packet. On mobile we collapse
          to a vertical timeline (PipelineMobile). */}
      <div className="mt-14 hidden md:block">
        <PipelineDesktop />
      </div>
      <div className="mt-10 md:hidden">
        <PipelineMobile />
      </div>
    </section>
  );
}

/* ───────────────────────── desktop pipeline ────────────────────────────── */

function PipelineDesktop() {
  return (
    <div className="relative">
      {/* Top SVG layer: 3 large nodes + animated connectors. Pure SVG so
          everything aligns with the cards below regardless of resize. */}
      <svg
        viewBox="0 0 1200 220"
        preserveAspectRatio="none"
        className="w-full h-[200px]"
        aria-hidden
      >
        <defs>
          <radialGradient id="mp-node" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#22d3ee" stopOpacity="0.8" />
            <stop offset="60%" stopColor="#22d3ee" stopOpacity="0.25" />
            <stop offset="100%" stopColor="#22d3ee" stopOpacity="0" />
          </radialGradient>
          <marker
            id="mp-arrow"
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

        {/* connector 1→2 */}
        <line
          x1="280"
          y1="110"
          x2="520"
          y2="110"
          stroke="rgba(34,211,238,0.35)"
          strokeWidth="1.5"
          strokeDasharray="6 6"
          markerEnd="url(#mp-arrow)"
        />
        <circle className="mp-packet mp-packet-1" cx="280" cy="110" r="4" fill="#22d3ee" />

        {/* connector 2→3 */}
        <line
          x1="680"
          y1="110"
          x2="920"
          y2="110"
          stroke="rgba(34,211,238,0.35)"
          strokeWidth="1.5"
          strokeDasharray="6 6"
          markerEnd="url(#mp-arrow)"
        />
        <circle className="mp-packet mp-packet-2" cx="680" cy="110" r="4" fill="#22d3ee" />

        {/* node 1 — Train */}
        <NodeMark cx={200} cy={110} delay={0} />
        {/* node 2 — Backtest */}
        <NodeMark cx={600} cy={110} delay={0.7} />
        {/* node 3 — Compare */}
        <NodeMark cx={1000} cy={110} delay={1.4} />

        <style>{`
          .mp-packet {
            opacity: 0;
            animation: mp-fly 3.6s linear infinite;
            filter: drop-shadow(0 0 6px #22d3ee);
          }
          .mp-packet-1 { animation-delay: 0.0s; }
          .mp-packet-2 { animation-delay: 1.2s; }
          @keyframes mp-fly {
            0%   { opacity: 0; transform: translateX(0); }
            5%   { opacity: 1; }
            45%  { opacity: 1; transform: translateX(240px); }
            55%  { opacity: 0; transform: translateX(240px); }
            100% { opacity: 0; transform: translateX(240px); }
          }
          @media (prefers-reduced-motion: reduce) {
            .mp-packet { animation: none; opacity: 0.6; }
          }
        `}</style>
      </svg>

      {/* Card row underneath the SVG, aligned to the three node positions
          via CSS grid. */}
      <div className="-mt-2 grid grid-cols-3 gap-6">
        {STEPS.map((s, i) => (
          <ScrollFade key={s.n} delayMs={i * 140}>
            <StepCard step={s} />
          </ScrollFade>
        ))}
      </div>
    </div>
  );
}

function NodeMark({ cx, cy, delay }: { cx: number; cy: number; delay: number }) {
  return (
    <g>
      <circle cx={cx} cy={cy} r="60" fill="url(#mp-node)" className="mp-halo" style={{ animationDelay: `${delay}s` }} />
      <circle cx={cx} cy={cy} r="36" fill="rgba(8,10,12,0.85)" stroke="#22d3ee" strokeWidth="1.6" />
      <circle cx={cx} cy={cy} r="6" fill="#22d3ee" className="mp-core" style={{ animationDelay: `${delay}s` }} />
      <style>{`
        .mp-halo {
          transform-origin: center;
          animation: mp-halo 2.8s ease-in-out infinite;
        }
        .mp-core {
          transform-origin: center;
          animation: mp-core 2.8s ease-in-out infinite;
        }
        @keyframes mp-halo {
          0%, 100% { transform: scale(1); opacity: 0.7; }
          50%      { transform: scale(1.18); opacity: 1; }
        }
        @keyframes mp-core {
          0%, 100% { transform: scale(1); }
          50%      { transform: scale(1.25); filter: drop-shadow(0 0 8px #22d3ee); }
        }
        @media (prefers-reduced-motion: reduce) {
          .mp-halo, .mp-core { animation: none; }
        }
      `}</style>
    </g>
  );
}

function StepCard({ step }: { step: (typeof STEPS)[number] }) {
  return (
    <div className="relative rounded-lg border border-cyan-400/15 bg-gradient-to-b from-cyan-400/[0.04] to-transparent p-6 h-full">
      <div className="flex items-center gap-3 mb-4">
        <div className="rounded-md border border-cyan-400/30 bg-cyan-400/10 p-2.5 text-cyan-300">
          {step.icon}
        </div>
        <span
          className="rounded bg-black/60 px-2 py-1 font-mono text-xs uppercase tracking-[0.18em] text-cyan-300 ring-1 ring-cyan-400/30"
          style={{ boxShadow: "0 0 12px rgba(34,211,238,0.25)" }}
        >
          {step.n}
        </span>
      </div>
      <h3
        className="text-2xl font-bold text-white"
        style={{ fontFamily: "var(--font-grotesk)" }}
      >
        {step.title}
      </h3>
      <p className="mt-4 text-sm leading-relaxed text-zinc-400">{step.body}</p>
    </div>
  );
}

/* ───────────────────────── mobile pipeline ─────────────────────────────── */

function PipelineMobile() {
  return (
    <ol className="space-y-5">
      {STEPS.map((s, i) => (
        <ScrollFade key={s.n} delayMs={i * 120}>
          <li className="relative flex gap-4">
            {/* vertical connector */}
            {i < STEPS.length - 1 && (
              <span className="absolute left-[18px] top-12 bottom-[-20px] w-px bg-gradient-to-b from-cyan-400/40 to-transparent" />
            )}
            <span className="relative shrink-0 mt-1.5 flex h-9 w-9 items-center justify-center rounded-full border border-cyan-400/40 bg-cyan-400/10 font-mono text-xs text-cyan-300">
              {s.n}
            </span>
            <StepCard step={s} />
          </li>
        </ScrollFade>
      ))}
    </ol>
  );
}

/* ───────────────────────── icons ───────────────────────────────────────── */

const STROKE: React.SVGProps<SVGSVGElement> = {
  width: 20,
  height: 20,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.5,
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
