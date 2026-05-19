import { cn } from "@/lib/utils";

/**
 * Glass surface with a 1px gradient-border shell + inner blurred panel.
 *
 * Per DESIGN.md §"Elevation & Depth" — glass is the primary depth language;
 * the gradient shell reads as a hairline frame instead of a flat stroke.
 * Two-element layout so the border gradient and inner background are both
 * controllable without conflicting backdrop-filter contexts.
 *
 * Usage:
 *   <GlassPanel className="p-6">…</GlassPanel>
 *   <GlassPanel glow="strong" as="article">…</GlassPanel>
 *
 * `glow` adds a soft cyan outer ring. Reserved for hero CTAs + the most
 * emphasized surface on a page — use sparingly.
 */
export function GlassPanel({
  children,
  className,
  innerClassName,
  glow,
  as: As = "div",
  ...rest
}: {
  children: React.ReactNode;
  className?: string;
  innerClassName?: string;
  glow?: "soft" | "strong";
  as?: keyof React.JSX.IntrinsicElements;
} & React.HTMLAttributes<HTMLElement>) {
  const Element = As as React.ElementType;
  return (
    <Element className={cn("glass-shell", className)} {...rest}>
      <div
        className={cn(
          "glass-inner",
          glow === "soft" && "glow-cyan",
          glow === "strong" && "glow-cyan-strong",
          innerClassName,
        )}
      >
        {children}
      </div>
    </Element>
  );
}

/**
 * Mono kicker label — DESIGN.md `label-md` (12px, weight 600, tracking 1.2px,
 * uppercase, cyan tint). Use above headlines or as section markers.
 */
export function Kicker({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <p className={cn("label-mono", className)}>{children}</p>;
}
