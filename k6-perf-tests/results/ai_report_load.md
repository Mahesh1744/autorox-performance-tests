## [WARN] AI Analysis: LOAD -- 2026-06-16 11:27 UTC

**Release Score: 63/100 (Grade C) -- BORDERLINE -- review before release**

| Component | Score | Max | Detail |
|-----------|------:|----:|--------|
| P95 Latency | 15 | 40 | 6170 ms vs static threshold 7000 ms |
| Error Rate | 30 | 30 | 0.03% |
| Checks | 10 | 15 | 100.0% passed |
| Throughput | 8 | 15 | Insufficient history -- neutral score |

### Key Metrics

- **P95**: 6170 ms
- **P99**: 9160 ms
- **Avg**: 2620 ms
- **Error rate**: 0.03%
- **Throughput**: 52.6 rps
- **Total reqs**: 32791
- **Peak VUs**: 200

### Anomalies

_None detected vs historical runs._

### Root Cause Analysis

**1. No significant issues detected**
> Evidence: All metrics within expected ranges based on history
> Action: No action required

### Bottleneck Prediction

Predicted inflection point: **~500 VUs**  
_Latency growth rate accelerates around 500 VUs -- monitor closely above this point_  
_(based on 5 data points across all test types)_

| VUs | P95 (ms) | Bar |
|----:|---------:|-----|
| 150 | 4620 | ######### |
| 200 | 5830 | ########### |
| 300 | 5810 | ########### |
| 500 | 6550 | ############# |
| 600 | 10760 | ##################### |
