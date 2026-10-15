# Professional Burnout of Teachers in Private and State Schools

![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)
![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)
![Status](https://img.shields.io/badge/status-pipeline%20skeleton-orange.svg)

**Authors:** Zhanat, Yergali
**Repository:** https://github.com/Zhanb089/teacher-burnout-study

## Overview

This repository contains the analysis pipeline for a quantitative cross-sectional study that compares
burnout among teachers of state and private schools and examines which working conditions are related to it.
Burnout is measured with the Maslach Burnout Inventory in the Russian adaptation by Vodopyanova and
Starchenkova (three scales: emotional exhaustion, depersonalization, reduced professional accomplishment).

**Research question.** Do teachers in state and private schools differ in burnout, and which working
conditions explain the difference?

| | H0 | H1 |
|---|---|---|
| RQ1 | Burnout does not differ between school types | State-school teachers have higher burnout |
| RQ2 | Working conditions are unrelated to burnout | Higher demands and lower resources go with higher burnout |
| RQ3 (exploratory) | The strength of each relation does not depend on school type | Class size and reporting matter more in state schools; parental pressure and job insecurity matter more in private schools |

The full methodology (variables, metrics, baseline, validity threats) is in
[`docs/methodology_card.md`](docs/methodology_card.md) (in Russian).

Primary metric: emotional exhaustion score (EE, 0-54). Guardrails: Cronbach's alpha >= 0.7 for every
scale and at least 15 complete questionnaires per group.

## Repository structure

```
teacher-burnout-study/
├── README.md
├── LICENSE
├── Dockerfile               # pinned base image, runs the pipeline
├── requirements.txt         # exact dependency versions
├── config.yaml              # all experiment parameters
├── data/
│   ├── sample/              # 8 fictional rows to test the pipeline
│   └── raw/
│       └── test_run.jsonl   # first measurement log: 10 warm-up + 120 timed runs (fictional data)
├── src/
│   └── benchmark.py         # scoring, guardrails, RQ1-RQ3 analysis + measurement harness (--bench)
├── notebooks/               # exploratory notebooks (empty for now)
├── docs/
│   └── methodology_card.md  # methodology passport card
└── results/                 # run_log.txt and summary.json (generated, not committed)
```

## System requirements

- Any OS with Docker 24+ (Linux, macOS, Windows with WSL2); no GPU needed.
- Without Docker: Python 3.11 and `pip install -r requirements.txt`.
- A few MB of disk space; a run on the sample takes about a second.

## Quickstart

Get the code once (`git clone https://github.com/Zhanb089/teacher-burnout-study.git`, then open the
folder). After that, two commands (they work the same in Linux, macOS, Windows PowerShell and cmd):

```bash
docker build -t burnout-analysis .
docker run --rm burnout-analysis
```

The container prints the full log to the screen. To also save `run_log.txt` and `summary.json` on your
computer, mount the results folder:

```bash
# Linux / macOS
docker run --rm -v "$(pwd)/results:/app/results" burnout-analysis
# Windows PowerShell
docker run --rm -v "${PWD}/results:/app/results" burnout-analysis
```

Without Docker (Python 3.11):

```bash
python -m venv .venv
# Linux / macOS: source .venv/bin/activate      Windows: .venv\Scripts\activate
pip install -r requirements.txt
python src/benchmark.py --config config.yaml
```

To analyse real data, set `paths.data` in `config.yaml` to your CSV (same columns as the sample).

## Measurement run (`--bench`)

Besides the analysis itself, the script can measure how long the analysis takes, as a clean experiment:

```bash
python src/benchmark.py --config config.yaml --bench
# Docker, saving the log to your computer (Linux / macOS; in PowerShell use ${PWD})
docker run --rm --cpus=2 --memory=2g -v "$(pwd)/data/raw:/app/data/raw" burnout-analysis \
    python src/benchmark.py --config config.yaml --bench
```

What happens:

1. Fictional respondents are generated first (`synthetic` section of `config.yaml`), for 35, 100 and 1000
   people, so the load is not only our planned survey size.
2. 10 warm-up runs are executed and logged with `"phase": "warmup"`. They are never used in the statistics.
3. 120 timed runs follow (`"phase": "measure"`). The stopwatch (`time.perf_counter_ns`) surrounds only
   `analyze()`. Generation, copying, printing and file writing are outside it, and the log is written
   only after the series is finished.
4. `data/raw/test_run.jsonl` gets one JSON line per run (microsecond timestamp, duration, status, error),
   a first line with the environment (Python and library versions, CPU, RAM, git commit, config hash, seed)
   and a last line with median, p95, p99 and the error rate. Failed runs are counted in the error rate,
   not dropped.

5. After the timed runs, six broken datasets are run 5 times each as phase `edge`: empty answers, answers
   outside 0-6, only one school type, tiny groups, duplicated respondents and "straight-lining" (the same
   answer everywhere). They are reported separately and never mixed into the main statistics. The analysis
   rejects the first three and the duplicates with a clear error (logged as `status: error`); tiny groups
   and straight-lining are processed and show up as a failed guardrail.

All parameters (number of runs, warm-up size, workload sizes, distributions, edge cases) are in `config.yaml`.
Inside Docker there is no git, so pass the commit yourself: `-e GIT_COMMIT=$(git rev-parse --short HEAD)`.
The committed `test_run.jsonl` contains only fictional data. Real survey exports in `data/raw/` stay
ignored by git.

## Planned analyses

| Question | Method | Reported metrics |
|---|---|---|
| RQ1 | Welch t-test; Mann-Whitney U if not normal | group means, p, Cohen's d |
| RQ2 | Spearman correlations (hierarchical regression is run in JASP) | rho, p; beta, R², delta R² |
| RQ3 | Spearman correlation within each school type | rho per group |
| Quality | Cronbach's alpha, group sizes | alpha per scale, n per group |

Expected output on the sample (the data are fictional, 4 rows per group, so the numbers only prove that
the pipeline runs; the group-size guardrail correctly reports FAIL):

| Scale | Mean (state) | Mean (private) | Cohen's d |
|---|---|---|---|
| EE | 38.75 | 19.00 | 2.676 |
| DP | 10.25 | 3.75 | 1.481 |
| RPA | 23.00 | 33.50 | -1.513 |

## Reproducibility checklist

- [x] Exact dependency versions (`requirements.txt`, pinned base image)
- [x] Fixed random seed in `config.yaml`
- [x] All analysis and load parameters in `config.yaml`
- [x] Measurement log with warm-up runs separated from timed runs (`data/raw/test_run.jsonl`)
- [x] Sample data to test the pipeline
- [x] One command to build and one to run
- [ ] Real survey data analysed (planned for Week 7)

## Data note

The sample data are fictional. The real survey is anonymous (no names, no school names); raw exports are
not committed (see `.gitignore`).

## Citation

```bibtex
@misc{teacher_burnout_schools_2026,
  title  = {Professional Burnout of Teachers in Private and State Schools},
  author = {Zhanat and Yergali},
  year   = {2026},
  url    = {https://github.com/Zhanb089/teacher-burnout-study}
}
```

## License

MIT, see [LICENSE](LICENSE).
