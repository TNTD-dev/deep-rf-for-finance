"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS: { href: string; label: string }[] = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/debate", label: "Debate" },
  { href: "/live", label: "Live" },
];

export function SiteNav() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-30 border-b border-cyan-400/15 backdrop-blur-md bg-black/60">
      <div className="container mx-auto max-w-7xl flex items-center gap-8 px-6 py-4">
        <Link href="/" className="flex items-center gap-2.5 group">
          <LogoMark />
          <span className="hidden sm:flex flex-col leading-none">
            <span
              className="font-bold tracking-tight text-white group-hover:text-cyan-300 transition-colors"
              style={{ fontFamily: "var(--font-grotesk)" }}
            >
              QuantArena
            </span>
            <span className="label-mono text-[10px] mt-0.5">
              8 agents · 1 benchmark · VN30
            </span>
          </span>
        </Link>

        <nav className="ml-auto flex items-center gap-1 text-sm">
          {LINKS.map((l) => {
            const active =
              pathname === l.href ||
              (l.href !== "/" && pathname?.startsWith(l.href));
            return (
              <Link
                key={l.href}
                href={l.href}
                className={[
                  "px-3 py-1.5 rounded-md font-mono text-xs uppercase tracking-[0.14em] link-glow",
                  active
                    ? "text-cyan-300 bg-cyan-500/10 ring-1 ring-cyan-400/25"
                    : "text-zinc-400 hover:text-cyan-300",
                ].join(" ")}
              >
                {l.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}

/** Hexagonal cyan logo mark — purely decorative. SVG so it scales clean. */
function LogoMark() {
  // Candlestick-inspired mark — three thin verticals with wicks above/below,
  // central one cyan-pulsed. Reads as trading at a glance instead of "generic
  // hex logo". 30×30 viewBox; pure SVG, no JS.
  return (
    <svg
      width="32"
      height="32"
      viewBox="0 0 32 32"
      fill="none"
      aria-hidden="true"
      className="text-cyan-400 drop-shadow-[0_0_8px_rgba(34,211,238,0.55)]"
    >
      {/* outer frame */}
      <rect
        x="1.5"
        y="1.5"
        width="29"
        height="29"
        rx="6"
        stroke="currentColor"
        strokeWidth="1.2"
        fill="rgba(34,211,238,0.06)"
      />
      {/* wick + body x3 — left bearish, center bullish (filled), right bullish */}
      <line x1="9" y1="7" x2="9" y2="25" stroke="currentColor" strokeWidth="1" opacity="0.6" />
      <rect x="7.5" y="14" width="3" height="8" fill="none" stroke="currentColor" strokeWidth="1.2" opacity="0.7" />
      <line x1="16" y1="5" x2="16" y2="27" stroke="currentColor" strokeWidth="1" />
      <rect x="14.5" y="9" width="3" height="14" fill="currentColor" />
      <line x1="23" y1="9" x2="23" y2="23" stroke="currentColor" strokeWidth="1" opacity="0.6" />
      <rect x="21.5" y="12" width="3" height="9" fill="none" stroke="currentColor" strokeWidth="1.2" opacity="0.7" />
    </svg>
  );
}
