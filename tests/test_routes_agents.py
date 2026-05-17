"""Tests for backend/routes/agents.py."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.routes.agents import BASELINE_AGENTS
from src.agents import AGENT_REGISTRY


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_agents_returns_registry_partition(client: TestClient) -> None:
    r = client.get("/agents")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"agents", "baselines"}

    # Partition must cover the full registry.
    all_returned = set(body["agents"]) | set(body["baselines"])
    assert all_returned == set(AGENT_REGISTRY)
    # No overlap.
    assert not (set(body["agents"]) & set(body["baselines"]))
    # Baselines slice matches the hardcoded set (those that exist in registry).
    assert set(body["baselines"]) == BASELINE_AGENTS & set(AGENT_REGISTRY)


def test_agents_alphabetical(client: TestClient) -> None:
    body = client.get("/agents").json()
    assert body["agents"] == sorted(body["agents"])
    assert body["baselines"] == sorted(body["baselines"])
