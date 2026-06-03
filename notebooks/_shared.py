"""Shared utilities for QuantArena defense notebooks.

Single import surface so each notebook starts the same way:

    from notebooks._shared import (
        RESULTS, FIGURES, AGENT_COLORS, ROLE_COLORS,
        load_metrics_table, load_curve, load_holdings, load_transcript,
        save_fig, setup_matplotlib,
    )
    setup_matplotlib()

Everything here is READ-ONLY against `results/`. Notebooks must not mutate
canonical artifacts (PKG-S snapshot is frozen).
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

# ─────────────────────────────────────────────────────────────────────────────
# Paths — anchor on the project root regardless of where the notebook lives
# ─────────────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESULTS = PROJECT_ROOT / "results"
FIGURES = PROJECT_ROOT / "report" / "figures"
DATA = PROJECT_ROOT / "data" / "processed"
TRANSCRIPTS = RESULTS / "multi_agent" / "transcripts"

# Make sure the figure dir exists — notebooks save into it.
FIGURES.mkdir(parents=True, exist_ok=True)

# ─────────────────────────────────────────────────────────────────────────────
# Palette — must match landing UI (lib/colors.ts) so slide + web stay consistent
# ─────────────────────────────────────────────────────────────────────────────

AGENT_COLORS: dict[str, str] = {
    # Baselines — neutral grays
    "buy_and_hold": "#9ca3af",
    "equal_weight": "#6b7280",
    "random": "#d1d5db",
    # RL — cool blues
    "ddpg": "#3b82f6",
    "ppo": "#0ea5e9",
    # LLM — warm hierarchy
    "zero_shot": "#f59e0b",
    "single_agentic": "#ef4444",
    "multi_agent": "#dc2626",  # headline agent
}

BASELINES = {"buy_and_hold", "equal_weight", "random"}
RL_AGENTS = {"ddpg", "ppo"}
LLM_AGENTS = {"zero_shot", "single_agentic", "multi_agent"}

# Per-role palette for multi_agent debate (RoleBadge in UI mirrors this).
ROLE_COLORS: dict[str, str] = {
    "technical_analyst": "#0ea5e9",
    "news_sentiment_analyst": "#06b6d4",
    "fundamental_analyst": "#14b8a6",
    "bullish_researcher": "#10b981",
    "bearish_researcher": "#ef4444",
    "trader": "#f59e0b",
    "risk_manager": "#ea580c",
    "portfolio_manager": "#7c3aed",
}

# ─────────────────────────────────────────────────────────────────────────────
# Loaders — single source of truth for every artifact
# ─────────────────────────────────────────────────────────────────────────────


def load_metrics_table() -> pd.DataFrame:
    """results/metrics_table.csv indexed by agent."""
    df = pd.read_csv(RESULTS / "metrics_table.csv")
    return df.set_index("agent")


def load_curve(agent: str) -> pd.DataFrame:
    """Per-agent portfolio_curve with parsed dates.

    Columns: date, agent_name, portfolio_value, cash, w_VCB, w_FPT, w_HPG,
    w_VIC, w_VNM.
    """
    df = pd.read_parquet(RESULTS / agent / "portfolio_curve.parquet")
    df["date"] = pd.to_datetime(df["date"])
    return df


def load_holdings(agent: str) -> pd.DataFrame:
    """Per-agent holdings (date + per-ticker share count)."""
    df = pd.read_parquet(RESULTS / agent / "holdings.parquet")
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
    return df


def load_metrics_json(agent: str) -> dict:
    """Per-agent metrics.json (financial + LLM extras)."""
    path = RESULTS / agent / "metrics.json"
    return json.loads(path.read_text())


def load_transcript(date: str) -> dict:
    """Multi-agent debate transcript for a given decision date (YYYY-MM-DD)."""
    return json.loads((TRANSCRIPTS / f"{date}.json").read_text())


def list_transcript_dates() -> list[str]:
    """Sorted list of decision dates that have cached transcripts."""
    return sorted(p.stem for p in TRANSCRIPTS.glob("*.json"))


# ─────────────────────────────────────────────────────────────────────────────
# Figure helpers
# ─────────────────────────────────────────────────────────────────────────────


def setup_matplotlib() -> None:
    """Defense-grade defaults: monospace tabular nums for axes, larger fonts,
    cyan-friendly grid, no top/right spines.

    Call once at the top of each notebook. Idempotent.
    """
    import logging

    # Silence matplotlib font manager warnings when fallback fonts are used
    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)

    plt.rcParams.update(
        {
            "figure.dpi": 100,
            "savefig.dpi": 150,
            "savefig.bbox": "tight",
            "font.family": ["DejaVu Sans", "Liberation Sans", "Ubuntu", "sans-serif"],
            "font.size": 11,
            "axes.titlesize": 13,
            "axes.titleweight": "600",
            "axes.labelsize": 11,
            "axes.grid": True,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "grid.alpha": 0.25,
            "grid.linestyle": "--",
            "legend.frameon": False,
            "xtick.labelsize": 10,
            "ytick.labelsize": 10,
        }
    )


def save_fig(name: str, fig: plt.Figure | None = None) -> Path:
    """Save a figure to ``report/figures/{name}.png`` at dpi=150.

    ``name`` should already include the notebook prefix, e.g. ``"03__cumret_bar"``.
    Returns the saved path so notebooks can show it inline.
    """
    if not name.endswith(".png"):
        name = name + ".png"
    out = FIGURES / name
    f = fig or plt.gcf()
    f.savefig(out, dpi=150, bbox_inches="tight")
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Sanity helpers — useful inside Defense Q&A cells
# ─────────────────────────────────────────────────────────────────────────────


def assert_frozen_snapshot() -> None:
    """Fail loud if a critical canonical artifact is missing — catches the case
    where someone accidentally reset the results dir before running notebooks."""
    must_exist = [
        RESULTS / "metrics_table.csv",
        RESULTS / "multi_agent" / "portfolio_curve.parquet",
        RESULTS / "ppo" / "portfolio_curve.parquet",
        RESULTS / "ddpg" / "portfolio_curve.parquet",
        TRANSCRIPTS,
    ]
    missing = [p for p in must_exist if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "Frozen snapshot incomplete — missing:\n  - "
            + "\n  - ".join(str(p) for p in missing)
        )
    n_transcripts = sum(1 for _ in TRANSCRIPTS.glob("*.json"))
    if n_transcripts < 50:
        raise AssertionError(
            f"Expected ≥50 cached transcripts (PKG-S full run); got {n_transcripts}."
        )
