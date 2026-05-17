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
      className="rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-gray-400"
    >
      {LABEL[state]}
    </button>
  );
}
