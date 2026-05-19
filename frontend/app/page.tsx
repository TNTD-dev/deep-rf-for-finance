"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ScrollFade } from "@/components/ScrollFade";
import { GlassPanel, Kicker } from "@/components/ui/glass";
import { BACKEND_URL, getAgents, getBacktest } from "@/lib/api";
import { agentCategory, colorFor } from "@/lib/colors";
import type { BacktestPayload } from "@/lib/types";

// Headline numbers Người 1 cites in the report. Hard-coded so the landing
// page renders immediately even when the backend is cold or unreachable.
const HEADLINE_STATS: { label: string; value: string; hint: string }[] = [
  { label: "Agents benchmarked", value: "8", hint: "3 baselines · 2 RL · 3 LLM" },
  { label: "Test window", value: "248", hint: "trading sessions 2025-05 → 2026-04" },
  { label: "Multi-agent return", value: "+50.18%", hint: "Sharpe 2.19 · 51 weekly decisions" },
  { label: "LLM cost", value: "$3.21", hint: "full backtest, gpt-4o + gpt-4o-mini" },
];

const FEATURES: { title: string; body: string; tag: string }[] = [
  {
    tag: "01 · Reinforcement Learning",
    title: "DDPG + PPO on a custom VN env",
    body: "Stable-baselines3 trained on 5 years of VN30 prices with HOSE rules baked in: ±7% price band, 100-share lots, asymmetric 0.15% / 0.25% fees. PPO is the headline RL agent at +40.29%.",
  },
  {
    tag: "02 · LLM Trading",
    title: "Zero-shot → agentic → multi-agent",
    body: "Three increasingly capable LLM patterns. Multi-agent runs an 8-role LangGraph: three analysts, a bull/bear debate, trader, risk manager, portfolio manager. Decisions are weekly, replayable, cached.",
  },
  {
    tag: "03 · Live Mode",
    title: "Watch agents reason in real time",
    body: "Click run. The multi-agent system streams agent_start / agent_complete / decision events via SSE — 8 role cards light up sequentially, ~30-60 seconds total, ~$0.05 per click. No replay, no recording.",
  },
  {
    tag: "04 · Honest Comparison",
    title: "Same env, same fees, same window",
    body: "Every agent runs through the same gymnasium env. No lookahead — news on day D is only visible from D+1 close. Person 2 verifies the invariants on every PR. Reproducible: same seed → identical trajectory.",
  },
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
      <Stats />
      <Leaderboard rows={rows} warm={warm} />
      <Features />
      <CallToAction />
      <Footer />
    </main>
  );
}

/* ────────────────────────────────────────────────────────────────────────── */
/*  HERO                                                                       */
/* ────────────────────────────────────────────────────────────────────────── */

function Hero() {
  return (
    <section className="relative overflow-hidden">
      {/* Soft cyan orb behind hero */}
      <div
        aria-hidden
        className="pointer-events-none absolute left-1/2 top-[-20%] h-[600px] w-[900px] -translate-x-1/2 rounded-full blur-3xl"
        style={{
          background:
            "radial-gradient(circle, rgba(34,211,238,0.18), transparent 60%)",
        }}
      />
      <div className="container mx-auto max-w-6xl px-6 pt-16 pb-20 sm:pt-24 sm:pb-28 relative">
        <ScrollFade>
          <Kicker>Intelligence Core · Nexora Systems</Kicker>
        </ScrollFade>
        <ScrollFade delayMs={80}>
          <h1 className="display-xl mt-6 text-white max-w-4xl">
            Can <span className="text-cyan-300">LLM agents</span> trade as well
            as deep <span className="text-cyan-300">reinforcement learning</span>?
          </h1>
        </ScrollFade>
        <ScrollFade delayMs={160}>
          <p className="mt-7 max-w-2xl text-base sm:text-lg leading-relaxed text-zinc-400">
            Eight agents — classical baselines, DDPG &amp; PPO,
            zero-shot LLM, single-agentic, and an 8-role multi-agent debate
            system — all benchmarked head-to-head on the Vietnamese VN30
            market across a full 12-month out-of-sample window.
          </p>
        </ScrollFade>
        <ScrollFade delayMs={240}>
          <div className="mt-10 flex flex-wrap items-center gap-3">
            <Link
              href="/dashboard"
              className="group inline-flex items-center gap-2 rounded-md bg-cyan-400 px-5 py-3 font-mono text-xs font-semibold uppercase tracking-[0.14em] text-black transition-all hover:bg-cyan-300 glow-cyan"
            >
              Open Dashboard
              <Arrow />
            </Link>
            <Link
              href="/live"
              className="inline-flex items-center gap-2 rounded-md border border-cyan-400/30 px-5 py-3 font-mono text-xs font-semibold uppercase tracking-[0.14em] text-cyan-200 transition-all hover:border-cyan-400 hover:text-cyan-100 hover:bg-cyan-400/5"
            >
              Run multi-agent live
              <Arrow />
            </Link>
            <Link
              href="/debate"
              className="font-mono text-xs uppercase tracking-[0.14em] text-zinc-400 hover:text-cyan-300 link-glow px-2 py-3"
            >
              · Replay a debate
            </Link>
          </div>
        </ScrollFade>
      </div>
    </section>
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
/*  STATS                                                                      */
/* ────────────────────────────────────────────────────────────────────────── */

function Stats() {
  return (
    <section className="border-y border-cyan-400/10 bg-black/30 backdrop-blur-sm">
      <div className="container mx-auto max-w-6xl px-6 py-10 grid grid-cols-2 lg:grid-cols-4 gap-px bg-cyan-400/10">
        {HEADLINE_STATS.map((s, i) => (
          <ScrollFade key={s.label} delayMs={i * 60} className="bg-black/70">
            <div className="px-5 py-6">
              <p className="label-mono">{s.label}</p>
              <p className="mt-3 text-3xl sm:text-4xl font-semibold tracking-tight text-white">
                {s.value}
              </p>
              <p className="mt-2 text-xs text-zinc-500">{s.hint}</p>
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
    <section className="container mx-auto max-w-6xl px-6 py-20">
      <ScrollFade>
        <Kicker>Leaderboard · full test window</Kicker>
        <h2 className="mt-4 text-3xl sm:text-4xl font-semibold tracking-tight text-white">
          Eight agents, one benchmark
        </h2>
        <p className="mt-3 text-sm text-zinc-400 max-w-xl">
          Live data from the backend at{" "}
          <code className="rounded bg-cyan-400/10 px-1.5 py-0.5 font-mono text-[11px] text-cyan-300">
            {BACKEND_URL}
          </code>
          . If the backend is cold, headline numbers above stay valid — they're
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
                  <td className="px-5 py-3 text-zinc-500">{i + 1}</td>
                  <td className="px-5 py-3">
                    <span className="inline-flex items-center gap-2">
                      <span
                        className="h-2 w-2 rounded-full"
                        style={{ background: colorFor(r.name) }}
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
          <p className="px-5 py-3 text-xs text-zinc-500">
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

// Static fallback so the leaderboard never renders empty even if the backend
// is cold. Matches PKG-S full-window results (multi_agent: 51 LLM decisions,
// 247 env steps; LLM smoke at 10 sessions).
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
/*  FEATURES                                                                   */
/* ────────────────────────────────────────────────────────────────────────── */

function Features() {
  return (
    <section className="container mx-auto max-w-6xl px-6 py-20">
      <ScrollFade>
        <Kicker>System overview</Kicker>
        <h2 className="mt-4 text-3xl sm:text-4xl font-semibold tracking-tight text-white">
          Four layers, one comparison
        </h2>
      </ScrollFade>

      <div className="mt-12 grid gap-6 sm:grid-cols-2">
        {FEATURES.map((f, i) => (
          <ScrollFade key={f.title} delayMs={i * 80}>
            <GlassPanel className="h-full">
              <div className="p-7">
                <p className="label-mono">{f.tag}</p>
                <h3 className="mt-4 text-xl font-semibold text-white">
                  {f.title}
                </h3>
                <p className="mt-3 text-sm leading-relaxed text-zinc-400">
                  {f.body}
                </p>
              </div>
            </GlassPanel>
          </ScrollFade>
        ))}
      </div>
    </section>
  );
}

/* ────────────────────────────────────────────────────────────────────────── */
/*  CTA                                                                        */
/* ────────────────────────────────────────────────────────────────────────── */

function CallToAction() {
  return (
    <section className="container mx-auto max-w-6xl px-6 py-20">
      <ScrollFade>
        <GlassPanel glow="soft">
          <div className="p-10 sm:p-14 flex flex-col lg:flex-row gap-8 items-start lg:items-center justify-between">
            <div className="max-w-xl">
              <Kicker>Try it now</Kicker>
              <h2 className="mt-4 text-2xl sm:text-3xl font-semibold tracking-tight text-white">
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
                className="group inline-flex items-center gap-2 rounded-md bg-cyan-400 px-5 py-3 font-mono text-xs font-semibold uppercase tracking-[0.14em] text-black hover:bg-cyan-300 transition-all"
              >
                Open /live
                <Arrow />
              </Link>
              <Link
                href="/debate"
                className="inline-flex items-center gap-2 rounded-md border border-cyan-400/30 px-5 py-3 font-mono text-xs font-semibold uppercase tracking-[0.14em] text-cyan-200 hover:border-cyan-400 hover:bg-cyan-400/5 transition-all"
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

/* ────────────────────────────────────────────────────────────────────────── */
/*  FOOTER                                                                     */
/* ────────────────────────────────────────────────────────────────────────── */

function Footer() {
  return (
    <footer className="border-t border-cyan-400/10 mt-10">
      <div className="container mx-auto max-w-6xl px-6 py-8 flex flex-wrap items-center gap-4 justify-between">
        <p className="label-mono text-zinc-500">
          Intelligence Core · DRL × LLM × VN30
        </p>
        <p className="text-xs text-zinc-500 font-mono">
          Backend{" "}
          <code className="rounded bg-cyan-400/10 px-1.5 py-0.5 text-cyan-300">
            {BACKEND_URL}
          </code>{" "}
          · Next.js 16 · Tailwind v4 · Recharts · FastAPI · LangGraph
        </p>
      </div>
    </footer>
  );
}
