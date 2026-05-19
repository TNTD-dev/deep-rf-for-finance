"use client";

import { colorFor } from "@/lib/colors";

interface Props {
  agents: string[];
  visible: Set<string>;
  onChange: (next: Set<string>) => void;
}

export function AgentToggle({ agents, visible, onChange }: Props) {
  return (
    <div className="flex flex-wrap gap-2">
      {agents.map((name) => {
        const on = visible.has(name);
        return (
          <button
            key={name}
            type="button"
            onClick={() => {
              const next = new Set(visible);
              if (on) next.delete(name);
              else next.add(name);
              onChange(next);
            }}
            className={`flex items-center gap-2 rounded-full border px-3 py-1 font-mono text-xs uppercase tracking-[0.08em] transition-colors ${
              on
                ? "bg-cyan-400/10 text-zinc-100"
                : "bg-transparent text-zinc-500 opacity-60 hover:opacity-100"
            }`}
            style={{ borderColor: on ? colorFor(name) : "rgba(34,211,238,0.18)" }}
          >
            <span
              className="inline-block h-2 w-2 rounded-full"
              style={{ backgroundColor: colorFor(name) }}
            />
            {name}
          </button>
        );
      })}
    </div>
  );
}
