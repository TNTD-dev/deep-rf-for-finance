"use client";

interface Props {
  dates: string[];
  value: string;
  onChange: (date: string) => void;
}

export function DatePicker({ dates, value, onChange }: Props) {
  return (
    <label className="inline-flex items-center gap-2 text-sm">
      <span className="text-gray-700">Decision date:</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded border border-gray-300 bg-white px-2 py-1 text-sm focus:ring-2 focus:ring-blue-300 focus:outline-none"
      >
        {dates.map((d) => (
          <option key={d} value={d}>
            {d}
          </option>
        ))}
      </select>
    </label>
  );
}
