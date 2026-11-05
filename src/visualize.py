"""Final figures (ss8 steps 3-4, Task 3): publication-ready figures from the processed data.

Input : data/processed/metrics_summary.csv   (written by src/process_data.py)
        data/processed/runs_clean.csv
Output: reports/figures/fig1_latency_vs_load.{pdf,png}
        reports/figures/fig2_distribution_boxplot.{pdf,png}
        reports/figures/captions.md

The three rules of scientific graphics, and where they are applied:

  Rule 1  Axes and scaling
          - every axis has a variable name AND a unit: "Latency (ms)"
          - latency axes start at 0; the throughput axis spans more than one
            order of magnitude, so it uses a logarithmic scale (labelled "log scale")
          - tick positions are set explicitly (only the workload sizes that exist)
          - seaborn font_scale=1.2 keeps text readable at column width in a PDF

  Rule 2  Confidence intervals and variance
          - shaded bands = 95% bootstrap CI of each statistic (same percentile
            bootstrap idea as seaborn errorbar=("ci", 95); numbers come from
            metrics_summary.csv, so figure and table always agree)
          - grey hatched band = p25-p75 of the runs, because latency is right-skewed
          - the box plot shows every single run, the 95% bootstrap CI of the median, and IQR outliers

  Rule 3  Colour and accessibility
          - sns.set_theme(style="whitegrid") with the colour-blind-safe palette
          - colour is never the only cue: each series also has its own line style
            and marker, and boxes carry hatching, so black-and-white print works

Usage:
    python src/visualize.py
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

ROOT = Path(__file__).resolve().parents[1]
METRICS_CSV = ROOT / "data" / "processed" / "metrics_summary.csv"
RUNS_CSV = ROOT / "data" / "processed" / "runs_clean.csv"
FIG_DIR = ROOT / "reports" / "figures"

LATENCY_YMAX = 100  # ms; latency axes always start at 0 (Rule 1)
X_LABEL = "Workload n (respondents, log scale)"


# --------------------------------------------------------------------------
# Style (Rule 1 font size, Rule 3 theme and palette)
# --------------------------------------------------------------------------
def set_publication_style() -> list:
    """Apply the publication theme; return the colour-blind-safe palette."""
    sns.set_theme(
        style="whitegrid",
        context="paper",
        font_scale=1.2,
        palette="colorblind",
        rc={
            "figure.dpi": 100,
            "savefig.dpi": 300,
            "savefig.bbox": "tight",
            "lines.linewidth": 1.8,
            "lines.markersize": 6,
            "legend.frameon": False,
            "hatch.linewidth": 0.8,
            "pdf.fonttype": 42,  # embed real fonts in the PDF (journals require it)
            "ps.fonttype": 42,
        },
    )
    return sns.color_palette("colorblind")


def load_inputs(metrics_csv: Path, runs_csv: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    for p in (metrics_csv, runs_csv):
        if not p.exists():
            raise FileNotFoundError(f"{p} not found. Run `python src/process_data.py` first.")
    metrics = pd.read_csv(metrics_csv, dtype={"workload_n": str})
    metrics = metrics[metrics["workload_n"] != "all"].copy()
    metrics["n"] = metrics["workload_n"].astype(int)
    metrics = metrics.sort_values("n").reset_index(drop=True)
    runs = pd.read_csv(runs_csv)
    runs = runs[runs["status"] == "ok"].copy()
    return metrics, runs


def _log_x_axis(ax: plt.Axes, sizes: np.ndarray) -> None:
    """Log x axis with ticks only at the workload sizes that were measured."""
    ax.set_xscale("log")
    ax.set_xticks(sizes)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.xaxis.set_minor_formatter(mticker.NullFormatter())
    ax.set_xlim(sizes.min() / 1.35, sizes.max() * 1.35)
    ax.set_xlabel(X_LABEL)


# --------------------------------------------------------------------------
# Figure 1: primary metric vs workload
# --------------------------------------------------------------------------
def plot_latency_vs_workload(metrics: pd.DataFrame, palette: list) -> plt.Figure:
    x = metrics["n"].to_numpy()
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(8.4, 3.6), layout="constrained",
                                  gridspec_kw={"width_ratios": [1.1, 1]})
    fig.get_layout_engine().set(w_pad=0.08, wspace=0.12)

    # --- (a) latency percentiles with 95% bootstrap CI --------------------
    series = [  # key, label, colour, line style, marker
        ("p50", "p50 (median)", palette[0], "-", "o"),
        ("p95", "p95", palette[1], "--", "s"),
        ("p99", "p99", palette[2], ":", "^"),
    ]
    ax.fill_between(x, metrics["latency_ms_p25"], metrics["latency_ms_p75"], facecolor="0.85",
                    edgecolor="0.45", hatch="////", linewidth=0, zorder=1)
    for key, label, color, ls, marker in series:
        ax.fill_between(x, metrics[f"latency_ms_{key}_ci_lo"], metrics[f"latency_ms_{key}_ci_hi"],
                        color=color, alpha=0.22, linewidth=0, zorder=2)
        ax.plot(x, metrics[f"latency_ms_{key}"], color=color, linestyle=ls, marker=marker,
                markeredgecolor="white", markeredgewidth=0.8, label=label, zorder=3)
        ax.annotate(key, (x[-1], metrics[f"latency_ms_{key}"].iloc[-1]), xytext=(7, 0),
                    textcoords="offset points", va="center", ha="left", fontsize=10)
    _log_x_axis(ax, x)
    ax.set_ylim(0, LATENCY_YMAX)
    ax.set_ylabel("Latency (ms)")
    ax.set_title("(a) Latency percentiles", loc="left", fontsize=11)

    # --- (b) throughput: spans orders of magnitude -> log scale ------------
    color = palette[0]
    ax2.fill_between(x, metrics["throughput_rps_p50_ci_lo"], metrics["throughput_rps_p50_ci_hi"],
                     color=color, alpha=0.22, linewidth=0, zorder=2)
    ax2.plot(x, metrics["throughput_rps_p50"], color=color, linestyle="-", marker="o",
             markeredgecolor="white", markeredgewidth=0.8, zorder=3)
    _log_x_axis(ax2, x)
    ax2.set_yscale("log")
    ax2.set_ylim(400, 40000)
    ax2.set_yticks([500, 1000, 2000, 5000, 10000, 20000])
    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax2.yaxis.set_minor_formatter(mticker.NullFormatter())
    ax2.set_ylabel("Throughput (respondents/s, log scale)")
    ax2.set_title("(b) Median throughput", loc="left", fontsize=11)

    handles = [Line2D([0], [0], color=c, linestyle=ls, marker=m, markeredgecolor="white", label=lab)
               for _, lab, c, ls, m in series]
    handles += [
        Patch(facecolor="0.85", edgecolor="0.45", hatch="////", label="p25-p75 of runs"),
        Patch(facecolor="0.6", alpha=0.35, label="95% bootstrap CI (shaded)"),
    ]
    fig.legend(handles=handles, loc="outside lower center", ncol=5, fontsize=9.5, columnspacing=1.2,
               handlelength=2.2)
    return fig


# --------------------------------------------------------------------------
# Figure 2: distribution and outliers
# --------------------------------------------------------------------------
def plot_latency_distribution(runs: pd.DataFrame, metrics: pd.DataFrame, palette: list) -> plt.Figure:
    """Box plot of the measured runs per workload, with every run drawn and the 95% CI of the median."""
    sizes = sorted(runs["workload_n"].unique())
    order = [str(n) for n in sizes]
    d = runs.assign(n_label=runs["workload_n"].astype(str))
    colors = palette[: len(sizes)]
    hatches = ["", "//", ".."][: len(sizes)]
    ci = metrics.set_index("n")

    fig, ax = plt.subplots(figsize=(5.2, 3.9), layout="constrained")
    sns.boxplot(data=d, x="n_label", y="duration_ms", hue="n_label", order=order, hue_order=order,
                palette=colors, legend=False, showfliers=False, width=0.5, linewidth=1.0,
                saturation=0.9, boxprops={"alpha": 0.75}, ax=ax)
    for patch, hatch in zip(ax.patches, hatches):
        patch.set_hatch(hatch)  # second cue besides colour (black-and-white print)

    rng = np.random.default_rng(42)  # fixed seed: the horizontal jitter is reproducible
    for i, s in enumerate(order):
        sub = d[d["n_label"] == s]
        inl, out = sub[~sub["is_outlier_iqr"]], sub[sub["is_outlier_iqr"]]
        ax.scatter(i + rng.uniform(-0.17, 0.17, len(inl)), inl["duration_ms"], s=7, color="0.25",
                   alpha=0.55, linewidths=0, zorder=4)
        ax.scatter(i + rng.uniform(-0.12, 0.12, len(out)), out["duration_ms"], marker="x", s=34,
                   color="black", linewidths=1.3, zorder=5)
        row = ci.loc[int(s)]  # 95% bootstrap CI of the median, same numbers as the table
        ax.errorbar(i, row["latency_ms_p50"],
                    yerr=[[row["latency_ms_p50"] - row["latency_ms_p50_ci_lo"]],
                          [row["latency_ms_p50_ci_hi"] - row["latency_ms_p50"]]],
                    fmt="D", color="black", markerfacecolor="white", markersize=5, capsize=5,
                    elinewidth=1.4, zorder=6)

    counts = d.groupby("n_label").size()
    ax.set_xticks(range(len(order)))
    ax.set_xticklabels([f"{s}\n({counts[s]} runs)" for s in order])
    ax.set_ylim(0, LATENCY_YMAX)
    ax.set_xlabel("Workload size, n (respondents)")
    ax.set_ylabel("Latency (ms)")

    handles = [
        Patch(facecolor="0.8", edgecolor="black", label="Box: p25-p50-p75, whiskers 1.5 x IQR"),
        Line2D([0], [0], marker="o", color="0.25", linestyle="", markersize=3, alpha=0.7, label="Single run"),
        Line2D([0], [0], marker="D", color="black", markerfacecolor="white", markersize=5, label="Median, 95% bootstrap CI"),
        Line2D([0], [0], marker="x", color="black", linestyle="", markersize=6, label="IQR outlier (kept in statistics)"),
    ]
    ax.legend(handles=handles, loc="upper left", fontsize=8)
    return fig


# --------------------------------------------------------------------------
# Export (Step 4)
# --------------------------------------------------------------------------
CAPTIONS = """# Figure captions

**Figure 1. Latency and throughput of the analysis script versus workload size.**
(a) Latency percentiles p50, p95 and p99. Lines show the statistic, coloured bands show its 95%
percentile-bootstrap confidence interval ({boot} resamples of the {per_size} measured runs per size),
and the grey hatched band shows the p25-p75 range of the runs. (b) Median throughput (respondents
processed per second) with its 95% bootstrap CI; both axes are logarithmic. Warm-up runs excluded.
With 40 runs per size, p99 is determined by the slowest one or two runs, so its interval is wide.

**Figure 2. Distribution of latency per workload size.**
Boxes mark p25, p50 and p75 of the {total} measured runs (whiskers 1.5 x IQR); dots are the single runs.
The white diamond with an error bar is the median with its 95% bootstrap CI. Crosses mark runs outside
1.5 x IQR of their workload size. They are flagged, not removed. Latency axis starts at 0 ms.
"""


def save_figure(fig: plt.Figure, name: str, out_dir: Path) -> list[Path]:
    """Vector PDF for the paper/LaTeX and 300 DPI PNG for web/GitHub."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = [out_dir / f"{name}.pdf", out_dir / f"{name}.png"]
    # CreationDate=None keeps the PDF byte-identical between runs (no timestamp inside),
    # so re-running the script does not show up as a change in git.
    fig.savefig(paths[0], metadata={"CreationDate": None})
    fig.savefig(paths[1], dpi=300)
    plt.close(fig)
    return paths


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--metrics", type=Path, default=METRICS_CSV)
    ap.add_argument("--runs", type=Path, default=RUNS_CSV)
    ap.add_argument("--out-dir", type=Path, default=FIG_DIR)
    args = ap.parse_args(argv)

    palette = set_publication_style()
    metrics, runs = load_inputs(args.metrics, args.runs)

    written: list[Path] = []
    written += save_figure(plot_latency_vs_workload(metrics, palette), "fig1_latency_vs_load", args.out_dir)
    written += save_figure(plot_latency_distribution(runs, metrics, palette), "fig2_distribution_boxplot", args.out_dir)

    (args.out_dir / "captions.md").write_text(
        CAPTIONS.format(boot=f"{int(metrics['ci_n_boot'].iloc[0]):,}", per_size=int(metrics["n_ok"].iloc[0]),
                        total=len(runs)),
        encoding="utf-8")
    for p in written:
        print(f"saved {p.relative_to(ROOT) if p.is_relative_to(ROOT) else p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())