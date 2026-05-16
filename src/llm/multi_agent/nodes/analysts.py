"""3 analyst nodes: technical, news+sentiment, fundamental.

Each:
- Pre-fetches per-ticker data via LookaheadSafeTools (D8: Python-side, not
  LLM tool_calls) — deterministic, bounded cost
- Makes ONE LLM call per analyst (5 tickers in one prompt, not 5 calls)
- Emits a single markdown blob (`<role>_brief`) — advisor feedback: per-ticker
  split is brittle, downstream prompts consume full context anyway
- Records one transcript entry; logs node_errors on exception

max_retries=2 in client.chat (override) — caps per-LLM-call wallclock at
1+2 ≈ 3s, fits 30s decision budget even with 10 sequential calls.
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.llm.multi_agent.state import MultiAgentState
from src.llm.multi_agent.transcript import now_iso

log = logging.getLogger(__name__)

_PROMPT_DIR = Path(__file__).resolve().parent.parent.parent / "prompts" / "multi_agent"
_MAX_RETRIES: int = 2  # advisor: bound per-call wallclock for 30s budget


def _load_prompt(name: str) -> str:
    p = _PROMPT_DIR / f"{name}.md"
    return p.read_text(encoding="utf-8")


# Lazy load on first use so missing-prompt errors fire late, not at module import
_PROMPTS: dict[str, str] = {}


def _prompt(role: str) -> str:
    if role not in _PROMPTS:
        _PROMPTS[role] = _load_prompt(role)
    return _PROMPTS[role]


def _format_indicators_block(tools, universe: list[str]) -> str:
    lines = []
    for t in universe:
        out = tools.get_indicators(t)
        as_of = out.get("as_of_date", "?")
        ind = out.get("indicators", {})
        kv = ", ".join(f"{k}={v:+.2f}" for k, v in ind.items())
        lines.append(f"- {t} (as_of={as_of}): {kv}")
    return "\n".join(lines)


def _format_price_history_block(tools, universe: list[str], days: int = 10) -> str:
    lines = []
    for t in universe:
        out = tools.get_price_history(t, days=days)
        rows = out.get("rows", [])
        if not rows:
            lines.append(f"- {t}: (no history)")
            continue
        first, last = rows[0], rows[-1]
        pct = (last["close"] / first["close"] - 1) * 100 if first["close"] else 0
        lines.append(
            f"- {t}: {first['date']}→{last['date']} "
            f"close {first['close']:.2f}→{last['close']:.2f} ({pct:+.2f}%) "
            f"over {len(rows)} bars"
        )
    return "\n".join(lines)


def _format_news_block(tools, universe: list[str]) -> str:
    items = tools.get_news()
    if not items:
        return "(no news visible)"
    # Filter to universe + cap 15
    filtered = [
        it for it in items
        if any(t in it.get("tickers", []) for t in universe)
    ][:15]
    if not filtered:
        return "(no news for universe)"
    lines = []
    for it in filtered:
        tickers_str = ",".join(t for t in it["tickers"] if t in universe)
        lines.append(
            f"- [{it['published_at'][:16]}] [{tickers_str}] {it['title']}"
        )
    return "\n".join(lines)


def _format_fundamentals_block(tools, universe: list[str]) -> str:
    lines = []
    for t in universe:
        try:
            out = tools.get_fundamentals(t)
            quarters = out.get("quarters_available", [])
            items_n = len(out.get("items", []))
            lines.append(
                f"- {t}: {len(quarters)} quarters visible "
                f"({', '.join(quarters[-4:])}), {items_n} line items"
            )
        except Exception as e:
            lines.append(f"- {t}: fundamentals fetch failed ({type(e).__name__})")
    return "\n".join(lines)


def _format_holdings_block(info: dict, universe: list[str]) -> str:
    pv = float(info.get("portfolio_value", 0))
    cash = float(info.get("cash", 0))
    holdings = info.get("holdings", [0] * len(universe))
    close_t = info.get("close_t", [1.0] * len(universe))
    lines = [f"- Total PV: {pv:,.0f} VND, cash {cash:,.0f} ({cash/max(pv,1)*100:.1f}%)"]
    for i, t in enumerate(universe):
        sh = int(holdings[i])
        pc = float(close_t[i])
        val = sh * pc
        lines.append(f"- {t}: {sh:,} shares × {pc:,.2f} = {val:,.0f} ({val/max(pv,1)*100:.1f}%)")
    return "\n".join(lines)


def _run_analyst(
    state: MultiAgentState,
    role: str,
    brief_key: str,
    user_message: str,
) -> dict:
    """Shared analyst plumbing: LLM call → brief + transcript + error handling."""
    try:
        result = state["client"].chat(
            model=state["models"][role],
            messages=[
                {"role": "system", "content": _prompt(role)},
                {"role": "user", "content": user_message},
            ],
            temperature=0.0,
            max_retries=_MAX_RETRIES,
        )
        brief = result.text or ""
        return {
            brief_key: brief,
            "transcript": [
                {
                    "role": role,
                    "ts": now_iso(),
                    "model": result.model,
                    "output": brief,
                    "usage": result.usage,
                }
            ],
        }
    except Exception as e:
        log.warning("%s failed: %s", role, e)
        return {
            brief_key: f"FAILURE: {role} ({type(e).__name__})",
            "node_errors": [
                {"role": role, "error": str(e), "ts": now_iso()}
            ],
            "transcript": [
                {"role": role, "ts": now_iso(), "error": str(e)}
            ],
        }


def technical_analyst(state: MultiAgentState) -> dict:
    """Read indicators + recent OHLC for all 5 tickers; write markdown brief."""
    tools = state["tools"]
    universe = state["universe"]
    user_msg = (
        "## Holdings hiện tại\n"
        + _format_holdings_block(state["info"], universe)
        + "\n\n## Chỉ báo kỹ thuật (z-score, pre-decision session)\n"
        + _format_indicators_block(tools, universe)
        + "\n\n## Giá 10 phiên gần nhất\n"
        + _format_price_history_block(tools, universe, days=10)
        + "\n\nViết phân tích kỹ thuật ngắn gọn cho 5 mã."
    )
    return _run_analyst(state, "technical_analyst", "technical_brief", user_msg)


def news_sentiment_analyst(state: MultiAgentState) -> dict:
    """Read recent visible news; summarize sentiment per ticker."""
    tools = state["tools"]
    universe = state["universe"]
    user_msg = (
        "## Tin tức gần đây (đã lọc visible D+2, tối đa 15)\n"
        + _format_news_block(tools, universe)
        + "\n\n## Danh mục hiện tại\n"
        + _format_holdings_block(state["info"], universe)
        + "\n\nĐánh giá sentiment cho 5 mã (positive/neutral/negative + 1 dòng lý do)."
    )
    return _run_analyst(
        state, "news_sentiment_analyst", "news_sentiment_brief", user_msg
    )


def fundamental_analyst(state: MultiAgentState) -> dict:
    """Read 4-quarter fundamentals; flag improving/stable/declining."""
    tools = state["tools"]
    universe = state["universe"]
    user_msg = (
        "## Báo cáo tài chính 4 quý gần nhất (đã lọc lag ~30 ngày)\n"
        + _format_fundamentals_block(tools, universe)
        + "\n\n## Danh mục hiện tại\n"
        + _format_holdings_block(state["info"], universe)
        + "\n\nĐánh giá fundamentals cho 5 mã (improving/stable/declining)."
    )
    return _run_analyst(
        state, "fundamental_analyst", "fundamental_brief", user_msg
    )
