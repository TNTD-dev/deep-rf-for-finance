"""GET /healthz — liveness + diagnostics (PKG-11).

Returns enough to confirm the backend can see the PKG-10 results dir
before opening the dashboard. ``curl /healthz`` is the demo-day smoke.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Request

from backend.models import HealthzResponse

router = APIRouter()


@router.get("/healthz", response_model=HealthzResponse)
def healthz(request: Request) -> dict:
    rd = request.app.state.results_dir
    n_files = len(list(rd.glob("*/metrics.json"))) if rd.exists() else 0
    return {
        "status": "ok",
        "results_dir": str(rd),
        "results_dir_exists": rd.exists(),
        "n_metrics_files": n_files,
        "n_cached": request.app.state.cache.size(),
        "uptime_s": time.monotonic() - request.app.state.started_at,
    }
