# Figure captions

**Figure 1. Latency and throughput of the analysis script versus workload size.**
(a) Latency percentiles p50, p95 and p99. Lines show the statistic, coloured bands show its 95%
percentile-bootstrap confidence interval (10,000 resamples of the 40 measured runs per size),
and the grey hatched band shows the p25-p75 range of the runs. (b) Median throughput (respondents
processed per second) with its 95% bootstrap CI; both axes are logarithmic. Warm-up runs excluded.
With 40 runs per size, p99 is determined by the slowest one or two runs, so its interval is wide.

**Figure 2. Distribution of latency per workload size.**
Violins show the density of the 120 measured runs; the inner box marks p25, p50 and p75.
Crosses mark runs outside 1.5 x IQR of their workload size. They are flagged, not removed.
Latency axis starts at 0 ms.
