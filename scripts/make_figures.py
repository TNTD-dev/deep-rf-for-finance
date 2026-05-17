"""Generate the 4 chart PNGs Người 1 needs for the slide deck (PKG-S S5b).

Reads `results/<agent>/portfolio_curve.parquet` + `results/metrics_table.csv`
and writes:

  report/figures/01_portfolio_curves.png    # value vs date, all agents
  report/figures/02_cum_return_bar.png      # cumulative return horizontal bar
  report/figures/03_sharpe_bar.png          # Sharpe horizontal bar
  report/figures/04_decision_frequency.png  # n_steps per agent (daily vs weekly)

Run after `python -m src.eval.run_all` so metrics_table.csv reflects the
latest backtests. Matplotlib only — no seaborn/plotly to keep deps light.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from src import config

RESULTS = config.PROJECT_ROOT / "results"
FIGURES = config.PROJECT_ROOT / "report" / "figures"

# Display order: baselines, RL, LLM. Last entry first when sorted by metric.
AGENTS = [
    "buy_and_hold",
    "equal_weight",
    "random",
    "ddpg",
    "ppo",
    "zero_shot",
    "single_agentic",
    "multi_agent",
]

# Stable per-agent palette — mirrors frontend/lib/colors.ts intent so slide
# colors don't shuffle between runs. Hex values are fine for matplotlib.
COLORS: dict[str, str] = {
    "buy_and_hold": "#6b7280",  # gray
    "equal_weight": "#94a3b8",  # slate
    "random": "#d1d5db",  # light gray
    "ddpg": "#2563eb",  # blue
    "ppo": "#7c3aed",  # violet
    "zero_shot": "#16a34a",  # green
    "single_agentic": "#ea580c",  # orange
    "multi_agent": "#dc2626",  # red — the headline agent
}


def _load_curve(agent: str) -> pd.DataFrame | None:
    path = RESULTS / agent / "portfolio_curve.parquet"
    if not path.exists():
        return None
    return pd.read_parquet(path)


def _load_metrics() -> pd.DataFrame:
    return pd.read_csv(RESULTS / "metrics_table.csv")


def fig_portfolio_curves(out: Path) -> None:
    fig, ax = plt.subplots(figsize=(11, 5.5))
    for agent in AGENTS:
        df = _load_curve(agent)
        if df is None or df.empty:
            continue
        ax.plot(
            df["date"],
            df["portfolio_value"] / 1e9,  # billions VND
            label=agent,
            color=COLORS.get(agent),
            linewidth=1.4,
        )
    ax.axhline(1.0, color="black", linestyle=":", linewidth=0.7, alpha=0.4)
    ax.set_title("Portfolio value — test 2025-05 → 2026-04 (VN30, initial 1B VND)")
    ax.set_xlabel("Date")
    ax.set_ylabel("Portfolio value (billion VND)")
    ax.legend(loc="upper left", fontsize=8, ncol=2)
    ax.grid(True, alpha=0.25)
    fig.autofmt_xdate()
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _horizontal_bar(metrics: pd.DataFrame, column: str, title: str, xlabel: str, out: Path) -> None:
    """Reusable: sort by `column`, draw colored bars, annotate values."""
    df = metrics.sort_values(column, ascending=True).reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    colors = [COLORS.get(a, "#666") for a in df["agent"]]
    bars = ax.barh(df["agent"], df[column], color=colors)
    for bar, val in zip(bars, df[column], strict=True):
        x = bar.get_width()
        align = "left" if x >= 0 else "right"
        offset = max(abs(df[column].max()), 0.01) * 0.01
        ax.text(
            x + (offset if x >= 0 else -offset),
            bar.get_y() + bar.get_height() / 2,
            f"{val:+.2%}" if "return" in column else f"{val:.2f}",
            va="center",
            ha=align,
            fontsize=9,
        )
    ax.axvline(0, color="black", linewidth=0.6)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.grid(True, alpha=0.25, axis="x")
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)


def fig_cum_return_bar(metrics: pd.DataFrame, out: Path) -> None:
    _horizontal_bar(
        metrics,
        "cumulative_return",
        "Cumulative return — test period",
        "Cumulative return",
        out,
    )


def fig_sharpe_bar(metrics: pd.DataFrame, out: Path) -> None:
    _horizontal_bar(
        metrics,
        "sharpe",
        "Sharpe ratio — test period",
        "Sharpe (annualized)",
        out,
    )


def fig_decision_frequency(metrics: pd.DataFrame, out: Path) -> None:
    """Bar of n_steps per agent — visualizes daily (RL/baselines ~248) vs
    weekly (LLM ~50) decision cadence. Bằng chứng cho PRD §15."""
    df = metrics.sort_values("n_steps", ascending=True).reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    colors = [COLORS.get(a, "#666") for a in df["agent"]]
    bars = ax.barh(df["agent"], df["n_steps"], color=colors)
    for bar, val in zip(bars, df["n_steps"], strict=True):
        ax.text(
            bar.get_width() + 2,
            bar.get_y() + bar.get_height() / 2,
            f"{int(val)}",
            va="center",
            fontsize=9,
        )
    ax.set_title("Backtest steps per agent (daily vs weekly cadence)")
    ax.set_xlabel("Number of decision steps")
    ax.grid(True, alpha=0.25, axis="x")
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    FIGURES.mkdir(parents=True, exist_ok=True)
    metrics_path = RESULTS / "metrics_table.csv"
    if not metrics_path.exists():
        print(f"missing {metrics_path}; run `python -m src.eval.run_all` first", file=sys.stderr)
        return 1
    metrics = _load_metrics()

    fig_portfolio_curves(FIGURES / "01_portfolio_curves.png")
    fig_cum_return_bar(metrics, FIGURES / "02_cum_return_bar.png")
    fig_sharpe_bar(metrics, FIGURES / "03_sharpe_bar.png")
    fig_decision_frequency(metrics, FIGURES / "04_decision_frequency.png")

    print(f"wrote 4 figures to {FIGURES}")
    for p in sorted(FIGURES.glob("*.png")):
        print(f"  {p.name}  ({p.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
