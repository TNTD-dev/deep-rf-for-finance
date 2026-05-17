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
            className={`flex items-center gap-2 rounded-full border px-3 py-1 text-sm transition ${
              on ? "bg-white" : "bg-gray-100 opacity-50"
            }`}
            style={{ borderColor: colorFor(name) }}
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
