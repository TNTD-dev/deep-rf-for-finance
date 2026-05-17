"""FastAPI app entry (PKG-11).

Run dev:   uvicorn backend.main:app --reload --port 8000
Run demo:  uvicorn backend.main:app --port 8000

Test fixture pattern — override the production results dir:

    from backend.main import create_app
    app = create_app()
    app.state.results_dir = tmp_path
    app.state.cache.clear()
    client = TestClient(app)
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.cache import JSONFileCache
from backend.routes import agents, backtest, debate, healthz
from src import config

RESULTS_DIR = config.PROJECT_ROOT / "results"


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.results_dir = RESULTS_DIR
    app.state.cache = JSONFileCache()
    app.state.started_at = time.monotonic()
    yield
    app.state.cache.clear()


def create_app() -> FastAPI:
    app = FastAPI(
        title="deep-rf-finance API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://localhost:8000"],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    # State for code paths that run BEFORE lifespan fires (TestClient
    # accesses app.state on first request — without these defaults, the
    # first read would AttributeError before the lifespan async context
    # opens).
    app.state.results_dir = RESULTS_DIR
    app.state.cache = JSONFileCache()
    app.state.started_at = time.monotonic()
    app.include_router(healthz.router)
    app.include_router(agents.router)
    app.include_router(backtest.router)
    app.include_router(debate.router)
    return app


app = create_app()
