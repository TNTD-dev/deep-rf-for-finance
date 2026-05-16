"""LangGraph wiring: build_graph() and build_app().

Separation: build_graph returns the uncompiled ``StateGraph`` so tests can
inspect edges; build_app compiles and returns the invocable app.

Topology:
    START
      → technical_analyst → news_sentiment_analyst → fundamental_analyst
      → bullish_researcher ⇄ bearish_researcher  (cap = state["debate_rounds_max"])
      → trader → risk_manager → portfolio_manager
      → END

Debate loop (D4): ``bearish_researcher`` increments ``debate_round`` after
each pair; ``_should_continue_debate`` is the conditional router (READ-ONLY
of state per advisor feedback). Analyst phase sequential, not parallel —
deterministic transcript ordering, same total cost.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from src.llm.multi_agent.nodes.analysts import (
    fundamental_analyst,
    news_sentiment_analyst,
    technical_analyst,
)
from src.llm.multi_agent.nodes.portfolio_manager import portfolio_manager
from src.llm.multi_agent.nodes.researchers import (
    bearish_researcher,
    bullish_researcher,
    should_continue_debate,
)
from src.llm.multi_agent.nodes.risk_manager import risk_manager
from src.llm.multi_agent.nodes.trader import trader
from src.llm.multi_agent.state import MultiAgentState


def build_graph() -> StateGraph:
    """Build the uncompiled StateGraph. Inputs flow through state, not closure."""
    g = StateGraph(MultiAgentState)
    g.add_node("technical_analyst", technical_analyst)
    g.add_node("news_sentiment_analyst", news_sentiment_analyst)
    g.add_node("fundamental_analyst", fundamental_analyst)
    g.add_node("bullish_researcher", bullish_researcher)
    g.add_node("bearish_researcher", bearish_researcher)
    g.add_node("trader", trader)
    g.add_node("risk_manager", risk_manager)
    g.add_node("portfolio_manager", portfolio_manager)

    g.add_edge(START, "technical_analyst")
    g.add_edge("technical_analyst", "news_sentiment_analyst")
    g.add_edge("news_sentiment_analyst", "fundamental_analyst")
    g.add_edge("fundamental_analyst", "bullish_researcher")

    g.add_edge("bullish_researcher", "bearish_researcher")
    g.add_conditional_edges(
        "bearish_researcher",
        should_continue_debate,
        {"loop": "bullish_researcher", "exit": "trader"},
    )

    g.add_edge("trader", "risk_manager")
    g.add_edge("risk_manager", "portfolio_manager")
    g.add_edge("portfolio_manager", END)
    return g


def build_app():
    """Compile and return the invocable graph app."""
    return build_graph().compile()
