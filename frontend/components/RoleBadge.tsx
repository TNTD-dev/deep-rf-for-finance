"use client";

import { roleColor } from "@/lib/colors";

interface Props {
  role: string;
  round?: number; // 1-based; only set for bull/bear in a debate sequence
}

export function RoleBadge({ role, round }: Props) {
  const color = roleColor(role);
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 font-mono text-[11px] font-semibold uppercase tracking-[0.05em]"
      style={{
        backgroundColor: `${color}1a`,
        color,
        boxShadow: `inset 0 0 0 1px ${color}40`,
      }}
    >
      <span
        className="inline-block h-1.5 w-1.5 rounded-full"
        style={{ backgroundColor: color, boxShadow: `0 0 6px ${color}` }}
      />
      {role}
      {round !== undefined && (
        <span className="rounded bg-black/40 px-1 text-[10px] font-semibold">
          R{round}
        </span>
      )}
    </span>
  );
}
