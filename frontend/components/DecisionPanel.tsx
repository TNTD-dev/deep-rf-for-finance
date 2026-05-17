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
      <p className="text-xs font-semibold text-gray-700">
        Portfolio weights (target allocation)
      </p>
      <div className="space-y-1.5">
        {entries.map(([ticker, weight]) => (
          <div key={ticker} className="flex items-center gap-3 text-sm">
            <span className="w-12 font-mono text-gray-700">{ticker}</span>
            <div className="h-5 flex-1 overflow-hidden rounded bg-gray-100">
              <div
                className="h-full transition-all"
                style={{
                  width: `${(Math.abs(weight) / maxWeight) * 100}%`,
                  backgroundColor: weight >= 0 ? "#10b981" : "#ef4444",
                }}
              />
            </div>
            <span className="w-16 text-right font-mono tabular-nums">
              {(weight * 100).toFixed(1)}%
            </span>
          </div>
        ))}
      </div>
      <details className="mt-2 text-xs text-gray-500">
        <summary className="cursor-pointer">Raw JSON</summary>
        <pre className="mt-1 rounded bg-gray-50 p-2 font-mono">
          {JSON.stringify(decision, null, 2)}
        </pre>
      </details>
    </div>
  );
}
