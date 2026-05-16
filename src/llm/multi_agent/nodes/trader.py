"""Trader node — synthesizes analyst briefs + debate into a concrete proposal."""

from __future__ import annotations

import logging

from src.llm.multi_agent.nodes.analysts import _MAX_RETRIES, _prompt
from src.llm.multi_agent.nodes.researchers import (
    _format_analyst_briefs,
    _format_debate_history,
)
from src.llm.multi_agent.state import MultiAgentState
from src.llm.multi_agent.transcript import now_iso

log = logging.getLogger(__name__)


def trader(state: MultiAgentState) -> dict:
    user_msg = (
        "## Báo cáo analyst\n"
        + _format_analyst_briefs(state)
        + "\n\n## Tranh luận bull/bear\n"
        + _format_debate_history(state.get("debate_exchanges", []))
        + "\n\n## Yêu cầu\n"
        "Tổng hợp thành một đề xuất CỤ THỂ cho danh mục (overweight / "
        "equal-weight / underweight mỗi mã + lý do ngắn). KHÔNG cần output "
        "JSON — chỉ markdown prose."
    )
    try:
        result = state["client"].chat(
            model=state["models"]["trader"],
            messages=[
                {"role": "system", "content": _prompt("trader")},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.0,
            max_retries=_MAX_RETRIES,
        )
        text = result.text or ""
        return {
            "trader_proposal": text,
            "transcript": [
                {"role": "trader", "ts": now_iso(),
                 "model": result.model, "output": text,
                 "usage": result.usage}
            ],
        }
    except Exception as e:
        log.warning("trader failed: %s", e)
        return {
            "trader_proposal": f"FAILURE: trader ({type(e).__name__})",
            "node_errors": [
                {"role": "trader", "error": str(e), "ts": now_iso()}
            ],
            "transcript": [
                {"role": "trader", "ts": now_iso(), "error": str(e)}
            ],
        }
