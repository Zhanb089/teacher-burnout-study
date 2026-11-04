# 4. Experimental Results & Discussion

This section reports how the survey-analysis pipeline of the teacher-burnout study behaves when the number of processed respondents grows. All quantities are defined in Table \ref{tab:notation} and Eqs. \ref{eq:latency}--\ref{eq:speedup} of Section 3. The pipeline was run with seed 42 inside the pinned Docker image (`python:3.11.9-slim-bookworm`); every number below can be regenerated with `python src/benchmark.py --bench`, `python src/process_data.py` and `python src/visualize_combined.py`.

## 4.1 Setup

Three workloads were measured, $n \in \{35, 100, 1000\}$ respondents, with $R_n = 40$ measured runs each ($R_{\mathrm{all}} = 120$) after 10 discarded warm-up runs. For every run the latency $\ell_{n,r}$ (Eq. \ref{eq:latency}) and the throughput $\theta_{n,r}$ (Eq. \ref{eq:throughput}) were recorded. Percentiles use linear interpolation (Eq. \ref{eq:percentile}) and their uncertainty is a percentile-bootstrap interval with $B = 10\,000$ resamples (Eq. \ref{eq:bootstrap}). Runs outside the IQR fences (Eq. \ref{eq:iqr}) were flagged but kept, because they are real behaviour of the system and not recording errors. The baseline for scaling is $n_0 = 35$, the size of the pilot sample.

## 4.2 Results

Table \ref{tab:results} summarises the measurements and Fig. \ref{fig:combined} shows them. No run failed, so the error rate of Eq. \ref{eq:error} is $\varepsilon = 0/120 = 0\,\%$. Nine of the 120 latencies (3, 4 and 2 for $n = 35, 100, 1000$) were flagged as outliers.

\begin{table}[t]
\centering
\caption{Latency and throughput of the analysis script (\texttt{analyze()}) by workload size $n$.
Each workload row summarises $R_n=40$ successful measured runs; the pooled row summarises all 120.
Ten warm-up runs are excluded; the error rate was 0\,\% in all runs.
Latency is reported as median (p25--p75); p95 and p99 are given with their 95\,\% percentile-bootstrap
confidence interval ($B=10\,000$ resamples, seed 42). Throughput is the median (p25--p75) number of
respondents processed per second, and $S(n)$ is the median throughput relative to the baseline
$n_0=35$ (Eq.~\ref{eq:speedup}). \textbf{Bold}: lowest (best) point estimate in a latency column;
\textit{italic}: second lowest. The workloads are conditions, not competing methods. The 95\,\% intervals of the
median latency overlap for $n=35$ and $n=100$, so their order is not meaningful; $n=1000$ is about
3\,ms slower and its interval does not overlap theirs.}
\label{tab:results}
\small
\begin{tabular}{@{}lcccrc@{}}
\toprule
 & \multicolumn{3}{c}{Latency (ms)} & \multicolumn{1}{c}{Throughput} & \\
\cmidrule(lr){2-4}\cmidrule(lr){5-5}
$n$ & median (p25--p75) & p95 [95\,\% CI] & p99 [95\,\% CI] & resp./s, median (p25--p75) & $S(n)$ \\
\midrule
35 (baseline) & \textit{43.9} (42.2--46.2) & \textit{53.8} [47.1, 69.3] & \textit{64.1} [51.1, 69.3] & 797 (758--830) & 1.00 \\
100 & \textbf{43.8} (41.9--45.9) & \textbf{53.3} [48.0, 62.6] & \textbf{59.0} [51.1, 62.6] & 2\,283 (2\,177--2\,384) & 2.86 \\
1000 & 46.8 (45.6--50.4) & 55.3 [51.5, 89.7] & 82.1 [53.0, 89.7] & 21\,371 (19\,850--21\,923) & 26.8 \\
\midrule
All (pooled) & 45.1 (43.2--47.4) & 53.8 [51.9, 69.3] & 70.0 [54.4, 89.7] & -- & -- \\
\bottomrule
\end{tabular}
\end{table}

\begin{figure*}[t]
  \centering
  \includegraphics[width=\textwidth]{figures/fig_combined_latency_throughput.pdf}
  \caption{Latency and throughput of the survey-processing pipeline for workloads of
  $n=35$, $100$ and $1000$ respondents (40 runs per size, $N=120$). \textbf{(a)}~Latency
  percentiles p50, p95 and p99; coloured bands are 95\% percentile-bootstrap confidence
  intervals ($B=10{,}000$, seed 42), the grey hatched band is the interquartile range
  (p25--p75) of the per-run latencies. \textbf{(b)}~Median throughput on log--log axes; the
  band is the 95\% bootstrap CI. \textbf{(c)}~Distribution of per-run latency; the inner box
  shows p25, p50 and p75, crosses mark IQR-rule outliers (9 of 120), which were kept in
  all statistics. Median latency rises only from 43.9\,ms to 46.8\,ms while throughput grows
  from 797 to 21\,371 respondents/s ($\times 26.8$ for a $\times 28.6$ larger workload).}
  \label{fig:combined}
\end{figure*}

**Latency.** The median latency is 43.9 ms for $n = 35$, 43.8 ms for $n = 100$ and 46.8 ms for $n = 1000$ (Table \ref{tab:results}, Fig. \ref{fig:combined}a). The intervals of the first two medians overlap almost completely, so the data do not show any difference between 35 and 100 respondents. The median at $n = 1000$ is about 3 ms higher and its 95 % interval, [46.2, 47.9] ms, does not overlap [43.0, 44.6] ms (for $n = 35$) or [43.0, 45.1] ms (for $n = 100$). A 28-fold larger workload therefore costs roughly 7 % more time per run.

**Throughput and scaling.** Throughput grows almost in proportion to the workload (Fig. \ref{fig:combined}b): the speed-up of Eq. \ref{eq:speedup} is $S(100) = 2.86$ and $S(1000) = 26.8$, which corresponds to an efficiency $E(100) = 1.00$ and $E(1000) = 0.94$ against the ideal value of 1. In plain terms, the cost of a run is dominated by a fixed overhead, so processing more respondents per run is almost free until the per-respondent work starts to matter at $n = 1000$.

**Tail latency.** The upper percentiles are less stable (Fig. \ref{fig:combined}a, c). The p95 stays between 53.3 and 55.3 ms, but the p99 moves from 64.1 ms ($n = 35$) to 59.0 ms ($n = 100$) and 82.1 ms ($n = 1000$). With $R_n = 40$ runs, the 99th percentile lies between the two largest observations, so its bootstrap interval is wide and its upper end equals the single slowest run (e.g. 89.7 ms for $n = 1000$). The rise of the p99 at $n = 1000$ is therefore a hint, not an established effect.

## 4.3 Discussion

**Meaning for the study.** The questionnaire data of the study (a few dozen teachers per school type) are at the size of the smallest workload, where one analysis run takes about 44 ms. Re-running the full pipeline after every data update is therefore practically free, and the analysis would still take less than 0.1 s for a thousand respondents. Performance is not a constraint for the planned comparison of state and private schools.

**Limitations.** (i) All runs were made on one machine and one container image, so absolute times describe this environment and only the relative picture (flat latency, near-linear throughput) is expected to transfer. (ii) Three workload sizes are enough to see a trend but not to fit a scaling law. (iii) The 40 runs per size give precise medians but imprecise tail percentiles. (iv) The workloads are synthetic respondents with the structure of the MBI questionnaire, not real answers. (v) Runs were executed one after another, so effects of concurrent use were not measured.

**Threats to validity.** Warm-up runs were discarded to avoid start-up effects; outliers were kept so that the reported tail is not artificially short; seeds and library versions are fixed, which makes the numbers reproducible but not independent of the hardware.

## 4.4 Summary

The pipeline processed all 120 measured runs without errors. Median latency stayed within 44--47 ms for workloads from 35 to 1000 respondents (Table \ref{tab:results}), and throughput increased by a factor of 26.8 for a 28.6-fold larger workload ($E = 0.94$, Fig. \ref{fig:combined}). The tail percentile p99 is the least certain quantity and should be re-measured with more runs if tail behaviour becomes important.
