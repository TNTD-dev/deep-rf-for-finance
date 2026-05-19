/**
 * Lightweight markdown parser tuned for QuantArena debate transcripts.
 *
 * Real markdown libs (react-markdown, marked) are 30-100KB minified. The
 * content shape here is constrained — headings, bold, lists, fenced code,
 * paragraphs — and we want first-class rendering of two domain primitives:
 *
 *   1. **Per-ticker analysis**: analyst outputs are `## TICKER\nSetup:…\nNhận định: **verdict** — …` repeated.
 *      We surface these as a grid of ticker cards instead of a vertical wall.
 *   2. **Inline numerics**: RSI z-scores, MACD readings, percentages.
 *      We tag them with the `Span.kind === "number"` so the renderer can
 *      stylize without re-running regex at render time.
 *
 * Pure functions, no React, easy to unit-test.
 */

export type Span =
  | { kind: "text"; text: string }
  | { kind: "bold"; text: string }
  | { kind: "code"; text: string }
  | { kind: "number"; text: string };

export type Block =
  | { kind: "heading"; level: 2 | 3; text: string }
  | { kind: "paragraph"; spans: Span[] }
  | { kind: "list"; items: Span[][] }
  | { kind: "code"; text: string; lang?: string };

/** Match a `## VCB`-style ticker header (1 uppercase word, optionally digits). */
const TICKER_HEADER_RE = /^##\s+([A-Z][A-Z0-9]{1,5})\s*$/;

/** Detect inline tokens: `**bold**`, `` `code` ``, numbers with optional ± and unit. */
const TOKEN_RE =
  /(\*\*[^*]+\*\*)|(`[^`]+`)|([+\-±]?\d+(?:[.,]\d+)?(?:%|x|s|B|M|K)?)/g;

export type TickerCard = {
  ticker: string;
  setupSpans: Span[];
  verdict: { tag: string; sentiment: Sentiment; rest: Span[] } | null;
  extraSpans: Span[]; // any other lines that aren't Setup / Nhận định
};

export type Sentiment = "bullish" | "bearish" | "neutral" | "mixed";

/**
 * Split a transcript entry into either a list of ticker cards (when the
 * content reads as per-ticker analysis) or a generic Block[] for free-form
 * prose. Returns `null` if there are no ticker headers — the caller falls
 * back to {@link parseBlocks}.
 */
export function parseTickerCards(content: string): TickerCard[] | null {
  if (!content) return null;
  // Pre-process: strip a leading ```markdown fence if present (fundamental
  // analyst sometimes wraps the whole thing in one).
  const stripped = content.replace(/^```(?:markdown)?\n([\s\S]*?)\n```$/, "$1");
  const lines = stripped.split("\n");

  // First pass: do we have ≥ 2 ticker headers? If not, bail.
  const tickerHeaderIndices: number[] = [];
  lines.forEach((l, i) => {
    if (TICKER_HEADER_RE.test(l.trim())) tickerHeaderIndices.push(i);
  });
  if (tickerHeaderIndices.length < 2) return null;

  const cards: TickerCard[] = [];
  for (let h = 0; h < tickerHeaderIndices.length; h++) {
    const start = tickerHeaderIndices[h];
    const end =
      h + 1 < tickerHeaderIndices.length
        ? tickerHeaderIndices[h + 1]
        : lines.length;
    const headerMatch = lines[start].trim().match(TICKER_HEADER_RE);
    if (!headerMatch) continue;
    const ticker = headerMatch[1];
    const body = lines.slice(start + 1, end);

    let setupText = "";
    let verdict: TickerCard["verdict"] = null;
    const extra: string[] = [];

    let i = 0;
    while (i < body.length) {
      const line = body[i].trim();
      if (!line) {
        i++;
        continue;
      }
      // Setup paragraph may span multiple lines until the next labelled line.
      if (/^Setup:/i.test(line)) {
        const parts: string[] = [line.replace(/^Setup:\s*/i, "")];
        i++;
        while (
          i < body.length &&
          body[i].trim() &&
          !/^Nhận định:/i.test(body[i].trim()) &&
          !/^[A-Z][^:]{1,30}:/.test(body[i].trim())
        ) {
          parts.push(body[i].trim());
          i++;
        }
        setupText = parts.join(" ").trim();
        continue;
      }
      const vm = line.match(/^Nhận định:\s*\*\*([^*]+)\*\*\s*(?:—|--)?\s*(.*)$/i);
      if (vm) {
        verdict = {
          tag: vm[1].trim(),
          sentiment: classifySentiment(vm[1]),
          rest: parseInline(vm[2].trim()),
        };
        i++;
        continue;
      }
      extra.push(line);
      i++;
    }

    cards.push({
      ticker,
      setupSpans: parseInline(setupText),
      verdict,
      extraSpans: extra.length ? parseInline(extra.join(" ")) : [],
    });
  }
  return cards;
}

/** Generic block parser — used when content isn't a per-ticker analysis. */
export function parseBlocks(content: string): Block[] {
  if (!content) return [];
  const stripped = content.replace(/^```(?:markdown)?\n([\s\S]*?)\n```$/, "$1");
  const lines = stripped.split("\n");
  const blocks: Block[] = [];

  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const trim = line.trim();

    // Fenced code block
    if (/^```/.test(trim)) {
      const lang = trim.replace(/^```/, "").trim() || undefined;
      i++;
      const buf: string[] = [];
      while (i < lines.length && !/^```/.test(lines[i].trim())) {
        buf.push(lines[i]);
        i++;
      }
      i++; // skip closing ```
      blocks.push({ kind: "code", text: buf.join("\n"), lang });
      continue;
    }

    // Heading
    const h2 = trim.match(/^##\s+(.+)$/);
    if (h2) {
      blocks.push({ kind: "heading", level: 2, text: h2[1].trim() });
      i++;
      continue;
    }
    const h3 = trim.match(/^###\s+(.+)$/);
    if (h3) {
      blocks.push({ kind: "heading", level: 3, text: h3[1].trim() });
      i++;
      continue;
    }

    // List
    if (/^[-*]\s+/.test(trim)) {
      const items: Span[][] = [];
      while (i < lines.length && /^[-*]\s+/.test(lines[i].trim())) {
        items.push(parseInline(lines[i].trim().replace(/^[-*]\s+/, "")));
        i++;
      }
      blocks.push({ kind: "list", items });
      continue;
    }

    // Blank → skip
    if (!trim) {
      i++;
      continue;
    }

    // Paragraph: collect until next blank/heading/list/fence
    const buf: string[] = [trim];
    i++;
    while (i < lines.length) {
      const t = lines[i].trim();
      if (
        !t ||
        /^#{2,3}\s+/.test(t) ||
        /^[-*]\s+/.test(t) ||
        /^```/.test(t)
      ) {
        break;
      }
      buf.push(t);
      i++;
    }
    blocks.push({ kind: "paragraph", spans: parseInline(buf.join(" ")) });
  }

  return blocks;
}

/** Tokenize a line into Spans. */
export function parseInline(text: string): Span[] {
  if (!text) return [];
  const out: Span[] = [];
  let last = 0;
  for (const m of text.matchAll(TOKEN_RE)) {
    const idx = m.index ?? 0;
    if (idx > last) out.push({ kind: "text", text: text.slice(last, idx) });
    if (m[1]) {
      out.push({ kind: "bold", text: m[1].slice(2, -2) });
    } else if (m[2]) {
      out.push({ kind: "code", text: m[2].slice(1, -1) });
    } else if (m[3]) {
      out.push({ kind: "number", text: m[3] });
    }
    last = idx + m[0].length;
  }
  if (last < text.length) out.push({ kind: "text", text: text.slice(last) });
  return out;
}

function classifySentiment(tag: string): Sentiment {
  const t = tag.toLowerCase();
  if (/(bull|tăng|mua|overweight|buy|positive|risk-on)/.test(t)) return "bullish";
  if (/(bear|giảm|bán|underweight|sell|negative|risk-off)/.test(t)) return "bearish";
  if (/(mix|hỗn hợp)/.test(t)) return "mixed";
  return "neutral";
}
