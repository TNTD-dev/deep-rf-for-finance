"use client";

interface Props {
  decision: Record<string, number>;
}

export function DecisionPanel({ decision }: Props) {
  const entries = Object.entries(decision);
  // Guard div-by-zero when all weights are 0 (defensive).
  const maxWeight = Math.max(...entries.map(([, v]) => Math.abs(v)), 0.0001);

  return (
    <div className="space-y-2">
      <p className="label-mono">Portfolio weights · target allocation</p>
      <div className="space-y-1.5">
        {entries.map(([ticker, weight]) => (
          <div key={ticker} className="flex items-center gap-3 text-sm">
            <span className="w-12 font-mono text-zinc-300">{ticker}</span>
            <div className="h-5 flex-1 overflow-hidden rounded bg-white/5 ring-1 ring-cyan-400/15">
              <div
                className="h-full transition-all"
                style={{
                  width: `${(Math.abs(weight) / maxWeight) * 100}%`,
                  background:
                    weight >= 0
                      ? "linear-gradient(90deg, #22d3ee, #06b6d4)"
                      : "linear-gradient(90deg, #f87171, #dc2626)",
                  boxShadow:
                    weight >= 0
                      ? "0 0 12px rgba(34,211,238,0.45)"
                      : "0 0 12px rgba(220,38,38,0.4)",
                }}
              />
            </div>
            <span
              className={`w-16 text-right font-mono tabular-nums ${
                weight >= 0 ? "text-cyan-300" : "text-rose-400"
              }`}
            >
              {(weight * 100).toFixed(1)}%
            </span>
          </div>
        ))}
      </div>
      <details className="mt-2 text-xs text-zinc-500">
        <summary className="cursor-pointer font-mono uppercase tracking-[0.08em] text-zinc-500 hover:text-cyan-300 transition-colors">
          Raw JSON
        </summary>
        <pre className="mt-2 rounded border border-cyan-400/15 bg-black/50 p-3 font-mono text-zinc-300">
          {JSON.stringify(decision, null, 2)}
        </pre>
      </details>
    </div>
  );
}
