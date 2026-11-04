"""Studio ss9, Step 3: one multi-panel, publication-ready figure.

Input : data/processed/metrics_summary.csv and data/processed/runs_clean.csv
        (written by src/process_data.py, see ss8)
Output: reports/figures/fig_combined_latency_throughput.{pdf,png,svg}
        with --split also fig_panel_a/b/c.{pdf,png,svg} (for LaTeX subcaption)

Panels
  (a) latency percentiles p50/p95/p99 versus workload size, 95% bootstrap CI bands
  (b) median throughput versus workload size, log axis
  (c) distribution of per-run latency (violins), IQR outliers marked

Size and fonts
  The figure is drawn at its FINAL printed size (7.16 in = IEEE \\textwidth, change with
  --width) with fonts of 7-8.5 pt. In LaTeX it is included at scale 1
  (\\includegraphics[width=\\textwidth]{...}), so a 7.5 pt tick label is 7.5 pt on paper.
  For a single column use --width 3.5 together with --split and place the panels
  two per row.

Usage:
    python src/visualize_combined.py
    python src/visualize_combined.py --split
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # no display needed (works in Docker / CI)
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.collections import PolyCollection
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

from visualize import FIG_DIR, LATENCY_YMAX, METRICS_CSV, RUNS_CSV, load_inputs

FULL_WIDTH_IN = 7.16  # IEEE two-column \textwidth in inches
HEIGHT_IN = 2.85
X_LABEL = "Workload n (respondents, log scale)"
STEM = "fig_combined_latency_throughput"


# --------------------------------------------------------------------------
# Style: sizes are in points at the final printed size
# --------------------------------------------------------------------------
def set_style() -> list:
    sns.set_theme(
        style="whitegrid",
        context="paper",
        palette="colorblind",
        rc={
            "font.size": 8,
            "axes.labelsize": 8.5,
            "axes.titlesize": 8.5,
            "xtick.labelsize": 7.5,
            "ytick.labelsize": 7.5,
            "legend.fontsize": 7,
            "lines.linewidth": 1.4,
            "lines.markersize": 4.5,
            "axes.linewidth": 0.6,
            "grid.linewidth": 0.4,
            "hatch.linewidth": 0.6,
            "legend.frameon": False,
            "figure.dpi": 100,
            "savefig.dpi": 300,
            "savefig.bbox": "standard",  # keep the exact figsize, so the printed size is what we set
            "pdf.fonttype": 42,   # embed real fonts in the PDF (journals require it)
            "ps.fonttype": 42,
            "svg.fonttype": "path",  # text as outlines: looks the same on every computer
            "svg.hashsalt": "teacher-burnout-study",  # fixed ids -> byte-identical SVG on re-runs
        },
    )
    return sns.color_palette("colorblind")


def log_x(ax: plt.Axes, sizes: np.ndarray) -> None:
    """Log x axis with ticks only at the measured workload sizes."""
    ax.set_xscale("log")
    ax.set_xticks(sizes)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.0f}"))
    ax.xaxis.set_minor_formatter(mticker.NullFormatter())
    ax.set_xlim(sizes.min() / 1.35, sizes.max() * 1.35)
    ax.set_xlabel(X_LABEL)


# --------------------------------------------------------------------------
# Panels (each draws into a given Axes, so the same code serves both layouts)
# --------------------------------------------------------------------------
SERIES = [  # key, label, palette index, line style, marker
    ("p50", "p50 (median)", 0, "-", "o"),
    ("p95", "p95", 1, "--", "s"),
    ("p99", "p99", 2, ":", "^"),
]


def panel_a(ax: plt.Axes, metrics: pd.DataFrame, palette: list) -> None:
    x = metrics["n"].to_numpy()
    ax.fill_between(x, metrics["latency_ms_p25"], metrics["latency_ms_p75"], facecolor="0.85",
                    edgecolor="0.45", hatch="////", linewidth=0, zorder=1)
    for key, label, ci, ls, marker in SERIES:
        color = palette[ci]
        ax.fill_between(x, metrics[f"latency_ms_{key}_ci_lo"], metrics[f"latency_ms_{key}_ci_hi"],
                        color=color, alpha=0.22, linewidth=0, zorder=2)
        ax.plot(x, metrics[f"latency_ms_{key}"], color=color, linestyle=ls, marker=marker,
                markeredgecolor="white", markeredgewidth=0.6, label=label, zorder=3)
        ax.annotate(key, (x[-1], metrics[f"latency_ms_{key}"].iloc[-1]), xytext=(5, 0),
                    textcoords="offset points", va="center", ha="left", fontsize=7)
    log_x(ax, x)
    ax.set_ylim(0, LATENCY_YMAX)
    ax.set_ylabel("Latency (ms)")


def panel_b(ax: plt.Axes, metrics: pd.DataFrame, palette: list) -> None:
    x = metrics["n"].to_numpy()
    color = palette[0]
    ax.fill_between(x, metrics["throughput_rps_p50_ci_lo"], metrics["throughput_rps_p50_ci_hi"],
                    color=color, alpha=0.22, linewidth=0, zorder=2)
    ax.plot(x, metrics["throughput_rps_p50"], color=color, linestyle="-", marker="o",
            markeredgecolor="white", markeredgewidth=0.6, zorder=3)
    log_x(ax, x)
    ax.set_yscale("log")
    ax.set_ylim(400, 40000)
    ax.set_yticks([500, 1000, 2000, 5000, 10000, 20000])
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.yaxis.set_minor_formatter(mticker.NullFormatter())
    ax.set_ylabel("Throughput (respondents/s, log scale)")


def panel_c(ax: plt.Axes, runs: pd.DataFrame, palette: list) -> None:
    sizes = sorted(runs["workload_n"].unique())
    order = [str(n) for n in sizes]
    d = runs.assign(n_label=runs["workload_n"].astype(str))
    colors = palette[: len(sizes)]
    hatches = ["", "//", ".."][: len(sizes)]

    sns.violinplot(data=d, x="n_label", y="duration_ms", hue="n_label", order=order, hue_order=order,
                   palette=colors, legend=False, inner="box", cut=0, density_norm="width",
                   linewidth=0.8, saturation=0.9, ax=ax)
    bodies = [c for c in ax.collections if isinstance(c, PolyCollection)]
    for body, hatch in zip(bodies, hatches):
        body.set_hatch(hatch)  # second cue besides colour (black-and-white print)
        body.set_alpha(0.75)

    out = d[d["is_outlier_iqr"]]
    ax.scatter([order.index(s) for s in out["n_label"]], out["duration_ms"], marker="x", s=18,
               color="black", linewidths=0.9, zorder=5)

    counts = d.groupby("n_label").size()
    ax.set_xticks(range(len(order)))
    ax.set_xticklabels(order)
    ax.set_ylim(0, LATENCY_YMAX)
    runs_each = int(counts.iloc[0]) if counts.nunique() == 1 else None  # same number of runs per size
    ax.set_xlabel(f"n ({runs_each} runs each)" if runs_each else "Workload n (respondents)")
    ax.set_ylabel("Latency (ms)")


def legend_handles(palette: list) -> list:
    handles = [Line2D([0], [0], color=palette[ci], linestyle=ls, marker=m, markeredgecolor="white",
                      label=lab) for _, lab, ci, ls, m in SERIES]
    handles += [
        Patch(facecolor="0.85", edgecolor="0.45", hatch="////", label="p25-p75 of runs"),
        Patch(facecolor="0.6", alpha=0.35, label="95% bootstrap CI"),
        Line2D([0], [0], marker="x", color="black", linestyle="", markersize=4.5,
               label="IQR outlier (kept)"),
    ]
    return handles


# --------------------------------------------------------------------------
# Figures
# --------------------------------------------------------------------------
def build_combined(metrics: pd.DataFrame, runs: pd.DataFrame, palette: list, width: float) -> plt.Figure:
    fig, (a, b, c) = plt.subplots(1, 3, figsize=(width, HEIGHT_IN), layout="constrained",
                                  gridspec_kw={"width_ratios": [1.15, 1.0, 0.85]})
    fig.get_layout_engine().set(w_pad=0.04, wspace=0.06)
    panel_a(a, metrics, palette)
    panel_b(b, metrics, palette)
    panel_c(c, runs, palette)
    a.set_title("(a) Latency percentiles", loc="left")
    b.set_title("(b) Median throughput", loc="left")
    c.set_title("(c) Latency distribution", loc="left")
    fig.legend(handles=legend_handles(palette), loc="outside lower center", ncol=6,
               columnspacing=1.0, handlelength=2.0)
    return fig


def build_panel(which: str, metrics: pd.DataFrame, runs: pd.DataFrame, palette: list,
                width: float) -> plt.Figure:
    """One panel as its own figure (no title, no legend: LaTeX subcaption and the caption supply them)."""
    fig, ax = plt.subplots(figsize=(width / 3.05, HEIGHT_IN * 0.8), layout="constrained")
    {"a": lambda: panel_a(ax, metrics, palette),
     "b": lambda: panel_b(ax, metrics, palette),
     "c": lambda: panel_c(ax, runs, palette)}[which]()
    # narrow panels: shorter labels so nothing is clipped (the caption explains "log scale")
    if which in "ab":
        ax.set_xlabel("Workload n (log)")
    if which == "b":
        ax.set_ylabel("Throughput (resp./s, log)")
    return fig


def save(fig: plt.Figure, stem: str, out_dir: Path, formats: list[str]) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for ext in formats:
        kw: dict = {}
        if ext == "pdf":
            kw["metadata"] = {"CreationDate": None}   # byte-identical re-runs
        elif ext == "svg":
            kw["metadata"] = {"Date": None}
        elif ext == "png":
            kw["dpi"] = 300
        path = out_dir / f"{stem}.{ext}"
        fig.savefig(path, **kw)
        written.append(path)
    plt.close(fig)
    return written


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--metrics", type=Path, default=METRICS_CSV)
    ap.add_argument("--runs", type=Path, default=RUNS_CSV)
    ap.add_argument("--out-dir", type=Path, default=FIG_DIR)
    ap.add_argument("--width", type=float, default=FULL_WIDTH_IN, help="figure width in inches")
    ap.add_argument("--formats", default="pdf,png,svg")
    ap.add_argument("--split", action="store_true", help="also write each panel as its own file")
    args = ap.parse_args(argv)

    formats = [f.strip() for f in args.formats.split(",") if f.strip()]
    palette = set_style()
    metrics, runs = load_inputs(args.metrics, args.runs)

    written = save(build_combined(metrics, runs, palette, args.width), STEM, args.out_dir, formats)
    if args.split:
        for which in "abc":
            written += save(build_panel(which, metrics, runs, palette, args.width),
                            f"fig_panel_{which}", args.out_dir, formats)
    for p in written:
        print(f"saved {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
