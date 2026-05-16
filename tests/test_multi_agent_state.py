"""MultiAgentState invariants — TypedDict shape, reducers, serializability."""

from __future__ import annotations

import json
from operator import add
from typing import get_args, get_origin, get_type_hints

import pandas as pd
import pytest

from src.llm.multi_agent.state import (
    ROLE_NAMES,
    MultiAgentState,
    make_initial_state,
    strip_non_serializable,
)
from src.llm.tools import LookaheadSafeTools


@pytest.fixture
def _initial(synthetic_market_data):
    md = synthetic_market_data
    tools = LookaheadSafeTools(md, pd.DataFrame(), md.dates[5])
    # OpenAIClient unused in these tests; passing a stub object is fine
    client = object()
    models = {role: "gpt-4o-mini" for role in ROLE_NAMES}
    return make_initial_state(
        market_data=md,
        news_data=pd.DataFrame(),
        info={"date": str(md.dates[5]), "holdings": [0] * 5,
              "portfolio_value": 1e9, "cash": 1e9,
              "close_t": [50.0] * 5, "t": 5},
        client=client,
        models=models,
        tools=tools,
        debate_rounds_max=2,
    )


def test_initial_state_has_required_inputs(_initial):
    """All input-side keys present + initialized; output-side keys default empty."""
    for k in ["market_data", "news_data", "tools", "client", "models",
              "info", "universe", "debate_round", "debate_rounds_max"]:
        assert k in _initial, f"missing required key {k!r}"
    assert _initial["debate_round"] == 0
    assert _initial["debate_rounds_max"] == 2
    assert _initial["universe"] == list(_initial["market_data"].tickers)
    assert _initial["technical_brief"] == ""
    assert _initial["transcript"] == []
    assert _initial["node_errors"] == []


def test_role_names_match_models_keys(_initial):
    """ROLE_NAMES is the single source of truth — make_initial_state populates
    models keyed by exactly these 8 names."""
    assert set(_initial["models"].keys()) == set(ROLE_NAMES)
    assert len(ROLE_NAMES) == 8


def test_transcript_reducer_is_list_add():
    """Annotated[list, add] = LangGraph appends successive node patches.

    Without this, the second node would overwrite the first's transcript
    entries and we'd lose history. Verifies via type introspection that
    transcript + debate_exchanges + node_errors all use the add reducer.
    """
    hints = get_type_hints(MultiAgentState, include_extras=True)
    for field in ["transcript", "debate_exchanges", "node_errors"]:
        ann = hints[field]
        assert get_origin(ann) is not None, f"{field}: not Annotated"
        args = get_args(ann)
        assert add in args, f"{field}: reducer must be `add`, got {args}"


def test_strip_non_serializable_makes_state_json_safe(_initial):
    """After dropping market_data/news_data/tools/client, the state must be
    JSON-serializable so the transcript writer can dump it."""
    stripped = strip_non_serializable(_initial)
    assert "market_data" not in stripped
    assert "tools" not in stripped
    assert "client" not in stripped
    # Should round-trip through JSON
    s = json.dumps(stripped, default=str)
    back = json.loads(s)
    assert back["debate_round"] == 0
    assert back["debate_rounds_max"] == 2
