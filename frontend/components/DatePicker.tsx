"use client";

interface Props {
  dates: string[];
  value: string;
  onChange: (date: string) => void;
}

export function DatePicker({ dates, value, onChange }: Props) {
  return (
    <label className="inline-flex items-center gap-3 font-mono text-sm">
      <span className="label-mono">Decision date</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-md border border-cyan-400/30 bg-black/60 px-3 py-1.5 font-mono text-sm text-zinc-100 focus:border-cyan-400 focus:ring-2 focus:ring-cyan-400/40 focus:outline-none transition-colors"
      >
        {dates.map((d) => (
          <option key={d} value={d} className="bg-black text-zinc-100">
            {d}
          </option>
        ))}
      </select>
    </label>
  );
}
