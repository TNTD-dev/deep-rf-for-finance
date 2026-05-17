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
      className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium"
      style={{ backgroundColor: `${color}20`, color }}
    >
      <span
        className="inline-block h-1.5 w-1.5 rounded-full"
        style={{ backgroundColor: color }}
      />
      {role}
      {round !== undefined && (
        <span className="rounded bg-white/70 px-1 text-[10px] font-semibold">
          R{round}
        </span>
      )}
    </span>
  );
}
