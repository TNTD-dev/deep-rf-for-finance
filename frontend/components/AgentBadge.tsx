"use client";

import { agentCategory } from "@/lib/colors";

interface Props {
  name: string;
}

const STYLES: Record<string, string> = {
  baseline: "bg-zinc-500/10 text-zinc-400 ring-zinc-500/25",
  rl: "bg-sky-400/10 text-sky-300 ring-sky-400/30",
  llm: "bg-cyan-400/15 text-cyan-200 ring-cyan-400/40",
};

export function AgentBadge({ name }: Props) {
  const cat = agentCategory(name);
  return (
    <span
      className={`inline-block rounded-full px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-[0.12em] ring-1 ${STYLES[cat] ?? STYLES.baseline}`}
    >
      {cat}
    </span>
  );
}
