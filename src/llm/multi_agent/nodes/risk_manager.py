"""Risk Manager node — critiques trader proposal from 3 angles."""

from __future__ import annotations

import logging

from src.llm.multi_agent.nodes.analysts import _MAX_RETRIES, _prompt
from src.llm.multi_agent.nodes.researchers import _format_analyst_briefs
from src.llm.multi_agent.state import MultiAgentState
from src.llm.multi_agent.transcript import now_iso

log = logging.getLogger(__name__)


def risk_manager(state: MultiAgentState) -> dict:
    user_msg = (
        "## Báo cáo analyst\n"
        + _format_analyst_briefs(state)
        + "\n\n## Đề xuất từ Trader\n"
        + state.get("trader_proposal", "(empty)")
        + "\n\n## Yêu cầu\n"
        "Phân tích rủi ro từ 3 góc: (1) concentration, (2) drawdown, "
        "(3) regime. Đề xuất điều chỉnh nếu cần. KHÔNG output JSON."
    )
    try:
        result = state["client"].chat(
            model=state["models"]["risk_manager"],
            messages=[
                {"role": "system", "content": _prompt("risk_manager")},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.0,
            max_retries=_MAX_RETRIES,
        )
        text = result.text or ""
        return {
            "risk_review": text,
            "transcript": [
                {"role": "risk_manager", "ts": now_iso(),
                 "model": result.model, "output": text,
                 "usage": result.usage}
            ],
        }
    except Exception as e:
        log.warning("risk_manager failed: %s", e)
        return {
            "risk_review": f"FAILURE: risk_manager ({type(e).__name__})",
            "node_errors": [
                {"role": "risk_manager", "error": str(e), "ts": now_iso()}
            ],
            "transcript": [
                {"role": "risk_manager", "ts": now_iso(), "error": str(e)}
            ],
        }
