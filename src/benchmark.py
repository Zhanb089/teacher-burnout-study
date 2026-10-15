"""Analysis pipeline and measurement harness for the teacher burnout study.

Reads a questionnaire CSV, scores the three burnout scales, checks the
guardrail metrics and runs the planned comparisons (RQ1-RQ3).
Everything is controlled by config.yaml.

Two modes.

1) Analyse the questionnaire (default). Prints a log and writes results/:

    python src/benchmark.py --config config.yaml

2) Measure the analysis itself. Warm-up runs and timed runs on synthetic
respondents, one JSON line per run in data/raw/test_run.jsonl:

    python src/benchmark.py --config config.yaml --bench

The measured function is `analyze()`. It does no printing and no file I/O, so the
stopwatch sees only the computation. All logging and file writing happen
before or after the timed part.
"""
import argparse
import gc
import hashlib
import json
import logging
import os
import platform
import random
import subprocess
import sys
import time
import uuid
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from scipy import stats

LOG = logging.getLogger("burnout")


def load_config(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def setup_logging(log_path):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(message)s")
    LOG.setLevel(logging.INFO)
    LOG.handlers.clear()
    for handler in (logging.StreamHandler(sys.stdout),
                    logging.FileHandler(log_path, mode="w", encoding="utf-8")):
        handler.setFormatter(fmt)
        LOG.addHandler(handler)


def score_scales(df, keys):
    """Sum item scores per scale (items are columns q1..q22)."""
    for scale, items in keys.items():
        df[scale] = df[[f"q{i}" for i in items]].sum(axis=1)
    return df


def cronbach_alpha(items):
    k = items.shape[1]
    total_var = items.sum(axis=1).var(ddof=1)
    if k < 2 or total_var == 0 or np.isnan(total_var):
        return float("nan")
    return float(k / (k - 1) * (1 - items.var(axis=0, ddof=1).sum() / total_var))


def zscore(s):
    sd = s.std(ddof=1)
    return (s - s.mean()) / sd if sd and not np.isnan(sd) else s * 0.0


def cohens_d(a, b):
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return float("nan")
    pooled = np.sqrt(((na - 1) * a.var(ddof=1) + (nb - 1) * b.var(ddof=1)) / (na + nb - 2))
    return float((a.mean() - b.mean()) / pooled) if pooled > 0 else float("nan")


def guardrails(df, cfg, keys):
    g = cfg["guardrails"]
    sizes = df["school_type"].value_counts().to_dict()
    out = {"group_sizes": {str(k): int(v) for k, v in sizes.items()}}
    out["min_group_size_ok"] = all(v >= g["min_group_size"] for v in sizes.values()) and len(sizes) == 2
    out["alpha"] = {}
    for scale, items in keys.items():
        a = cronbach_alpha(df[[f"q{i}" for i in items]])
        out["alpha"][scale] = {"value": None if np.isnan(a) else round(a, 3),
                               "ok": bool(a >= g["min_alpha"]) if not np.isnan(a) else False}
    return out


def rq1(df, scales, cfg):
    gos, priv = cfg["groups"]["state"], cfg["groups"]["private"]
    res = {}
    for scale in scales:
        a = df.loc[df["school_type"] == gos, scale]
        b = df.loc[df["school_type"] == priv, scale]
        t = stats.ttest_ind(a, b, equal_var=False)
        u = stats.mannwhitneyu(a, b, alternative="two-sided")
        res[scale] = {
            "mean_state": round(float(a.mean()), 2), "mean_private": round(float(b.mean()), 2),
            "welch_t_p": round(float(t.pvalue), 4), "mannwhitney_p": round(float(u.pvalue), 4),
            "cohens_d": round(cohens_d(a, b), 3),
        }
    return res


def rq2(df, factors, scales):
    res = {}
    for factor in factors:
        for scale in scales:
            rho, p = stats.spearmanr(df[factor], df[scale])
            res[f"{factor} ~ {scale}"] = {"rho": round(float(rho), 3), "p": round(float(p), 4)}
    return res


def rq3(df, hyps, cfg):
    gos, priv = cfg["groups"]["state"], cfg["groups"]["private"]
    res = {}
    for name, (factor, scale) in hyps.items():
        entry = {}
        for label, code in (("state", gos), ("private", priv)):
            sub = df[df["school_type"] == code]
            rho, p = stats.spearmanr(sub[factor], sub[scale])
            entry[label] = {"rho": round(float(rho), 3), "p": round(float(p), 4)}
        res[name] = entry
    return res


def validate_items(df, cfg):
    """Reject incomplete or invalid questionnaires instead of scoring them silently wrong."""
    q = cfg["questionnaire"]
    cols = [f"q{i}" for items in cfg["scale_keys"].values() for i in items]
    answers = df[cols]
    n_missing = int(answers.isna().sum().sum())
    n_invalid = int(((answers < q["item_min"]) | (answers > q["item_max"])).sum().sum())
    if "id" in df.columns and df["id"].duplicated().any():
        raise ValueError(f"{int(df['id'].duplicated().sum())} duplicated respondent ids")
    if n_missing:
        raise ValueError(f"{n_missing} empty item answers: exclude incomplete questionnaires first")
    if n_invalid:
        raise ValueError(f"{n_invalid} item answers outside {q['item_min']}-{q['item_max']}")


def analyze(df, cfg):
    """Score the scales, check guardrails and run RQ1-RQ3. Returns a result dict."""
    validate_items(df, cfg)
    keys = cfg["scale_keys"]
    scales = list(keys)
    df = score_scales(df, keys)
    df["burnout_index"] = zscore(df["EE"]) + zscore(df["DP"]) - zscore(df["RPA"])
    outcomes = scales + ["burnout_index"]
    return {
        "n": int(len(df)),
        "guardrails": guardrails(df, cfg, keys),
        "RQ1": rq1(df, outcomes, cfg),
        "RQ2": rq2(df, cfg["work_factors"], outcomes),
        "RQ3": rq3(df, cfg["rq3_hypotheses"], cfg),
    }


def report(result, cfg):
    """Write the human-readable log of an analysis result."""
    g = result["guardrails"]
    LOG.info("-- Guardrails --")
    LOG.info("group sizes: %s (required >= %d each): %s",
             g["group_sizes"], cfg["guardrails"]["min_group_size"],
             "PASS" if g["min_group_size_ok"] else "FAIL (expected for the sample)")
    for scale, a in g["alpha"].items():
        LOG.info("alpha %s: %s (>= %.1f): %s", scale, a["value"], cfg["guardrails"]["min_alpha"],
                 "PASS" if a["ok"] else "FAIL")
    LOG.info("-- RQ1: state vs private --")
    for scale, r in result["RQ1"].items():
        LOG.info("%s: %s", scale, r)
    LOG.info("-- RQ2: Spearman, work factors vs burnout indicators (EE is primary) --")
    for k, r in result["RQ2"].items():
        LOG.info("%s: %s", k, r)
    LOG.info("-- RQ3 (exploratory): correlation within each group --")
    for k, r in result["RQ3"].items():
        LOG.info("%s: %s", k, r)


def generate_respondents(n, cfg, seed):
    """Fictional questionnaire with the same columns as the real export.

    A latent burnout level (normal distribution, shifted up for state-school
    teachers) drives the item answers; reporting hours have a heavy right tail
    (Pareto) instead of a uniform spread. Parameters live in config.yaml -> synthetic.
    """
    syn = cfg["synthetic"]
    state_code, private_code = cfg["groups"]["state"], cfg["groups"]["private"]
    rng = np.random.default_rng(seed)

    n_private = n // 2
    school = np.array([state_code] * (n - n_private) + [private_code] * n_private)
    is_state = school == state_code
    latent = rng.normal(0.0, 1.0, n) + np.where(is_state, syn["state_shift"], 0.0)

    df = pd.DataFrame({"id": [f"S{i + 1:05d}" for i in range(n)], "school_type": school})

    hw = syn["hours_week"]
    df["hours_week"] = np.clip(rng.normal(hw["mean"], hw["sd"], n), hw["min"], hw["max"]).round().astype(int)
    cs = syn["class_size"]
    df["class_size"] = np.clip(rng.normal(np.where(is_state, cs["state_mean"], cs["private_mean"]), cs["sd"], n),
                               cs["min"], cs["max"]).round().astype(int)
    rh = syn["report_hours"]
    df["report_hours"] = np.clip((rng.pareto(rh["pareto_shape"], n) + 1) * rh["scale"],
                                 rh["min"], rh["max"]).round().astype(int)
    rt = syn["rating"]
    for col in ("support", "parent_pressure", "stability"):
        df[col] = np.clip(np.round(rng.normal(rt["mean"], rt["sd"], n) * 2) / 2, rt["min"], rt["max"])

    ty = syn["tenure_years"]
    df["tenure_years"] = np.clip(rng.gamma(ty["gamma_shape"], ty["gamma_scale"], n), 0, ty["max"]).round().astype(int)
    df["class_teacher"] = rng.integers(0, 2, n)
    df["level"] = rng.integers(1, 4, n)

    lo, hi = cfg["questionnaire"]["item_min"], cfg["questionnaire"]["item_max"]
    mid = (lo + hi) / 2
    items = {}
    for scale, numbers in cfg["scale_keys"].items():
        sign = -1.0 if scale == "RPA" else 1.0
        for i in numbers:
            raw = mid + sign * syn["loading"] * latent + rng.normal(0.0, syn["item_noise_sd"], n)
            items[i] = np.clip(np.rint(raw), lo, hi).astype(int)
    for i in sorted(items):
        df[f"q{i}"] = items[i]
    return df


def make_edge_case(name, cfg, seed):
    """Broken or unusual dataset built from a normal one (the cases are listed in config.yaml)."""
    syn = cfg["synthetic"]
    rng = np.random.default_rng(seed)
    df = generate_respondents(cfg["benchmark"]["workload_sizes"][0], cfg, seed)
    cols = [f"q{i}" for items in cfg["scale_keys"].values() for i in items]
    if name == "missing_values":
        df[cols] = df[cols].mask(rng.random((len(df), len(cols))) < syn["edge_missing_share"])
    elif name == "out_of_range":
        mask = rng.random((len(df), len(cols))) < syn["edge_out_of_range_share"]
        df[cols] = df[cols].mask(mask, syn["edge_out_of_range_value"])
    elif name == "single_group":
        df = df[df["school_type"] == cfg["groups"]["state"]].copy()
    elif name == "tiny_groups":
        df = generate_respondents(syn["edge_tiny_size"], cfg, seed)
    elif name == "duplicates":
        df = pd.concat([df, df.head(syn["edge_duplicate_rows"])], ignore_index=True)
    elif name == "straight_lining":
        df[cols] = syn["edge_straight_value"]
    else:
        raise ValueError(f"unknown edge case: {name}")
    return df


def _cpu_model():
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
                return winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
        except OSError:
            pass
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.lower().startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or None


def _ram_bytes():
    if sys.platform == "win32":
        try:
            import ctypes

            class MemoryStatus(ctypes.Structure):
                _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong),
                            ("total_phys", ctypes.c_ulonglong), ("avail_phys", ctypes.c_ulonglong),
                            ("total_page", ctypes.c_ulonglong), ("avail_page", ctypes.c_ulonglong),
                            ("total_virtual", ctypes.c_ulonglong), ("avail_virtual", ctypes.c_ulonglong),
                            ("avail_ext", ctypes.c_ulonglong)]

            status = MemoryStatus()
            status.length = ctypes.sizeof(MemoryStatus)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.total_phys)
        except (AttributeError, OSError):
            pass
        return None
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal"):
                return int(line.split()[1]) * 1024
    except OSError:
        pass
    return None


def _git_state():
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                                text=True, timeout=5, check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain"], capture_output=True,
                                    text=True, timeout=5, check=True).stdout.strip())
        return commit, dirty
    except (OSError, subprocess.SubprocessError):
        return os.environ.get("GIT_COMMIT"), None


def collect_metadata(config_path, cfg, run_id):
    commit, dirty = _git_state()
    try:
        affinity = len(os.sched_getaffinity(0))
    except AttributeError:
        affinity = None
    return {
        "type": "meta",
        "run_id": run_id,
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "numpy": np.__version__, "pandas": pd.__version__,
        "scipy": __import__("scipy").__version__, "pyyaml": yaml.__version__,
        "os": platform.platform(),
        "machine": platform.machine(),
        "cpu_model": _cpu_model(),
        "cpu_count": os.cpu_count(),
        "cpus_available": affinity,
        "ram_total_bytes": _ram_bytes(),
        "in_docker": Path("/.dockerenv").exists(),
        "git_commit": commit, "git_dirty": dirty,
        "config_sha256": hashlib.sha256(Path(config_path).read_bytes()).hexdigest()[:12],
        "seed": cfg["seed"],
        "benchmark": cfg["benchmark"],
        "synthetic": cfg["synthetic"],
    }


def _pct(values, q):
    return round(float(np.percentile(values, q)), 1) if len(values) else None


def summarize(runs):
    """Latency statistics over the given measured runs (durations in microseconds).

    Failed runs are never dropped silently: they count in error_rate, and the
    `*_all_us` figures include them. The other figures use successful runs only.
    """
    ok = np.array([r["duration_us"] for r in runs if r["status"] == "ok"], dtype=float)
    every = np.array([r["duration_us"] for r in runs], dtype=float)
    return {
        "n_measured": len(runs),
        "n_ok": int(len(ok)),
        "error_rate": round(1 - len(ok) / len(runs), 4) if runs else None,
        "median_us": _pct(ok, 50), "p95_us": _pct(ok, 95), "p99_us": _pct(ok, 99),
        "mean_us": round(float(ok.mean()), 1) if len(ok) else None,
        "max_us": round(float(ok.max()), 1) if len(ok) else None,
        "median_all_us": _pct(every, 50), "p95_all_us": _pct(every, 95),
    }


def run_benchmark(cfg, config_path):
    """Warm-up + timed runs of analyze() on synthetic data; returns all JSONL records."""
    b = cfg["benchmark"]
    warmup, measured, sizes = b["warmup_runs"], b["measured_runs"], b["workload_sizes"]
    run_id = uuid.uuid4().hex[:8]
    records = [collect_metadata(config_path, cfg, run_id)]

    datasets = {n: generate_respondents(n, cfg, cfg["seed"] + n) for n in sizes}

    gc_was_enabled = gc.isenabled()

    def timed_run(seq, phase, df, **extra):
        """One run: everything except the lines between the two stopwatch marks is outside the timing."""
        gc.collect()
        if b["disable_gc"]:
            gc.disable()
        status, error = "ok", None
        ts_start_us = time.time_ns() // 1000
        t0 = time.perf_counter_ns()
        try:
            analyze(df, cfg)
        except Exception as exc:
            status, error = "error", repr(exc)
        t1 = time.perf_counter_ns()
        if gc_was_enabled:
            gc.enable()
        records.append({
            "type": "run", "run_id": run_id, "seq": seq, "phase": phase,
            "workload_n": len(df), "ts_start_us": ts_start_us,
            "duration_us": (t1 - t0) // 1000, "status": status, "error": error, **extra,
        })

    seq = 0
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for i in range(warmup + measured):
            n = sizes[i % len(sizes)]
            timed_run(seq, "warmup" if i < warmup else "measure", datasets[n].copy())
            seq += 1
        for name in b["edge_cases"]:
            edge_df = make_edge_case(name, cfg, cfg["seed"])
            for _ in range(b["edge_repeats"]):
                timed_run(seq, "edge", edge_df.copy(), edge_case=name)
                seq += 1

    measure_runs = [r for r in records if r["type"] == "run" and r["phase"] == "measure"]
    summary = {"type": "summary", "run_id": run_id, "overall": summarize(measure_runs), "by_workload_n": {}}
    for n in sizes:
        summary["by_workload_n"][str(n)] = summarize([r for r in measure_runs if r["workload_n"] == n])
    summary["edge_cases"] = {}
    for name in b["edge_cases"]:
        runs = [r for r in records if r["type"] == "run" and r.get("edge_case") == name]
        errors = [r["error"] for r in runs if r["status"] == "error"]
        summary["edge_cases"][name] = {"runs": len(runs), "errors": len(errors),
                                       "outcome": "rejected" if errors else "processed",
                                       "first_error": errors[0] if errors else None}
    records.append(summary)
    return records


def write_jsonl(records, path):
    """All file output happens here, after the series is finished."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def print_summary(records, path):
    summary = records[-1]
    runs = [r for r in records if r["type"] == "run"]
    print(f"runs: {sum(r['phase'] == 'warmup' for r in runs)} warm-up (discarded) + "
          f"{sum(r['phase'] == 'measure' for r in runs)} measured -> {path}")
    print(f"{'workload n':>10} {'median ms':>10} {'p95 ms':>8} {'p99 ms':>8} {'errors':>7}")
    rows = list(summary["by_workload_n"].items()) + [("all", summary["overall"])]
    for label, s in rows:
        f = lambda v: "n/a" if v is None else f"{v / 1000:.2f}"
        print(f"{label:>10} {f(s['median_us']):>10} {f(s['p95_us']):>8} {f(s['p99_us']):>8} "
              f"{s['error_rate']:>7.1%}")
    if summary.get("edge_cases"):
        print("edge cases (separate from the statistics above):")
        for name, e in summary["edge_cases"].items():
            detail = f" ({e['first_error'][:60]})" if e["first_error"] else ""
            print(f"  {name:<16} {e['outcome']:<10}{detail}")


def main_analysis(cfg, config_path):
    random.seed(cfg["seed"])
    np.random.seed(cfg["seed"])

    out_dir = Path(cfg["paths"]["output_dir"])
    setup_logging(out_dir / "run_log.txt")
    LOG.info("== Teacher burnout analysis pipeline ==")
    LOG.info("config: %s | seed: %s", config_path, cfg["seed"])

    data_path = Path(cfg["paths"]["data"])
    df = pd.read_csv(data_path)
    LOG.info("data: %s | rows: %d", data_path, len(df))

    result = analyze(df, cfg)
    report(result, cfg)

    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    LOG.info("done. results written to %s and %s", out_dir / "run_log.txt", summary_path)


def main_benchmark(cfg, config_path):
    random.seed(cfg["seed"])
    np.random.seed(cfg["seed"])
    out_path = Path(cfg["benchmark"]["output"])
    records = run_benchmark(cfg, config_path)
    write_jsonl(records, out_path)
    print_summary(records, out_path)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--bench", action="store_true",
                        help="measure the analysis (warm-up + timed runs) and write a JSONL log")
    args = parser.parse_args()

    cfg = load_config(args.config)
    if args.bench:
        main_benchmark(cfg, args.config)
    else:
        main_analysis(cfg, args.config)


if __name__ == "__main__":
    main()
