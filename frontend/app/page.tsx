"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { FeatureTiles } from "@/components/FeatureTiles";
import { MethodologyPipeline } from "@/components/MethodologyPipeline";
import { OrbitalHero } from "@/components/OrbitalHero";
import { ScrollFade } from "@/components/ScrollFade";
import { GlassPanel, Kicker } from "@/components/ui/glass";
import { BACKEND_URL, getAgents, getBacktest } from "@/lib/api";
import { agentCategory, colorFor } from "@/lib/colors";
import type { BacktestPayload } from "@/lib/types";

// Headline numbers baked in so the landing renders instantly even when the
// backend is cold or unreachable. These match the PKG-S full-window snapshot.
const HEADLINE_STATS: { label: string; value: string; hint: string }[] = [
  { label: "Agents benchmarked", value: "8", hint: "3 baselines · 2 RL · 3 LLM" },
  { label: "Test window", value: "248", hint: "trading sessions · 2025-05 → 2026-04" },
  { label: "Multi-agent return", value: "+50.18%", hint: "Sharpe 2.19 · 51 weekly decisions" },
  { label: "LLM cost", value: "$3.21", hint: "full backtest, gpt-4o + gpt-4o-mini" },
];

type AgentRow = {
  name: string;
  cum: number;
  sharpe: number;
  steps: number;
};

export default function LandingPage() {
  const [rows, setRows] = useState<AgentRow[] | null>(null);
  const [warm, setWarm] = useState<"checking" | "online" | "offline">("checking");

  useEffect(() => {
    (async () => {
      try {
        const list = await getAgents();
        const all = [...list.baselines, ...list.agents];
        const results = await Promise.allSettled(all.map(getBacktest));
        const ok: AgentRow[] = [];
        results.forEach((r, i) => {
          if (r.status === "fulfilled") {
            const p = r.value as BacktestPayload;
            ok.push({
              name: all[i],
              cum: p.metrics.cumulative_return,
              sharpe: p.metrics.sharpe,
              steps: p.metrics.n_steps,
            });
          }
        });
        ok.sort((a, b) => b.cum - a.cum);
        setRows(ok);
        setWarm("online");
      } catch {
        setWarm("offline");
      }
    })();
  }, []);

  return (
    <main className="relative">
      <Hero />
      <TickerBar />
      <Stats />
      <Leaderboard rows={rows} warm={warm} />
      <FeatureTiles />
      <MethodologyPipeline />
      <CallToAction />
    </main>
  );
}

/* ────────────────────────────────────────────────────────────────────────── */
/*  HERO                                                                       */
/* ────────────────────────────────────────────────────────────────────────── */

function Hero() {
  return (
    <section className="relative overflow-hidden">
      <div className="container mx-auto max-w-7xl px-6 pt-12 pb-12 sm:pt-16 sm:pb-16 relative">
        <div className="grid lg:grid-cols-[1.1fr_1fr] gap-10 items-center">
          {/* LEFT — copy + CTAs */}
          <div>
            <ScrollFade>
              <Kicker>QuantArena · DRL × Agentic LLM · VN30</Kicker>
            </ScrollFade>
            <ScrollFade delayMs={80}>
              <h1
                className="display-xl mt-6 text-white"
                style={{ fontFamily: "var(--font-grotesk)" }}
              >
                Battle of the{" "}
                <span className="text-cyan-300">trading minds</span>.
              </h1>
            </ScrollFade>
            <ScrollFade delayMs={160}>
              <p className="mt-6 max-w-xl text-base sm:text-lg leading-relaxed text-zinc-400">
                Eight agents head-to-head on Vietnam's VN30 market — classical
                baselines, deep reinforcement learning, and three flavors of
                LLM trading culminating in an 8-role multi-agent debate.{" "}
                <span className="text-zinc-200">
                  Same env. Same fees. Same window.
                </span>
              </p>
            </ScrollFade>
            <ScrollFade delayMs={240}>
              <div className="mt-9 flex flex-wrap items-center gap-3">
                <Link
                  href="/dashboard"
                  className="group inline-flex items-center gap-2 rounded-md bg-cyan-400 px-6 py-3.5 font-mono text-xs font-semibold uppercase tracking-[0.14em] text-black transition-all hover:bg-cyan-300 glow-cyan"
                >
                  Open Dashboard
                  <Arrow />
                </Link>
                <Link
                  href="/live"
                  className="inline-flex items-center gap-2 rounded-md border border-cyan-400/35 bg-cyan-400/5 px-6 py-3.5 font-mono text-xs font-semibold uppercase tracking-[0.14em] text-cyan-200 transition-all hover:border-cyan-400 hover:text-cyan-100 hover:bg-cyan-400/10"
                >
                  Run multi-agent live
                  <Arrow />
                </Link>
                <Link
                  href="/debate"
                  className="font-mono text-xs uppercase tracking-[0.14em] text-zinc-500 hover:text-cyan-300 link-glow px-2 py-3.5"
                >
                  · Replay a debate
                </Link>
              </div>
            </ScrollFade>

            {/* Trust-line: tech bar */}
            <ScrollFade delayMs={320}>
              <div className="mt-12 flex flex-wrap gap-x-6 gap-y-2 items-center text-[11px] text-zinc-500 font-mono uppercase tracking-[0.1em]">
                <span>Powered by</span>
                <TechChip>FastAPI</TechChip>
                <TechChip>LangGraph</TechChip>
                <TechChip>stable-baselines3</TechChip>
                <TechChip>gpt-4o</TechChip>
                <TechChip>vnstock</TechChip>
              </div>
            </ScrollFade>
          </div>

          {/* RIGHT — orbital visualization */}
          <ScrollFade delayMs={120}>
            <OrbitalHero />
          </ScrollFade>
        </div>
      </div>
    </section>
  );
}

function TechChip({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded border border-cyan-400/15 bg-cyan-400/5 px-2 py-0.5 text-cyan-300/80">
      {children}
    </span>
  );
}

function Arrow() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 14 14"
      fill="none"
      aria-hidden
      className="transition-transform group-hover:translate-x-0.5"
    >
      <path
        d="M3 7h8m0 0L7.5 3.5M11 7l-3.5 3.5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/* ────────────────────────────────────────────────────────────────────────── */
/*  TICKER BAR — continuously scrolling ribbon                                 */
/* ────────────────────────────────────────────────────────────────────────── */

function TickerBar() {
  const items: { ticker: string; pct: string; pos: boolean }[] = [
    { ticker: "VCB", pct: "+1.24%", pos: true },
    { ticker: "FPT", pct: "+0.87%", pos: true },
    { ticker: "HPG", pct: "-0.32%", pos: false },
    { ticker: "VIC", pct: "+2.05%", pos: true },
    { ticker: "VNM", pct: "-0.18%", pos: false },
    { ticker: "VN30", pct: "+0.74%", pos: true },
  ];
  // Repeat the array so the CSS marquee has enough content to scroll without
  // gaps. Two copies = seamless loop when translated -50%.
  const reel = [...items, ...items, ...items, ...items];

  return (
    <div className="border-y border-cyan-400/15 bg-black/40 backdrop-blur-sm overflow-hidden">
      <div className="ticker-track flex items-center gap-12 py-3 whitespace-nowrap font-mono text-[12px]">
        {reel.map((it, i) => (
          <span key={i} className="inline-flex items-center gap-2 text-zinc-400">
            <span className="text-zinc-100">{it.ticker}</span>
            <span className={it.pos ? "text-cyan-300" : "text-rose-400"}>
              {it.pct}
            </span>
            <span className="text-zinc-700">•</span>
          </span>
        ))}
      </div>
      <style jsx>{`
        .ticker-track {
          animation: ticker 40s linear infinite;
          width: max-content;
        }
        @keyframes ticker {
          to {
            transform: translateX(-50%);
          }
        }
        @media (prefers-reduced-motion: reduce) {
          .ticker-track {
            animation: none;
          }
        }
      `}</style>
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────────────── */
/*  STATS                                                                      */
/* ────────────────────────────────────────────────────────────────────────── */

function Stats() {
  return (
    <section className="container mx-auto max-w-7xl px-6 py-16">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-px bg-cyan-400/15 rounded-lg overflow-hidden">
        {HEADLINE_STATS.map((s, i) => (
          <ScrollFade
            key={s.label}
            delayMs={i * 70}
            className="bg-gradient-to-br from-cyan-400/5 to-transparent backdrop-blur-sm"
          >
            <div className="px-6 py-7 hover:bg-cyan-400/8 transition-colors h-full">
              <p className="label-mono">{s.label}</p>
              <p
                className="mt-4 text-4xl sm:text-5xl font-bold tracking-tight text-white tabular-nums"
                style={{
                  fontFamily: "var(--font-grotesk)",
                  textShadow: "0 0 24px rgba(34,211,238,0.25)",
                }}
              >
                {s.value}
              </p>
              <p className="mt-2 text-xs text-zinc-500 font-mono">{s.hint}</p>
            </div>
          </ScrollFade>
        ))}
      </div>
    </section>
  );
}

/* ────────────────────────────────────────────────────────────────────────── */
/*  LEADERBOARD                                                                */
/* ────────────────────────────────────────────────────────────────────────── */

function Leaderboard({
  rows,
  warm,
}: {
  rows: AgentRow[] | null;
  warm: "checking" | "online" | "offline";
}) {
  return (
    <section className="container mx-auto max-w-7xl px-6 py-20">
      <ScrollFade>
        <Kicker>Leaderboard · full test window</Kicker>
        <h2
          className="mt-4 text-4xl sm:text-5xl font-bold tracking-tight text-white"
          style={{ fontFamily: "var(--font-grotesk)" }}
        >
          Eight agents, one benchmark
        </h2>
        <p className="mt-3 text-sm text-zinc-400 max-w-xl">
          Live data from the backend at{" "}
          <code className="rounded bg-cyan-400/10 px-1.5 py-0.5 font-mono text-[11px] text-cyan-300">
            {BACKEND_URL}
          </code>
          . If the backend is cold, the numbers above stay valid — they're
          baked into the page.
        </p>
      </ScrollFade>

      <ScrollFade delayMs={120}>
        <GlassPanel className="mt-10" innerClassName="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-cyan-400/15 text-left">
                <th className="px-5 py-3 label-mono text-zinc-500">#</th>
                <th className="px-5 py-3 label-mono text-zinc-500">Agent</th>
                <th className="px-5 py-3 label-mono text-zinc-500">Category</th>
                <th className="px-5 py-3 label-mono text-zinc-500 text-right">
                  Cum return
                </th>
                <th className="px-5 py-3 label-mono text-zinc-500 text-right">
                  Sharpe
                </th>
                <th className="px-5 py-3 label-mono text-zinc-500 text-right">
                  Steps
                </th>
                <th className="px-5 py-3"></th>
              </tr>
            </thead>
            <tbody className="font-mono text-[13px]">
              {(rows ?? PLACEHOLDER_ROWS).map((r, i) => (
                <tr
                  key={r.name}
                  className="border-b border-cyan-400/5 last:border-0 hover:bg-cyan-400/5 transition-colors"
                >
                  <td className="px-5 py-3 text-zinc-500 tabular-nums">
                    {String(i + 1).padStart(2, "0")}
                  </td>
                  <td className="px-5 py-3">
                    <span className="inline-flex items-center gap-2.5">
                      <span
                        className="h-2.5 w-2.5 rounded-full"
                        style={{
                          background: colorFor(r.name),
                          boxShadow: `0 0 8px ${colorFor(r.name)}`,
                        }}
                      />
                      <span className="text-zinc-100">{r.name}</span>
                    </span>
                  </td>
                  <td className="px-5 py-3 text-zinc-400">
                    {agentCategory(r.name)}
                  </td>
                  <td
                    className={`px-5 py-3 text-right tabular-nums ${
                      r.cum >= 0 ? "text-cyan-300" : "text-rose-400"
                    }`}
                  >
                    {r.cum >= 0 ? "+" : ""}
                    {(r.cum * 100).toFixed(2)}%
                  </td>
                  <td className="px-5 py-3 text-right tabular-nums text-zinc-200">
                    {r.sharpe.toFixed(2)}
                  </td>
                  <td className="px-5 py-3 text-right tabular-nums text-zinc-500">
                    {r.steps}
                  </td>
                  <td className="px-5 py-3 text-right">
                    <Link
                      href={`/agents/${r.name}`}
                      className="text-xs font-mono uppercase tracking-[0.12em] text-cyan-300 hover:text-cyan-100 link-glow"
                    >
                      View →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="px-5 py-3 text-xs text-zinc-500 font-mono">
            {warm === "checking" && "Polling backend…"}
            {warm === "online" && `Live · backend reachable at ${BACKEND_URL}`}
            {warm === "offline" &&
              `Backend offline · showing baked-in numbers. Start with uvicorn backend.main:app`}
          </p>
        </GlassPanel>
      </ScrollFade>
    </section>
  );
}

const PLACEHOLDER_ROWS: AgentRow[] = [
  { name: "buy_and_hold", cum: 1.0318, sharpe: 2.75, steps: 247 },
  { name: "equal_weight", cum: 0.5307, sharpe: 2.14, steps: 247 },
  { name: "multi_agent", cum: 0.5018, sharpe: 2.19, steps: 247 },
  { name: "ppo", cum: 0.4029, sharpe: 1.26, steps: 247 },
  { name: "zero_shot", cum: 0.0869, sharpe: 10.52, steps: 10 },
  { name: "single_agentic", cum: 0.0647, sharpe: 8.93, steps: 10 },
  { name: "ddpg", cum: 0.0107, sharpe: 0.05, steps: 247 },
  { name: "random", cum: -0.1032, sharpe: -0.45, steps: 247 },
];

/* ────────────────────────────────────────────────────────────────────────── */
/*  FEATURES + METHODOLOGY — extracted to FeatureTiles.tsx + MethodologyPipeline.tsx */
/* ────────────────────────────────────────────────────────────────────────── */

/* ────────────────────────────────────────────────────────────────────────── */
/*  CTA                                                                        */
/* ────────────────────────────────────────────────────────────────────────── */

function CallToAction() {
  return (
    <section className="container mx-auto max-w-7xl px-6 py-20">
      <ScrollFade>
        <GlassPanel glow="soft">
          <div className="p-10 sm:p-14 flex flex-col lg:flex-row gap-8 items-start lg:items-center justify-between">
            <div className="max-w-xl">
              <Kicker>Try it now</Kicker>
              <h2
                className="mt-4 text-3xl sm:text-4xl font-bold tracking-tight text-white"
                style={{ fontFamily: "var(--font-grotesk)" }}
              >
                Multi-agent debate in 30 seconds
              </h2>
              <p className="mt-3 text-sm text-zinc-400">
                Click run. Watch 8 LLM roles deliberate over today's VN30
                tickers and emit a final portfolio allocation. ~$0.05 per run.
                Streaming, not replay.
              </p>
            </div>
            <div className="flex flex-wrap gap-3">
              <Link
                href="/live"
                className="group inline-flex items-center gap-2 rounded-md bg-cyan-400 px-6 py-3.5 font-mono text-xs font-semibold uppercase tracking-[0.14em] text-black hover:bg-cyan-300 transition-all glow-cyan"
              >
                Open /live
                <Arrow />
              </Link>
              <Link
                href="/debate"
                className="inline-flex items-center gap-2 rounded-md border border-cyan-400/35 bg-cyan-400/5 px-6 py-3.5 font-mono text-xs font-semibold uppercase tracking-[0.14em] text-cyan-200 hover:border-cyan-400 hover:bg-cyan-400/10 transition-all"
              >
                Browse cached
                <Arrow />
              </Link>
            </div>
          </div>
        </GlassPanel>
      </ScrollFade>
    </section>
  );
}

