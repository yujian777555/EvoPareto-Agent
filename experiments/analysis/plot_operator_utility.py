"""Phase5-R2: paper-grade operator utility plots.

Outputs PNG+PDF into paper/figures/.
Figure A: utility vs generation (mean±std)
Figure B: selection probability vs generation
Figure C: usage / accepted / avg credit
Figure D: utility + HV overlay
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT_ANALYSIS = ROOT / "results" / "analysis"
FIG_DIR = ROOT / "paper" / "figures"

COLORS = {
    "planner": "#2b6cb0",
    "memory": "#2f855a",
    "reflection": "#c05621",
    "tool": "#6b46c1",
    "budget": "#b83280",
}


def _load(bench: str) -> dict:
    p = OUT_ANALYSIS / f"operator_utility_{bench}.json"
    return json.loads(p.read_text(encoding="utf-8"))


def _mean_std_plot(ax, gens, mean, std, label, color):
    ax.plot(gens, mean, label=label, color=color, linewidth=2)
    if any(s > 0 for s in std):
        lo = [m - s for m, s in zip(mean, std)]
        hi = [m + s for m, s in zip(mean, std)]
        ax.fill_between(gens, lo, hi, color=color, alpha=0.18, linewidth=0)


def plot_benchmark(bench: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    data = _load(bench)
    agg = data["aggregated"]
    gens = agg["generation"]
    ops = data["operators"]

    FIG_DIR.mkdir(parents=True, exist_ok=True)

    # Figure A: utility
    fig, ax = plt.subplots(figsize=(7.2, 4.4), dpi=160)
    for op in ops:
        d = agg["operators"][op]
        _mean_std_plot(ax, gens, d["utility_mean"], d["utility_std"], op, COLORS[op])
    ax.set_xlabel("Generation")
    ax.set_ylabel("Operator utility score")
    ax.set_title(f"Operator utility over generations ({bench})")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best", fontsize=9)
    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(FIG_DIR / f"operator_utility_{bench}.{ext}")
    plt.close(fig)

    # Figure B: probability
    fig, ax = plt.subplots(figsize=(7.2, 4.4), dpi=160)
    for op in ops:
        d = agg["operators"][op]
        _mean_std_plot(ax, gens, d["probability_mean"], d["probability_std"], op, COLORS[op])
    ax.set_xlabel("Generation")
    ax.set_ylabel("Selection probability")
    ax.set_title(f"Mutation selection probability ({bench})")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best", fontsize=9)
    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(FIG_DIR / f"operator_probability_{bench}.{ext}")
    plt.close(fig)

    # Figure C: usage / accepted / avg credit (3 panels)
    fig, axes = plt.subplots(1, 3, figsize=(11.5, 3.6), dpi=160)
    for ax, key, title in (
        (axes[0], "count_mean", "Usage count"),
        (axes[1], "accepted_mean", "Accepted offspring"),
        (axes[2], "avg_credit_mean", "Average credit"),
    ):
        for op in ops:
            d = agg["operators"][op]
            std_key = key.replace("_mean", "_std")
            _mean_std_plot(ax, gens, d[key], d.get(std_key, [0] * len(gens)), op, COLORS[op])
        ax.set_xlabel("Generation")
        ax.set_title(title)
        ax.grid(True, alpha=0.25)
    axes[0].set_ylabel("Count")
    axes[1].set_ylabel("Count")
    axes[2].set_ylabel("Credit")
    axes[2].legend(loc="best", fontsize=8)
    fig.suptitle(f"Operator usage and credit ({bench})")
    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(FIG_DIR / f"operator_usage_credit_{bench}.{ext}")
    plt.close(fig)

    # Figure D: HV + top utilities
    hvs = []
    # reconstruct mean HV from per-seed if present
    for run in data.get("per_seed", []):
        hvs.append([g["global_metrics"]["hypervolume"] for g in run["generations"]])
    if hvs:
        n = len(hvs[0])
        hv_mean = [sum(s[i] for s in hvs) / len(hvs) for i in range(n)]
        hv_std = [
            (sum((s[i] - hv_mean[i]) ** 2 for s in hvs) / len(hvs)) ** 0.5 for i in range(n)
        ]
    else:
        hv_mean, hv_std = [0] * len(gens), [0] * len(gens)

    fig, ax1 = plt.subplots(figsize=(7.2, 4.4), dpi=160)
    ax1.plot(gens, hv_mean, color="#1a202c", linewidth=2.2, label="HV")
    if any(s > 0 for s in hv_std):
        ax1.fill_between(
            gens,
            [m - s for m, s in zip(hv_mean, hv_std)],
            [m + s for m, s in zip(hv_mean, hv_std)],
            color="#1a202c", alpha=0.12, linewidth=0,
        )
    ax1.set_xlabel("Generation")
    ax1.set_ylabel("Hypervolume", color="#1a202c")
    ax2 = ax1.twinx()
    for op in ops:
        d = agg["operators"][op]
        ax2.plot(gens, d["utility_mean"], color=COLORS[op], linestyle="--", linewidth=1.6, label=f"{op} util")
    ax2.set_ylabel("Operator utility (dashed)")
    ax1.set_title(f"Utility vs search quality ({bench})")
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="best", fontsize=8)
    ax1.grid(True, alpha=0.2)
    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(FIG_DIR / f"operator_utility_vs_hv_{bench}.{ext}")
    plt.close(fig)

    # Single-seed diagnostic (seed 0 in per_seed)
    if data.get("per_seed"):
        run = data["per_seed"][0]
        fig, ax = plt.subplots(figsize=(7.2, 4.0), dpi=160)
        gens1 = [g["generation"] for g in run["generations"]]
        for op in ops:
            series = [g["operators"][op]["utility"] for g in run["generations"]]
            ax.plot(gens1, series, label=op, color=COLORS[op], linewidth=1.8)
        ax.set_xlabel("Generation")
        ax.set_ylabel("Utility score")
        ax.set_title(f"Operator utility — single seed ({bench}, seed={run['seed']})")
        ax.grid(True, alpha=0.25)
        ax.legend(loc="best", fontsize=9)
        fig.tight_layout()
        for ext in ("png", "pdf"):
            fig.savefig(FIG_DIR / f"operator_utility_{bench}_single_seed.{ext}")
        plt.close(fig)


def main() -> None:
    for bench in ("alfworld", "webshop"):
        print("plot", bench, flush=True)
        plot_benchmark(bench)
    print("Figures ->", FIG_DIR)


if __name__ == "__main__":
    main()
