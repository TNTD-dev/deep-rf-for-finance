"""Pydantic v2 response schemas (PKG-11).

Mirror PRD §10 verbatim. PKG-10 ``src.eval.backtest.build_payload`` is the
producer; these models are the consumer contract. Validation fires on
response (FastAPI ``response_model=``) so PKG-10 schema drift surfaces as
a 500, not a silent regression.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Provenance(BaseModel):
    ts: str
    seed: int
    test_window: list[str] | None = None
    n_steps: int


class PortfolioPoint(BaseModel):
    date: str
    value: int


class Metrics(BaseModel):
    """Financial + LLM-specific. ``extra='allow'`` surfaces per-agent extras
    (llm_cost_usd, n_decisions, avg_latency_s, hallucination_rate, ...)
    without subclassing per agent type."""

    model_config = ConfigDict(extra="allow")

    cumulative_return: float
    sharpe: float
    sortino: float
    max_drawdown: float
    turnover: float
    total_cost: float
    n_steps: int


class BacktestPayload(BaseModel):
    agent: str
    portfolio_curve: list[PortfolioPoint]
    # date is str, per-ticker counts are int — keep loose so VN30 expansion
    # doesn't require a model rev.
    holdings: list[dict[str, int | str]]
    metrics: Metrics
    provenance: Provenance


class AgentList(BaseModel):
    agents: list[str]
    baselines: list[str]


class DebateEntry(BaseModel):
    """Single transcript entry. ``decision`` (optional) only attaches to the
    final portfolio_manager entry; ``model`` + ``ts`` are bonus extras that
    PRD §10 doesn't forbid."""

    model_config = ConfigDict(extra="allow")

    role: str
    content: str


class DebateTranscript(BaseModel):
    date: str
    transcript: list[DebateEntry]


class DebateDatesResponse(BaseModel):
    """List of available transcript dates for a given agent (PKG-S S5b)."""

    agent: str
    dates: list[str]


class HealthzResponse(BaseModel):
    status: str
    results_dir: str
    results_dir_exists: bool
    n_metrics_files: int
    n_cached: int
    uptime_s: float
