# Domain model (Software Engineering track): C4 diagrams

This document describes the measured system as a C4 model (levels 1-3) and marks the **metric collection
points** (M1-M5). It is written in [Mermaid](https://mermaid.js.org/), which GitHub renders directly.

## 1. System in one sentence

A researcher runs a Python analysis pipeline over a questionnaire (MBI, Maslach Burnout Inventory) answered
by teachers of state and private schools. To be sure the pipeline is fast and does not fail, a benchmark
harness runs it repeatedly for 35, 100 and 1000 respondents, records the time of every run, and turns the
log into statistics and figures.

## 2. Level 1: System context

```mermaid
C4Context
    title System context: teacher-burnout-study

    Person(researcher, "Researcher", "Runs the benchmark and reads the report")
    System(study, "teacher-burnout-study", "Scores MBI questionnaires, compares state and private schools, measures its own performance")
    System_Ext(github, "GitHub", "Stores code, figures and the report; the release is tagged here")
    System_Ext(jasp, "JASP", "Hierarchical regression for RQ2 (outside the pipeline)")

    Rel(researcher, study, "Runs: python src/benchmark.py --bench")
    Rel(study, github, "Is published to")
    Rel(researcher, jasp, "Runs regression in")
```

## 3. Level 2: Containers (where metrics are collected)

Containers are separately runnable or storable parts. Highlighted nodes `M1`-`M5` are the **metric collection
points** described in section 5.

```mermaid
flowchart TB
    R([Researcher])

    subgraph DOCKER["Python 3.11 environment, pinned versions (the Docker image runs the benchmark)"]
        direction LR
        CFG[("config.yaml<br/>seed 42, workloads, scales")]
        BENCH["<b>Benchmark harness</b><br/>src/benchmark.py --bench<br/>runs analyze() n times"]
        PROC["<b>Data processor</b><br/>src/process_data.py<br/>clean, statistics, bootstrap CI"]
        VIZ["<b>Figure generator</b><br/>src/visualize.py"]
        NB["<b>Notebook</b><br/>notebooks/01_data_analysis.ipynb"]
    end

    RAW[("data/raw/test_run.jsonl<br/>raw log: meta, runs, summary")]
    PROCD[("data/processed/<br/>runs_clean.csv<br/>metrics_summary.csv<br/>edge_cases.csv")]
    FIGS[("reports/figures/<br/>fig1, fig2 (.pdf, .png 300 DPI)")]

    R -->|runs| BENCH
    CFG --> BENCH
    BENCH -->|"M1 M2 M3: one JSON line per run"| RAW
    RAW --> PROC
    PROC -->|"M4: error rate, outlier flags<br/>M5: p50 p95 p99 + 95% CI"| PROCD
    PROCD --> VIZ
    VIZ --> FIGS
    RAW --> NB
    NB --> PROC
    NB --> VIZ
    FIGS -->|"figures use the same numbers<br/>as metrics_summary.csv"| R

    classDef metric fill:#fff3cd,stroke:#b8860b,stroke-width:2px;
    class BENCH,PROC,VIZ metric;
```

## 4. Level 3: Components of the benchmark harness

The harness `src/benchmark.py` is where raw measurements are created. The timer wraps **only** the analysis
call: data generation, the copy of the input table and writing the log are outside the two stopwatch marks,
and garbage collection is switched off during the call so that a random collection pause does not appear as a slow run.

```mermaid
flowchart TB
    subgraph H["Container: src/benchmark.py (--bench)"]
        direction TB
        CM["collect_metadata()<br/>run_id, hardware, library versions, git state"]
        GEN["generate_respondents(n, cfg, seed)<br/>synthetic MBI answers (fictional)"]
        RUN["run_benchmark(cfg)<br/>10 warm-up + 120 measured runs (round-robin over n = 35, 100, 1000)<br/>+ 30 edge-case runs"]
        TIMER["<b>M1 Timer: timed_run()</b><br/>gc.collect(), garbage collector off<br/>t0 = perf_counter_ns()<br/>analyze(df, cfg)<br/>t1 = perf_counter_ns()"]
        STAT["<b>M2 Status capture</b><br/>status ok / error + error text"]
        ANA["analyze(df, cfg)<br/>scoring, guardrails, RQ1-RQ3<br/>(the system under test)"]
        SUM["summarize(runs)<br/>quick summary (last line of the log)"]
        WR["write_jsonl(records, path)"]
    end

    CM --> RUN
    GEN --> RUN
    RUN --> TIMER
    TIMER --> ANA
    ANA --> TIMER
    TIMER --> STAT
    STAT --> RUN
    RUN --> SUM
    RUN --> WR
    SUM --> WR

    classDef metric fill:#fff3cd,stroke:#b8860b,stroke-width:2px;
    class TIMER,STAT metric;
```

### Components of the data processor

```mermaid
flowchart TB
    subgraph P["Container: src/process_data.py"]
        direction TB
        L["load_jsonl() + validate_runs()"]
        C["clean()<br/>drop warm-up, split edge cases"]
        O["flag_outliers_iqr()<br/>Tukey fences, flag only"]
        G["<b>M4 guardrail_error_rate()</b><br/>errors over ALL measured runs"]
        M["compute_metrics()<br/>median, p95, p99, mean, SD<br/>bootstrap 95% CI, B = 10 000, seed 42"]
        E["export()<br/>runs_clean.csv, metrics_summary.csv, edge_cases.csv"]
    end
    L --> C --> O --> G --> M --> E
    classDef metric fill:#fff3cd,stroke:#b8860b,stroke-width:2px;
    class G,M metric;
```

## 5. Metric collection points

| Id | Where (component) | What is measured | Unit | How | Stored in |
|---|---|---|---|---|---|
| **M1** | `timed_run()` inside `run_benchmark()`, timer around `analyze()` | Duration of one run, `duration_us` | µs (converted to ms) | `time.perf_counter_ns()` before and after (monotonic clock) | raw log, field `duration_us` |
| **M1b** | `timed_run()` | Start time of the run | µs since epoch | `time.time_ns()` | raw log, field `ts_start_us` |
| **M2** | `timed_run()`, `try/except` | Outcome of the run | ok / error | exception caught, text stored, run is **not** dropped | raw log, fields `status`, `error` |
| **M3** | `run_benchmark()` schedule | Phase and workload | warmup / measure / edge; n | counters per run | raw log, fields `phase`, `workload_n`, `seq` |
| **M4** | `guardrail_error_rate()` | Error rate (guardrail metric) | share, 0-1 | errors / all measured runs, overall and per workload | `metrics_summary.csv`, column `error_rate` |
| **M5** | `compute_metrics()` | Latency p50, p95, p99, mean, SD; throughput; 95 % CI | ms; respondents/s | percentile bootstrap, 10 000 resamples, seed 42 | `metrics_summary.csv` |

Derived quantities (formulas in the paper section 3): throughput θ = n / (duration in s), speed-up
S(n) = θ̃ₙ / θ̃ₙ₀ and efficiency E(n) = S(n) / (n / n₀) with baseline n₀ = 35.

## 6. Domain entities

```mermaid
classDiagram
    class Experiment {
        +run_id
        +seed = 42
        +config_sha256
        +git_commit
    }
    class Run {
        +seq
        +phase : warmup | measure | edge
        +workload_n : 35 | 100 | 1000
        +duration_us
        +status : ok | error
    }
    class Workload {
        +n : respondents
    }
    class Metric {
        +name : p50 | p95 | p99 | mean | SD
        +value
        +ci_lo
        +ci_hi
        +unit
    }
    class Guardrail {
        +error_rate
    }
    class Figure {
        +file : pdf + png 300 DPI
    }
    Experiment "1" --> "*" Run : produces
    Workload "1" --> "*" Run : size of input
    Run "*" --> "1" Metric : aggregated into per workload
    Run "*" --> "1" Guardrail : counted by
    Metric "*" --> "*" Figure : plotted in
```

## 7. Design decisions that protect the measurement

| Decision | Reason |
|---|---|
| Monotonic clock `perf_counter_ns` | Wall-clock time can jump (NTP) and would corrupt a duration |
| Garbage collector off while timing (`gc.collect()` before each run) | A collection pause in the middle of a run would look like a slow run and inflate the tail |
| Warm-up runs are recorded but excluded | Cold start (imports, caches) is not steady-state behaviour |
| Errors are kept and counted | Dropping failed runs would bias latency (selection bias) |
| Outliers are flagged, not deleted | They are real slow runs; median and percentiles are robust to them |
| Fixed seed 42, pinned Docker image and libraries | Same input gives the same numbers on another computer |
| Raw log is committed, processed files are derived | Every number can be recomputed from `data/raw/test_run.jsonl` |

## 8. Limitations of the model

The model describes one machine and one container image. Respondents are synthetic, so the data show how the
pipeline behaves, not real burnout results. Runs are sequential, so concurrent load is not modelled.
