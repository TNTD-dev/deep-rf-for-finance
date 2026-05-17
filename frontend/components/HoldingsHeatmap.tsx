"use client";

import type { BacktestPayload } from "@/lib/types";

interface Props {
  payload: BacktestPayload;
}

const CELL_W = 5;
const CELL_H = 28;
const LABEL_W = 50;
const FILL = "#059669"; // emerald-600

export function HoldingsHeatmap({ payload }: Props) {
  const first = payload.holdings[0];
  const tickers = first ? Object.keys(first).filter((k) => k !== "date") : [];

  if (tickers.length === 0 || payload.holdings.length === 0) {
    return <p className="text-sm text-gray-500">No holdings data.</p>;
  }

  const dates = payload.holdings.map((h) => String(h.date));
  const N = dates.length;

  // Per-ticker max — each row normalized independently so VCB's smaller
  // absolute share count doesn't wash out next to HPG's larger one.
  const perTickerMax: Record<string, number> = {};
  for (const t of tickers) {
    let m = 0;
    for (const row of payload.holdings) {
      const v = Number(row[t] ?? 0);
      if (v > m) m = v;
    }
    perTickerMax[t] = m || 1;
  }

  const totalW = LABEL_W + N * CELL_W;
  const totalH = tickers.length * CELL_H;

  return (
    <div className="overflow-x-auto">
      <svg width={totalW} height={totalH + 18} className="text-xs">
        {tickers.map((t, row) => (
          <g key={t}>
            <text
              x={0}
              y={row * CELL_H + CELL_H / 2 + 4}
              fontSize="11"
              fill="#374151"
            >
              {t}
            </text>
            {payload.holdings.map((h, i) => {
              const v = Number(h[t] ?? 0);
              const opacity = v / perTickerMax[t];
              return (
                <rect
                  key={`${t}-${i}`}
                  x={LABEL_W + i * CELL_W}
                  y={row * CELL_H}
                  width={CELL_W}
                  height={CELL_H - 1}
                  fill={FILL}
                  fillOpacity={opacity}
                >
                  <title>{`${t} on ${h.date}: ${v.toLocaleString()} shares`}</title>
                </rect>
              );
            })}
          </g>
        ))}
        {dates.map((d, i) =>
          i % 21 === 0 ? (
            <text
              key={`${d}-${i}`}
              x={LABEL_W + i * CELL_W}
              y={totalH + 14}
              fontSize="10"
              fill="#6b7280"
            >
              {d.slice(0, 7)}
            </text>
          ) : null,
        )}
      </svg>
      <p className="mt-2 text-xs text-gray-500">
        Color intensity = share count, normalized per ticker (each row scales
        to its own max so smaller-priced tickers stay visible). Hover a cell
        for the exact count.
      </p>
    </div>
  );
}
