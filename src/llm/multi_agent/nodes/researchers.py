"""Bullish vs Bearish researcher debate (cap = state['debate_rounds_max']).

Each round = 1 bullish turn + 1 bearish turn (2 LLM calls). Bearish
increments ``debate_round`` (D4). Conditional router ``should_continue_debate``
is READ-ONLY (advisor): it just reads ``debate_round`` and routes — no
state mutation.

Each researcher reads all 3 analyst briefs + the full debate history so
arguments build on prior turns.
"""

from __future__ import annotations

import logging

from src.llm.multi_agent.nodes.analysts import _MAX_RETRIES, _prompt
from src.llm.multi_agent.state import MultiAgentState
from src.llm.multi_agent.transcript import now_iso

log = logging.getLogger(__name__)


def _format_debate_history(exchanges: list[dict]) -> str:
    if not exchanges:
        return "(chưa có lượt nào — bạn nói đầu tiên)"
    lines = []
    for ex in exchanges:
        lines.append(
            f"### {ex['role'].upper()} (round {ex.get('round', '?')})\n"
            f"{ex.get('text', '')}"
        )
    return "\n\n".join(lines)


def _format_analyst_briefs(state: MultiAgentState) -> str:
    return (
        "## Technical analyst\n"
        + state.get("technical_brief", "(empty)")
        + "\n\n## News/Sentiment analyst\n"
        + state.get("news_sentiment_brief", "(empty)")
        + "\n\n## Fundamental analyst\n"
        + state.get("fundamental_brief", "(empty)")
    )


def _run_researcher(state: MultiAgentState, role: str) -> tuple[str, dict | None]:
    """Returns (text, error_record_or_None)."""
    user_msg = (
        "## Báo cáo các analyst\n"
        + _format_analyst_briefs(state)
        + "\n\n## Lịch sử tranh luận\n"
        + _format_debate_history(state.get("debate_exchanges", []))
        + f"\n\n## Round hiện tại: {state['debate_round']}\n"
        + ("Hãy lập luận của bạn (bull/bear theo vai trò)." )
    )
    try:
        result = state["client"].chat(
            model=state["models"][role],
            messages=[
                {"role": "system", "content": _prompt(role)},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.0,
            max_retries=_MAX_RETRIES,
        )
        return (result.text or "", None)
    except Exception as e:
        log.warning("%s failed at round %d: %s", role, state["debate_round"], e)
        return (
            f"FAILURE: {role} ({type(e).__name__})",
            {"role": role, "error": str(e), "ts": now_iso(),
             "round": state["debate_round"]},
        )


def bullish_researcher(state: MultiAgentState) -> dict:
    """Argue for increasing exposure to strongest signals."""
    text, err = _run_researcher(state, "bullish_researcher")
    rd = state["debate_round"]
    patch: dict = {
        "debate_exchanges": [
            {"role": "bullish_researcher", "round": rd, "text": text,
             "ts": now_iso()}
        ],
        "transcript": [
            {"role": "bullish_researcher", "ts": now_iso(),
             "round": rd, "output": text}
        ],
    }
    if err:
        patch["node_errors"] = [err]
    return patch


def bearish_researcher(state: MultiAgentState) -> dict:
    """Argue for caution; INCREMENTS debate_round after speaking (D4)."""
    text, err = _run_researcher(state, "bearish_researcher")
    rd = state["debate_round"]
    patch: dict = {
        "debate_exchanges": [
            {"role": "bearish_researcher", "round": rd, "text": text,
             "ts": now_iso()}
        ],
        "transcript": [
            {"role": "bearish_researcher", "ts": now_iso(),
             "round": rd, "output": text}
        ],
        "debate_round": rd + 1,  # advance counter
    }
    if err:
        patch["node_errors"] = [err]
    return patch


def should_continue_debate(state: MultiAgentState) -> str:
    """Conditional router — READ-ONLY of state (no mutation).

    Returns "loop" to re-enter bullish_researcher, "exit" to proceed to trader.
    """
    cap = state.get("debate_rounds_max", 2)
    return "loop" if state["debate_round"] < cap else "exit"
