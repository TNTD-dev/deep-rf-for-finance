"""GET /backtest/{agent} — pure read of PKG-10 metrics.json (PKG-11)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from backend.models import BacktestPayload

router = APIRouter()


@router.get("/backtest/{agent}", response_model=BacktestPayload)
def get_backtest(agent: str, request: Request) -> dict:
    path = request.app.state.results_dir / agent / "metrics.json"
    data = request.app.state.cache.get(path)
    if data is None:
        raise HTTPException(404, f"no metrics for agent {agent!r}")
    return data
