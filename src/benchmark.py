"""Analysis pipeline skeleton for the teacher burnout study.

Reads a questionnaire CSV, scores the three burnout scales, checks the
guardrail metrics and runs the planned comparisons (RQ1-RQ3).
Everything is controlled by config.yaml. The same script runs on the tiny
sample in data/sample/ and, later, on the real survey export.

Usage:
    python src/benchmark.py --config config.yaml
"""
import argparse
import json
import logging
import random
import sys
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    cfg = load_config(args.config)
    random.seed(cfg["seed"])
    np.random.seed(cfg["seed"])

    out_dir = Path(cfg["paths"]["output_dir"])
    setup_logging(out_dir / "run_log.txt")
    LOG.info("== Teacher burnout analysis pipeline ==")
    LOG.info("config: %s | seed: %s", args.config, cfg["seed"])

    data_path = Path(cfg["paths"]["data"])
    df = pd.read_csv(data_path)
    LOG.info("data: %s | rows: %d", data_path, len(df))

    keys = cfg["scale_keys"]
    scales = list(keys)
    df = score_scales(df, keys)
    df["burnout_index"] = zscore(df["EE"]) + zscore(df["DP"]) - zscore(df["RPA"])

    result = {"n": int(len(df)), "guardrails": guardrails(df, cfg, keys)}
    LOG.info("-- Guardrails --")
    LOG.info("group sizes: %s (required >= %d each): %s",
             result["guardrails"]["group_sizes"], cfg["guardrails"]["min_group_size"],
             "PASS" if result["guardrails"]["min_group_size_ok"] else "FAIL (expected for the sample)")
    for scale, a in result["guardrails"]["alpha"].items():
        LOG.info("alpha %s: %s (>= %.1f): %s", scale, a["value"], cfg["guardrails"]["min_alpha"],
                 "PASS" if a["ok"] else "FAIL")

    outcomes = scales + ["burnout_index"]
    result["RQ1"] = rq1(df, outcomes, cfg)
    LOG.info("-- RQ1: state vs private --")
    for scale, r in result["RQ1"].items():
        LOG.info("%s: %s", scale, r)

    result["RQ2"] = rq2(df, cfg["work_factors"], outcomes)
    LOG.info("-- RQ2: Spearman, work factors vs burnout indicators (EE is primary) --")
    for k, r in result["RQ2"].items():
        LOG.info("%s: %s", k, r)

    result["RQ3"] = rq3(df, cfg["rq3_hypotheses"], cfg)
    LOG.info("-- RQ3 (exploratory): correlation within each group --")
    for k, r in result["RQ3"].items():
        LOG.info("%s: %s", k, r)

    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    LOG.info("done. results written to %s and %s", out_dir / "run_log.txt", summary_path)


if __name__ == "__main__":
    main()
