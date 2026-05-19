"use client";

/**
 * TranscriptContent — renders a single transcript entry's body text.
 *
 * Routing logic:
 *   - If the content reads as per-ticker analysis (analysts mostly) → ticker
 *     grid: one glass card per ticker with setup body + verdict pill.
 *   - Otherwise → light markdown render (headings, bold, lists, fenced code,
 *     paragraphs) with inline highlighting for **bold** and numerics.
 *
 * No JS in render — both branches are pure mapping over the parser output.
 * The parser lives in lib/transcript.ts and is unit-testable independently.
 */

import {
  parseBlocks,
  parseTickerCards,
  type Block,
  type Sentiment,
  type Span,
  type TickerCard,
} from "@/lib/transcript";

const SENTIMENT_STYLES: Record<Sentiment, { ring: string; bg: string; text: string; dot: string }> = {
  bullish: {
    ring: "ring-cyan-400/45",
    bg: "bg-cyan-400/12",
    text: "text-cyan-200",
    dot: "bg-cyan-300",
  },
  bearish: {
    ring: "ring-rose-400/45",
    bg: "bg-rose-500/12",
    text: "text-rose-200",
    dot: "bg-rose-300",
  },
  neutral: {
    ring: "ring-zinc-400/35",
    bg: "bg-zinc-500/10",
    text: "text-zinc-200",
    dot: "bg-zinc-300",
  },
  mixed: {
    ring: "ring-amber-400/45",
    bg: "bg-amber-400/10",
    text: "text-amber-200",
    dot: "bg-amber-300",
  },
};

export function TranscriptContent({ content }: { content: string }) {
  if (!content?.trim()) {
    return (
      <p className="font-mono text-xs text-zinc-500">(no body content)</p>
    );
  }
  const cards = parseTickerCards(content);
  if (cards) return <TickerGrid cards={cards} />;
  const blocks = parseBlocks(content);
  return <BlockList blocks={blocks} />;
}

/* ───────────────────────── Ticker grid ─────────────────────────────────── */

function TickerGrid({ cards }: { cards: TickerCard[] }) {
  // .transcript-container + .transcript-ticker-grid switch columns based on
  // the parent container's width (container queries) instead of viewport —
  // so the same grid renders 3 cols on a wide /agents page and 1 col in a
  // narrow /debate sidecar.
  return (
    <div className="transcript-container">
      <div className="transcript-ticker-grid">
        {cards.map((c) => (
          <TickerCardView key={c.ticker} card={c} />
        ))}
      </div>
    </div>
  );
}

function TickerCardView({ card }: { card: TickerCard }) {
  const verdict = card.verdict;
  const style = verdict ? SENTIMENT_STYLES[verdict.sentiment] : null;
  return (
    <div
      className={`relative rounded-md border bg-black/55 backdrop-blur-sm p-4 transition-colors hover:bg-black/70 ${
        verdict ? `border-cyan-400/15 hover:border-cyan-400/35` : "border-cyan-400/15"
      }`}
    >
      <div className="flex items-center justify-between gap-2 mb-3">
        <div className="flex items-center gap-2">
          <span
            className="h-1.5 w-1.5 rounded-full bg-cyan-300"
            style={{ boxShadow: "0 0 6px rgba(34,211,238,0.8)" }}
          />
          <span
            className="font-mono text-sm font-bold tracking-[0.08em] text-white"
            style={{ fontFamily: "var(--font-jbm)" }}
          >
            {card.ticker}
          </span>
        </div>
        {verdict && style && (
          <span
            className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-[0.1em] ring-1 ${style.bg} ${style.ring} ${style.text}`}
          >
            <span className={`h-1.5 w-1.5 rounded-full ${style.dot}`} />
            {verdict.tag}
          </span>
        )}
      </div>
      {card.setupSpans.length > 0 && (
        <p className="text-sm leading-relaxed text-zinc-300">
          <SpanList spans={card.setupSpans} />
        </p>
      )}
      {verdict && verdict.rest.length > 0 && (
        <p className="mt-3 pt-3 border-t border-cyan-400/10 text-sm leading-relaxed text-zinc-400">
          <SpanList spans={verdict.rest} />
        </p>
      )}
      {card.extraSpans.length > 0 && (
        <p className="mt-3 text-xs leading-relaxed text-zinc-500">
          <SpanList spans={card.extraSpans} />
        </p>
      )}
    </div>
  );
}

/* ───────────────────────── Block list (free-form) ──────────────────────── */

function BlockList({ blocks }: { blocks: Block[] }) {
  return (
    <div className="space-y-3">
      {blocks.map((b, i) => (
        <BlockView key={i} block={b} />
      ))}
    </div>
  );
}

function BlockView({ block }: { block: Block }) {
  switch (block.kind) {
    case "heading":
      return block.level === 2 ? (
        <h4
          className="mt-2 font-semibold text-white text-base"
          style={{ fontFamily: "var(--font-grotesk)" }}
        >
          {block.text}
        </h4>
      ) : (
        <h5
          className="mt-1 font-semibold text-cyan-200 text-sm"
          style={{ fontFamily: "var(--font-grotesk)" }}
        >
          {block.text}
        </h5>
      );
    case "list":
      return (
        <ul className="space-y-1.5 pl-1">
          {block.items.map((spans, i) => (
            <li key={i} className="flex gap-2.5 text-sm text-zinc-300">
              <span className="mt-2 inline-block h-1 w-1 shrink-0 rounded-full bg-cyan-400/70" />
              <span className="flex-1 leading-relaxed">
                <SpanList spans={spans} />
              </span>
            </li>
          ))}
        </ul>
      );
    case "code":
      return (
        <pre className="overflow-x-auto rounded border border-cyan-400/15 bg-black/60 p-3 font-mono text-xs leading-relaxed text-zinc-300">
          {block.text}
        </pre>
      );
    case "paragraph":
      return (
        <p className="text-sm leading-relaxed text-zinc-300">
          <SpanList spans={block.spans} />
        </p>
      );
  }
}

/* ───────────────────────── Inline span renderer ────────────────────────── */

function SpanList({ spans }: { spans: Span[] }) {
  return (
    <>
      {spans.map((s, i) => (
        <SpanView key={i} span={s} />
      ))}
    </>
  );
}

function SpanView({ span }: { span: Span }) {
  switch (span.kind) {
    case "text":
      return <>{span.text}</>;
    case "bold":
      return <strong className="font-semibold text-white">{span.text}</strong>;
    case "code":
      return (
        <code className="rounded bg-cyan-400/10 px-1.5 py-0.5 font-mono text-[12px] text-cyan-300">
          {span.text}
        </code>
      );
    case "number": {
      const isPos = /^\+/.test(span.text);
      const isNeg = /^-/.test(span.text);
      const cls = isPos
        ? "text-cyan-300"
        : isNeg
          ? "text-rose-300"
          : "text-zinc-100";
      return (
        <span
          className={`font-mono tabular-nums ${cls}`}
          style={{ fontFamily: "var(--font-jbm)" }}
        >
          {span.text}
        </span>
      );
    }
  }
}
