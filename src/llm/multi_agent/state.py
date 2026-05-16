"""MultiAgentState — TypedDict flowing through the LangGraph state machine.

All 6 roles read + write this single state object. Reducer-tagged fields
(``Annotated[list, add]``) auto-concatenate when multiple nodes append.
Non-reducer fields are last-write-wins.

Per advisor feedback: analysts emit a SINGLE markdown blob (``*_brief``)
per role, NOT a per-ticker list. Reduces parser fragility (LLM may use
``### VCB`` vs ``## VCB`` vs ``**VCB:**``) and downstream nodes consume
the brief whole anyway.
"""

from __future__ import annotations

from operator import add
from typing import Annotated, TypedDict

from src.env_data_loader import MarketData
from src.llm.client import OpenAIClient
from src.llm.tools import LookaheadSafeTools

# Canonical role list — single source of truth for prompts, models, tests.
ROLE_NAMES: tuple[str, ...] = (
    "technical_analyst",
    "news_sentiment_analyst",
    "fundamental_analyst",
    "bullish_researcher",
    "bearish_researcher",
    "trader",
    "risk_manager",
    "portfolio_manager",
)


class MultiAgentState(TypedDict, total=False):
    """State carried through the LangGraph state machine.

    ``total=False`` lets node fns return partial-update dicts without
    needing NotRequired markers on every field.
    """

    # --- Inputs (set in make_initial_state; never mutated mid-graph) ---
    market_data: MarketData
    news_data: object  # pd.DataFrame; object to avoid pandas import in TypedDict
    tools: LookaheadSafeTools
    client: OpenAIClient
    models: dict[str, str]              # role → model id
    info: dict                          # env info: date, holdings, pv, ...
    universe: list[str]                 # config.TICKERS

    # --- Analyst outputs (single markdown blob per analyst) ---
    technical_brief: str
    news_sentiment_brief: str
    fundamental_brief: str

    # --- Debate loop ---
    debate_round: int                   # incremented by bearish_researcher after each pair
    debate_rounds_max: int              # cap from constructor
    debate_exchanges: Annotated[list[dict], add]  # ordered: bull r0, bear r0, bull r1, ...

    # --- Synthesis chain ---
    trader_proposal: str
    risk_review: str
    portfolio_manager_output: str       # raw text; parsed by MultiAgentTrader

    # --- Observability ---
    transcript: Annotated[list[dict], add]
    node_errors: Annotated[list[dict], add]


def make_initial_state(
    *,
    market_data: MarketData,
    news_data,
    info: dict,
    client: OpenAIClient,
    models: dict[str, str],
    tools: LookaheadSafeTools,
    debate_rounds_max: int = 2,
) -> MultiAgentState:
    """Build the initial state for one graph invocation.

    All input-side keys populated; output-side keys initialized to empty
    sentinels so node fns can use ``state.get(...)`` safely.
    """
    return MultiAgentState(
        market_data=market_data,
        news_data=news_data,
        tools=tools,
        client=client,
        models=dict(models),
        info=dict(info),
        universe=list(market_data.tickers),
        technical_brief="",
        news_sentiment_brief="",
        fundamental_brief="",
        debate_round=0,
        debate_rounds_max=int(debate_rounds_max),
        debate_exchanges=[],
        trader_proposal="",
        risk_review="",
        portfolio_manager_output="",
        transcript=[],
        node_errors=[],
    )


def strip_non_serializable(state: MultiAgentState) -> dict:
    """Return a dict copy with non-JSON-serializable input keys removed.

    Used by the transcript writer + tests. Keeps the live state intact
    so downstream code unaffected.
    """
    drop_keys = {"market_data", "news_data", "tools", "client"}
    return {k: v for k, v in state.items() if k not in drop_keys}
