"use client";

import { useEffect, useRef, useState } from "react";

import { cn } from "@/lib/utils";

/**
 * Subtle fade-in + 16px translate when the element scrolls into view.
 * Respects prefers-reduced-motion (CSS handles the opt-out — see
 * .scroll-fade rule in globals.css).
 *
 * `delayMs` adds a staggered start so siblings can reveal in sequence:
 *   <ScrollFade delayMs={0}>card 1</ScrollFade>
 *   <ScrollFade delayMs={80}>card 2</ScrollFade>
 *   <ScrollFade delayMs={160}>card 3</ScrollFade>
 *
 * One-shot: once visible, never re-hides (no flicker on scroll back).
 */
export function ScrollFade({
  children,
  delayMs = 0,
  className,
  as: As = "div",
}: {
  children: React.ReactNode;
  delayMs?: number;
  className?: string;
  as?: keyof React.JSX.IntrinsicElements;
}) {
  const ref = useRef<HTMLElement | null>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    // Skip the observer entirely if motion is reduced — CSS already shows
    // content; this is just to avoid setting state pointlessly.
    if (
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    ) {
      setVisible(true);
      return;
    }
    const obs = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            setVisible(true);
            obs.disconnect();
            break;
          }
        }
      },
      { rootMargin: "0px 0px -10% 0px", threshold: 0.05 },
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  const Element = As as React.ElementType;
  return (
    <Element
      ref={ref}
      className={cn("scroll-fade", visible && "is-visible", className)}
      style={delayMs ? { transitionDelay: `${delayMs}ms` } : undefined}
    >
      {children}
    </Element>
  );
}
