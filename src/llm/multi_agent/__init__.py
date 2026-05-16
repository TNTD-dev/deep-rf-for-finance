"""Multi-agent LangGraph trader (PKG-8).

Six LLM roles in a state machine: 3 Analysts → Bull/Bear debate (≤2 rounds)
→ Trader → Risk Manager → Portfolio Manager. Per-portfolio weekly decision.
See .agent/plans/pkg-8-multi-agent-langgraph.md.
"""

from src.llm.multi_agent.agent import MultiAgentTrader
from src.llm.multi_agent.graph import build_app, build_graph
from src.llm.multi_agent.state import MultiAgentState, make_initial_state

__all__ = [
    "MultiAgentTrader",
    "MultiAgentState",
    "build_app",
    "build_graph",
    "make_initial_state",
]
