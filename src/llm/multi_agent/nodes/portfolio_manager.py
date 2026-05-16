"""Portfolio Manager node — sole producer of JSON weights (D9).

Outputs raw text; MultiAgentTrader.decide() parses it via parse_weights_json.
Keeps graph state JSON-serializable (np.ndarray would break transcript dumps).
"""

from __future__ import annotations

import logging

from src.llm.multi_agent.nodes.analysts import _MAX_RETRIES, _prompt
from src.llm.multi_agent.state import MultiAgentState
from src.llm.multi_agent.transcript import now_iso

log = logging.getLogger(__name__)


def portfolio_manager(state: MultiAgentState) -> dict:
    user_msg = (
        "## Đề xuất từ Trader\n"
        + state.get("trader_proposal", "(empty)")
        + "\n\n## Review từ Risk Manager\n"
        + state.get("risk_review", "(empty)")
        + "\n\n## Yêu cầu\n"
        "Quyết định cuối cùng: trả về DUY NHẤT một khối JSON với weights "
        "cho 5 mã (VCB, FPT, HPG, VIC, VNM). Tuân thủ schema trong "
        "system prompt."
    )
    try:
        result = state["client"].chat(
            model=state["models"]["portfolio_manager"],
            messages=[
                {"role": "system", "content": _prompt("portfolio_manager")},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.0,
            max_retries=_MAX_RETRIES,
        )
        text = result.text or ""
        return {
            "portfolio_manager_output": text,
            "transcript": [
                {"role": "portfolio_manager", "ts": now_iso(),
                 "model": result.model, "raw_text": text,
                 "usage": result.usage}
            ],
        }
    except Exception as e:
        log.warning("portfolio_manager failed: %s", e)
        return {
            "portfolio_manager_output": "",  # parser → hold-shares
            "node_errors": [
                {"role": "portfolio_manager", "error": str(e),
                 "ts": now_iso()}
            ],
            "transcript": [
                {"role": "portfolio_manager", "ts": now_iso(),
                 "error": str(e)}
            ],
        }
