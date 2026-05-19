"use client";

interface Props {
  state: "idle" | "streaming" | "done" | "error";
  onClick: () => void;
}

const LABEL: Record<Props["state"], string> = {
  idle: "Run for today",
  streaming: "Running…",
  done: "Run again",
  error: "Retry",
};

export function RunButton({ state, onClick }: Props) {
  const isStreaming = state === "streaming";
  return (
    <button
      type="button"
      disabled={isStreaming}
      onClick={onClick}
      className={`inline-flex items-center gap-2 rounded-md px-5 py-2.5 font-mono text-xs font-semibold uppercase tracking-[0.14em] transition-all ${
        isStreaming
          ? "cursor-not-allowed bg-zinc-700 text-zinc-400"
          : "bg-cyan-400 text-black hover:bg-cyan-300 glow-cyan"
      }`}
    >
      {isStreaming && (
        <span className="h-2 w-2 animate-pulse rounded-full bg-cyan-200" />
      )}
      {LABEL[state]}
    </button>
  );
}
