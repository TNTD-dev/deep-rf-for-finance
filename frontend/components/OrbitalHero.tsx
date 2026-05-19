"use client";

/**
 * OrbitalHero — animated SVG visualization for the landing page.
 *
 * Composition:
 *   - Central glowing core (the "arena")
 *   - 3 nested orbital rings rotating at different speeds
 *   - 8 agent dots distributed across rings (3 baselines outer, 2 RL middle,
 *     3 LLM inner — visually maps the taxonomy in lib/colors.ts)
 *   - Faint ticker codes (VCB / FPT / HPG / VIC / VNM) drifting upward
 *   - Connection lines from core to each agent dot, pulsing
 *
 * Pure SVG + CSS animations. No JS animation loop → no jank, GPU-accelerated.
 * Reduced-motion: animations auto-pause via @media query in the stylesheet
 * block at the bottom.
 */

import { AGENT_COLORS } from "@/lib/colors";

const RING_AGENTS: { ring: 0 | 1 | 2; name: string; angle: number }[] = [
  // Inner ring (LLM — the headline)
  { ring: 0, name: "multi_agent", angle: 90 },
  { ring: 0, name: "single_agentic", angle: 210 },
  { ring: 0, name: "zero_shot", angle: 330 },
  // Middle ring (RL)
  { ring: 1, name: "ppo", angle: 60 },
  { ring: 1, name: "ddpg", angle: 240 },
  // Outer ring (baselines)
  { ring: 2, name: "buy_and_hold", angle: 30 },
  { ring: 2, name: "equal_weight", angle: 150 },
  { ring: 2, name: "random", angle: 270 },
];

const RING_RADII = [78, 140, 210]; // px
const TICKERS = ["VCB", "FPT", "HPG", "VIC", "VNM"];

function polar(r: number, deg: number): { x: number; y: number } {
  // Round to 2 decimals so the serialized transform string is identical
  // between SSR (Node V8) and CSR (browser V8). Math.cos / Math.sin can
  // diverge in the last fractional digit across engines, which Next 16
  // reports as a hydration mismatch on the orbital dot transforms.
  const rad = (deg - 90) * (Math.PI / 180);
  return {
    x: Math.round(r * Math.cos(rad) * 100) / 100,
    y: Math.round(r * Math.sin(rad) * 100) / 100,
  };
}

export function OrbitalHero() {
  return (
    <div className="relative h-[460px] sm:h-[520px] flex items-center justify-center select-none">
      {/* Deep glow halo behind the whole composition */}
      <div
        aria-hidden
        className="absolute inset-0 blur-3xl opacity-60"
        style={{
          background:
            "radial-gradient(circle at center, rgba(34,211,238,0.25), transparent 55%)",
        }}
      />

      <svg
        viewBox="-260 -260 520 520"
        className="relative h-full w-full max-w-[560px]"
        aria-hidden
      >
        <defs>
          <radialGradient id="core-glow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#67e8f9" stopOpacity="1" />
            <stop offset="60%" stopColor="#22d3ee" stopOpacity="0.6" />
            <stop offset="100%" stopColor="#22d3ee" stopOpacity="0" />
          </radialGradient>
          <linearGradient id="ring-stroke" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#22d3ee" stopOpacity="0.0" />
            <stop offset="50%" stopColor="#22d3ee" stopOpacity="0.6" />
            <stop offset="100%" stopColor="#22d3ee" stopOpacity="0.0" />
          </linearGradient>
        </defs>

        {/* Orbital rings — each rotates at a different speed (CSS @keyframes
            below), so the dots placed on them appear to revolve. */}
        {RING_RADII.map((r, i) => (
          <g
            key={r}
            className={`orbit orbit-${i}`}
            style={{ transformOrigin: "0 0" }}
          >
            <circle
              cx="0"
              cy="0"
              r={r}
              fill="none"
              stroke="url(#ring-stroke)"
              strokeWidth={1}
              strokeDasharray="2 6"
              opacity={0.55}
            />
            {RING_AGENTS.filter((a) => a.ring === i).map((a) => {
              const { x, y } = polar(r, a.angle);
              const color = AGENT_COLORS[a.name] ?? "#22d3ee";
              return (
                <g key={a.name} transform={`translate(${x}, ${y})`}>
                  {/* Subtle halo behind the dot */}
                  <circle
                    r={11}
                    fill={color}
                    opacity={0.22}
                  />
                  <circle
                    r={5}
                    fill={color}
                    style={{
                      filter: `drop-shadow(0 0 6px ${color})`,
                    }}
                  />
                </g>
              );
            })}
          </g>
        ))}

        {/* Faint connection lines core → ring midpoints (decorative) */}
        {[0, 60, 120, 180, 240, 300].map((deg) => {
          const { x, y } = polar(210, deg);
          return (
            <line
              key={deg}
              x1="0"
              y1="0"
              x2={x}
              y2={y}
              stroke="#22d3ee"
              strokeOpacity={0.08}
              strokeWidth={1}
            />
          );
        })}

        {/* Central core — pulses */}
        <g className="core-pulse" style={{ transformOrigin: "0 0" }}>
          <circle cx="0" cy="0" r="46" fill="url(#core-glow)" />
          <circle
            cx="0"
            cy="0"
            r="22"
            fill="#22d3ee"
            opacity="0.85"
            style={{ filter: "drop-shadow(0 0 16px #22d3ee)" }}
          />
          <circle cx="0" cy="0" r="6" fill="#000" />
        </g>

        {/* Floating tickers — 5 codes drift up around the composition */}
        {TICKERS.map((t, i) => {
          const angle = (i / TICKERS.length) * 360;
          const { x, y } = polar(248, angle);
          return (
            <text
              key={t}
              x={x}
              y={y}
              className="ticker-drift"
              style={{ animationDelay: `${i * 0.4}s` }}
              fill="#67e8f9"
              fillOpacity={0.5}
              fontSize="11"
              fontFamily="var(--font-jbm)"
              textAnchor="middle"
              dominantBaseline="middle"
            >
              {t}
            </text>
          );
        })}
      </svg>

      {/* Floating side stats — emphasize the trading context */}
      <FloatingStat
        className="left-1 top-12 sm:left-6"
        label="Sharpe"
        value="2.19"
      />
      <FloatingStat
        className="right-1 top-20 sm:right-6"
        label="Return"
        value="+50.18%"
      />
      <FloatingStat
        className="left-4 bottom-12"
        label="Decisions"
        value="51"
      />
      <FloatingStat
        className="right-4 bottom-16"
        label="Cost"
        value="$3.21"
      />

      <style jsx>{`
        :global(.orbit-0) {
          animation: spin 32s linear infinite;
        }
        :global(.orbit-1) {
          animation: spin-reverse 48s linear infinite;
        }
        :global(.orbit-2) {
          animation: spin 72s linear infinite;
        }
        :global(.core-pulse) {
          animation: pulse 3.4s ease-in-out infinite;
        }
        :global(.ticker-drift) {
          animation: drift 8s ease-in-out infinite;
        }
        @keyframes spin {
          to {
            transform: rotate(360deg);
          }
        }
        @keyframes spin-reverse {
          to {
            transform: rotate(-360deg);
          }
        }
        @keyframes pulse {
          0%,
          100% {
            transform: scale(1);
            opacity: 1;
          }
          50% {
            transform: scale(1.08);
            opacity: 0.92;
          }
        }
        @keyframes drift {
          0%,
          100% {
            transform: translateY(0);
            opacity: 0.4;
          }
          50% {
            transform: translateY(-6px);
            opacity: 0.75;
          }
        }
        @media (prefers-reduced-motion: reduce) {
          :global(.orbit-0),
          :global(.orbit-1),
          :global(.orbit-2),
          :global(.core-pulse),
          :global(.ticker-drift) {
            animation: none;
          }
        }
      `}</style>
    </div>
  );
}

function FloatingStat({
  label,
  value,
  className,
}: {
  label: string;
  value: string;
  className?: string;
}) {
  return (
    <div
      className={`pointer-events-none absolute hidden md:flex flex-col items-start gap-0.5 ${className ?? ""}`}
    >
      <span className="label-mono text-[9px] text-cyan-300/70">{label}</span>
      <span
        className="font-mono text-base font-semibold text-white tabular-nums"
        style={{ textShadow: "0 0 12px rgba(34,211,238,0.5)" }}
      >
        {value}
      </span>
    </div>
  );
}
