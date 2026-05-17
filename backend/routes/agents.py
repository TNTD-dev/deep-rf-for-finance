"""GET /agents — registry-derived list, partitioned baseline vs agent (PKG-11)."""

from __future__ import annotations

from fastapi import APIRouter

from backend.models import AgentList

# Lazy import of AGENT_REGISTRY at request time — importing src.agents at
# module load pulls langgraph + torch (~1.5s) and pushes the cold-start
# budget over 2s. The first /agents request pays that cost; subsequent
# requests see Python's import cache (~0ms).
BASELINE_AGENTS = frozenset({"buy_and_hold", "equal_weight", "random"})

router = APIRouter()


@router.get("/agents", response_model=AgentList)
def get_agents() -> dict:
    from src.agents import AGENT_REGISTRY

    all_names = set(AGENT_REGISTRY.keys())
    return {
        "agents": sorted(all_names - BASELINE_AGENTS),
        "baselines": sorted(all_names & BASELINE_AGENTS),
    }
