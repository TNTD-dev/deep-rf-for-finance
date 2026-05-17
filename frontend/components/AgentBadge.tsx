"use client";

import { agentCategory } from "@/lib/colors";

interface Props {
  name: string;
}

const STYLES: Record<string, string> = {
  baseline: "bg-gray-100 text-gray-700",
  rl: "bg-blue-100 text-blue-800",
  llm: "bg-red-100 text-red-800",
};

export function AgentBadge({ name }: Props) {
  const cat = agentCategory(name);
  return (
    <span
      className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${STYLES[cat] ?? STYLES.baseline}`}
    >
      {cat.toUpperCase()}
    </span>
  );
}
