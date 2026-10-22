"""Studio ss8, Steps 1-2: clean the raw JSONL benchmark log and compute statistics.

Input : data/raw/test_run.jsonl   (written by src/benchmark.py)
Output: data/processed/runs_clean.csv       one row per measured run, with flags
        data/processed/metrics_summary.csv  mean, SD, p50, p95, p99 and 95% bootstrap CIs
        data/processed/edge_cases.csv       outcome of each edge-case scenario

Log structure (one JSON object per line, discriminated by the "type" field):
    meta    first line: run_id, library versions, hardware, benchmark config
    run     one row per execution: phase, workload_n, duration_us, status, error
    summary last line: statistics computed by benchmark.py itself

Design decisions (explained in the README / report):
  * Warm-up rows are removed from the analysis, but counted and reported.
  * Errors are NEVER dropped silently: the error rate is a guardrail metric
    computed over ALL measured runs (ok + error), so failures cannot bias the
    sample (selection bias). Latency statistics later use status == "ok" rows.
  * Edge-case rows (phase == "edge") are correctness checks on bad input, not
    performance measurements, so they are analysed separately.
  * Outliers are only FLAGGED (Tukey fences, 1.5 x IQR, computed per workload
    size). No row is deleted.

Usage:
    python src/process_data.py
    python src/process_data.py --input data/raw/test_run.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW_PATH = ROOT / "data" / "raw" / "test_run.jsonl"
PROCESSED_DIR = ROOT / "data" / "processed"

# Phase that holds the real measurements. The studio text calls it "benchmark";
# our benchmark.py writes "measure". Change this one constant if yours differs.
MEASURE_PHASE = "measure"
WARMUP_PHASE = "warmup"
EDGE_PHASE = "edge"

VALID_PHASES = {WARMUP_PHASE, MEASURE_PHASE, EDGE_PHASE}
VALID_STATUS = {"ok", "error"}
REQUIRED_RUN_FIELDS = [
    "run_id", "seq", "phase", "workload_n", "ts_start_us", "duration_us", "status", "error",
]
# HTTP codes named in the assignment. Our benchmark is a local script, so none
# are expected; the check stays so the same code works for a networked service.
HTTP_ERROR_RE = re.compile(r"\b(429|500|504)\b")
IQR_FACTOR = 1.5

# Step 2 settings. Percentile bootstrap, the same idea seaborn uses for
# errorbar=("ci", 95): resample the runs with replacement, recompute the
# statistic, take the 2.5th and 97.5th percentile of the resampled values.
BOOT_RESAMPLES = 10_000
CI_LEVEL = 95
DEFAULT_SEED = 42


# --------------------------------------------------------------------------
# 1. Loading
# --------------------------------------------------------------------------
def load_jsonl(path: Path) -> tuple[dict, pd.DataFrame, dict | None]:
    """Parse the log. Returns (meta, runs_dataframe, summary_or_None).

    A corrupt LAST line (process killed while writing) is skipped with a
    warning. A corrupt line anywhere else is a hard error, because it means
    the file was damaged or edited.
    """
    if not path.exists():
        raise FileNotFoundError(f"log not found: {path}")

    lines = [(i, ln.strip()) for i, ln in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)]
    lines = [(i, ln) for i, ln in lines if ln]
    if not lines:
        raise ValueError(f"log is empty: {path}")

    meta: dict | None = None
    summary: dict | None = None
    runs: list[dict] = []
    for pos, (lineno, text) in enumerate(lines):
        try:
            rec = json.loads(text)
        except json.JSONDecodeError as exc:
            if pos == len(lines) - 1:
                print(f"WARNING: last line {lineno} is truncated and was skipped ({exc})", file=sys.stderr)
                continue
            raise ValueError(f"line {lineno}: invalid JSON ({exc})") from exc

        kind = rec.get("type")
        if kind == "meta":
            meta = rec
        elif kind == "run":
            runs.append(rec)
        elif kind == "summary":
            summary = rec
        else:
            raise ValueError(f"line {lineno}: unknown record type {kind!r}")

    if meta is None:
        raise ValueError("log has no 'meta' record (environment metadata is required for reproducibility)")
    if not runs:
        raise ValueError("log has no 'run' records")
    return meta, pd.DataFrame(runs), summary


# --------------------------------------------------------------------------
# 2. Schema validation
# --------------------------------------------------------------------------
def validate_runs(df: pd.DataFrame, meta: dict) -> list[str]:
    """Raise ValueError on structural problems; return a list of soft notes."""
    problems: list[str] = []
    notes: list[str] = []

    missing = [c for c in REQUIRED_RUN_FIELDS if c not in df.columns]
    if missing:
        raise ValueError(f"missing required fields: {missing}")

    if df["run_id"].nunique() != 1 or df["run_id"].iloc[0] != meta.get("run_id"):
        problems.append("run_id differs between meta and run records (mixed logs?)")
    if df["seq"].duplicated().any():
        problems.append(f"{int(df['seq'].duplicated().sum())} duplicated seq values")
    if not df["seq"].is_monotonic_increasing:
        problems.append("seq is not increasing (records out of order)")

    bad_phase = set(df["phase"].unique()) - VALID_PHASES
    if bad_phase:
        problems.append(f"unknown phase values: {sorted(bad_phase)}")
    bad_status = set(df["status"].unique()) - VALID_STATUS
    if bad_status:
        problems.append(f"unknown status values: {sorted(bad_status)}")

    dur = pd.to_numeric(df["duration_us"], errors="coerce")
    if dur.isna().any() or (dur <= 0).any():
        problems.append("duration_us must be a positive number in every row")
    if (df["status"].eq("ok") & df["error"].notna()).any():
        problems.append("rows with status 'ok' carry an error message")
    if (df["status"].eq("error") & df["error"].isna()).any():
        problems.append("rows with status 'error' have no error message")

    # The run counts must match the config that was logged in `meta`.
    cfg = meta.get("benchmark", {})
    for phase, key in ((WARMUP_PHASE, "warmup_runs"), (MEASURE_PHASE, "measured_runs")):
        if key in cfg:
            got = int((df["phase"] == phase).sum())
            if got != cfg[key]:
                problems.append(f"{phase}: expected {cfg[key]} runs from config, found {got}")
    sizes = set(cfg.get("workload_sizes", []))
    if sizes:
        stray = set(df.loc[df["phase"].isin([WARMUP_PHASE, MEASURE_PHASE]), "workload_n"]) - sizes
        if stray:
            problems.append(f"workload_n outside configured sizes: {sorted(stray)}")

    if problems:
        raise ValueError("schema validation failed:\n  - " + "\n  - ".join(problems))
    return notes


# --------------------------------------------------------------------------
# 3. Cleaning: warm-up, errors (guardrail), outliers (non-destructive)
# --------------------------------------------------------------------------
def classify_error(msg: object) -> str:
    """'none' | 'http' (429/500/504 in the message) | 'runtime' (everything else)."""
    if msg is None or (isinstance(msg, float) and np.isnan(msg)):
        return "none"
    return "http" if HTTP_ERROR_RE.search(str(msg)) else "runtime"


def guardrail_error_rate(df: pd.DataFrame) -> pd.DataFrame:
    """Error rate over ALL measured runs, overall and per workload size."""
    def _rate(g: pd.DataFrame) -> pd.Series:
        n_err = int((g["status"] == "error").sum())
        return pd.Series({
            "n_runs": len(g),
            "n_ok": len(g) - n_err,
            "n_error": n_err,
            "n_http_error": int((g["error_kind"] == "http").sum()),
            "error_rate": n_err / len(g),
        })

    by_n = df.groupby("workload_n").apply(_rate, include_groups=False)
    overall = _rate(df).to_frame("all").T
    overall.index.name = "workload_n"
    return pd.concat([overall, by_n])


def flag_outliers_iqr(df: pd.DataFrame, factor: float = IQR_FACTOR) -> pd.DataFrame:
    """Add is_outlier_iqr / outlier_side using Tukey fences per workload size.

    Fences are computed on status == 'ok' rows only and applied to those rows.
    Nothing is removed: later steps decide how to treat flagged rows.
    """
    out = df.copy()
    out["is_outlier_iqr"] = False
    out["outlier_side"] = ""
    ok = out["status"] == "ok"
    grp = out.loc[ok].groupby("workload_n")["duration_us"]
    q1, q3 = grp.transform(lambda s: s.quantile(0.25)), grp.transform(lambda s: s.quantile(0.75))
    iqr = q3 - q1
    lo, hi = q1 - factor * iqr, q3 + factor * iqr
    d = out.loc[ok, "duration_us"]
    out.loc[ok, "is_outlier_iqr"] = (d < lo) | (d > hi)
    out.loc[ok, "outlier_side"] = np.where(d > hi, "high", np.where(d < lo, "low", ""))
    return out


def summarize_edge_cases(df: pd.DataFrame) -> pd.DataFrame:
    """One row per edge-case scenario: was the bad input rejected or processed?"""
    rows = []
    for case, g in df.groupby("edge_case", sort=False):
        n_err = int((g["status"] == "error").sum())
        rows.append({
            "edge_case": case,
            "runs": len(g),
            "errors": n_err,
            "outcome": "rejected" if n_err == len(g) else ("processed" if n_err == 0 else "mixed"),
            "median_duration_us": float(g["duration_us"].median()),
            "first_error": g["error"].dropna().iloc[0] if n_err else "",
        })
    return pd.DataFrame(rows)


def clean(df: pd.DataFrame) -> dict[str, pd.DataFrame | int]:
    """Split the log by phase and apply the Step 1 cleaning rules."""
    df = df.copy()
    df["error_kind"] = df["error"].map(classify_error)
    df["duration_ms"] = df["duration_us"] / 1000.0

    warmup = df[df["phase"] == WARMUP_PHASE]
    measured = df[df["phase"] == MEASURE_PHASE].copy()
    edge = df[df["phase"] == EDGE_PHASE]

    measured = flag_outliers_iqr(measured)
    return {
        "n_warmup_removed": len(warmup),
        "measured": measured,
        "edge": edge,
        "guardrail": guardrail_error_rate(measured),
        "edge_summary": summarize_edge_cases(edge) if len(edge) else pd.DataFrame(),
    }


# --------------------------------------------------------------------------
# 4. Step 2: aggregation, statistics, bootstrap confidence intervals
# --------------------------------------------------------------------------
# Each statistic reduces a (n_resamples, n_runs) matrix along axis 1.
_STATS = {
    "mean": lambda a: a.mean(axis=1),
    "p50": lambda a: np.median(a, axis=1),
    "p95": lambda a: np.percentile(a, 95, axis=1),
    "p99": lambda a: np.percentile(a, 99, axis=1),
}


def bootstrap_ci(values: np.ndarray, stat: str, rng: np.random.Generator) -> tuple[float, float]:
    """95% percentile-bootstrap confidence interval of one statistic."""
    values = np.asarray(values, dtype=float)
    idx = rng.integers(0, len(values), size=(BOOT_RESAMPLES, len(values)))
    boot = _STATS[stat](values[idx])
    lo, hi = np.percentile(boot, [(100 - CI_LEVEL) / 2, 100 - (100 - CI_LEVEL) / 2])
    return float(lo), float(hi)


def describe(values: np.ndarray, prefix: str, ci_stats: tuple[str, ...], rng: np.random.Generator) -> dict:
    """Mean, SD (n-1), p25, p50, p75, p95, p99 and bootstrap CIs for `ci_stats`."""
    v = np.asarray(values, dtype=float)
    row = {
        f"{prefix}_mean": v.mean(),
        f"{prefix}_sd": v.std(ddof=1),
        f"{prefix}_p25": np.percentile(v, 25),
        f"{prefix}_p50": np.median(v),
        f"{prefix}_p75": np.percentile(v, 75),
        f"{prefix}_p95": np.percentile(v, 95),
        f"{prefix}_p99": np.percentile(v, 99),
    }
    for stat in ci_stats:
        lo, hi = bootstrap_ci(v, stat, rng)
        row[f"{prefix}_{stat}_ci_lo"] = lo
        row[f"{prefix}_{stat}_ci_hi"] = hi
    return row


def compute_metrics(measured: pd.DataFrame, seed: int = DEFAULT_SEED) -> pd.DataFrame:
    """One row per workload size plus an 'all' row (latency only).

    Latency (ms) comes from every successful measured run, outliers included:
    flagged spikes are real behaviour of the system, so they stay in the
    statistics (the median and percentiles are robust to them anyway).
    Throughput (respondents/s) = workload_n / run duration. It is only
    comparable inside one workload size, so the 'all' row leaves it empty.
    """
    rng = np.random.default_rng(seed)
    ok_all = measured[measured["status"] == "ok"].copy()
    ok_all["throughput_rps"] = ok_all["workload_n"] / (ok_all["duration_us"] / 1e6)

    rows = []
    groups = [(str(n), measured[measured["workload_n"] == n], ok_all[ok_all["workload_n"] == n])
              for n in sorted(measured["workload_n"].unique())]
    groups.append(("all", measured, ok_all))

    for label, m, ok in groups:
        row = {
            "workload_n": label,
            "n_runs": len(m),
            "n_ok": len(ok),
            "error_rate": float((m["status"] == "error").mean()),
            "n_outliers_iqr": int(m["is_outlier_iqr"].sum()),
            "ci_level": CI_LEVEL,
            "ci_n_boot": BOOT_RESAMPLES,
            "seed": seed,
        }
        row.update(describe(ok["duration_ms"], "latency_ms", ("mean", "p50", "p95", "p99"), rng))
        if label != "all":
            row.update(describe(ok["throughput_rps"], "throughput_rps", ("mean", "p50"), rng))
        rows.append(row)
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# 5. Report + export
# --------------------------------------------------------------------------
def print_report(meta: dict, res: dict) -> None:
    m: pd.DataFrame = res["measured"]
    ok = m[m["status"] == "ok"]
    print(f"run_id {meta['run_id']}  |  python {meta.get('python')}  |  docker: {meta.get('in_docker')}")
    print(f"warm-up rows removed : {res['n_warmup_removed']}")
    print(f"measured rows kept   : {len(m)}  (ok: {len(ok)})")
    print(f"edge-case rows       : {len(res['edge'])}  (analysed separately)")
    print("\nGuardrail metric: error rate over ALL measured runs")
    print(res["guardrail"].to_string(float_format=lambda x: f"{x:.4f}"))
    n_out = int(m["is_outlier_iqr"].sum())
    print(f"\nIQR outliers flagged (kept, not deleted): {n_out} of {len(ok)}")
    if n_out:
        cols = ["seq", "workload_n", "duration_ms", "outlier_side"]
        print(m.loc[m["is_outlier_iqr"], cols].to_string(index=False, float_format=lambda x: f"{x:.2f}"))
    if len(res["edge_summary"]):
        print("\nEdge cases (expected: bad input is rejected, not silently processed)")
        print(res["edge_summary"][["edge_case", "runs", "errors", "outcome"]].to_string(index=False))


def print_metrics(metrics: pd.DataFrame, seed: int) -> None:
    print(f"\nStep 2: summary statistics ({CI_LEVEL}% bootstrap CI, {BOOT_RESAMPLES} resamples, seed {seed})")
    lat = metrics[["workload_n", "n_ok", "latency_ms_mean", "latency_ms_sd", "latency_ms_p50",
                   "latency_ms_p95", "latency_ms_p99"]]
    print("Latency (ms):")
    print(lat.to_string(index=False, float_format=lambda x: f"{x:.2f}"))
    print("Median latency with 95% CI (ms):")
    for _, r in metrics.iterrows():
        print(f"  n={r['workload_n']:>4}: {r['latency_ms_p50']:.2f}  [{r['latency_ms_p50_ci_lo']:.2f}, "
              f"{r['latency_ms_p50_ci_hi']:.2f}]")
    thr = metrics[metrics["workload_n"] != "all"][["workload_n", "throughput_rps_mean", "throughput_rps_sd",
                                                     "throughput_rps_p50", "throughput_rps_p95",
                                                     "throughput_rps_p99"]]
    print("Throughput (respondents/s):")
    print(thr.to_string(index=False, float_format=lambda x: f"{x:.0f}"))


def export(res: dict, metrics: pd.DataFrame, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    keep = ["run_id", "seq", "phase", "workload_n", "ts_start_us", "duration_us", "duration_ms",
            "status", "error_kind", "is_outlier_iqr", "outlier_side"]
    res["measured"][keep].to_csv(out_dir / "runs_clean.csv", index=False)
    metrics.to_csv(out_dir / "metrics_summary.csv", index=False, float_format="%.6g")
    if len(res["edge_summary"]):
        res["edge_summary"].to_csv(out_dir / "edge_cases.csv", index=False)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", type=Path, default=RAW_PATH)
    ap.add_argument("--out-dir", type=Path, default=PROCESSED_DIR)
    args = ap.parse_args(argv)

    meta, df, _summary = load_jsonl(args.input)
    validate_runs(df, meta)
    res = clean(df)
    seed = int(meta.get("seed", DEFAULT_SEED))  # same seed as the benchmark -> reproducible CIs
    metrics = compute_metrics(res["measured"], seed=seed)
    print_report(meta, res)
    print_metrics(metrics, seed)
    export(res, metrics, args.out_dir)
    print(f"\nSaved to {args.out_dir}: runs_clean.csv, metrics_summary.csv, edge_cases.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
