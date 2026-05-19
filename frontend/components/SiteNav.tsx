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
        <Link href="/" className="flex items-center gap-2 group">
          <LogoMark />
          <span className="hidden sm:flex flex-col leading-none">
            <span className="font-semibold tracking-tight text-white group-hover:text-cyan-300 transition-colors">
              Intelligence Core
            </span>
            <span className="label-mono text-[10px]">DRL × LLM · VN30</span>
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
  return (
    <svg
      width="32"
      height="32"
      viewBox="0 0 32 32"
      fill="none"
      aria-hidden="true"
      className="text-cyan-400 drop-shadow-[0_0_8px_rgba(34,211,238,0.55)]"
    >
      <path
        d="M16 2.5L27.5 9v14L16 29.5 4.5 23V9L16 2.5z"
        stroke="currentColor"
        strokeWidth="1.4"
        fill="rgba(34,211,238,0.08)"
      />
      <path
        d="M16 9.5L22 13v6l-6 3.5L10 19v-6l6-3.5z"
        stroke="currentColor"
        strokeWidth="1.2"
        fill="none"
        opacity="0.7"
      />
      <circle cx="16" cy="16" r="1.6" fill="currentColor" />
    </svg>
  );
}
