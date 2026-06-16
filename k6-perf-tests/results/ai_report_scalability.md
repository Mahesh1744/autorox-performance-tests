## [WARN] AI Analysis: SCALABILITY -- 2026-06-12 10:46 UTC

**Release Score: 67/100 (Grade C) -- BORDERLINE -- review before release**

| Component | Score | Max | Detail |
|-----------|------:|----:|--------|
| P95 Latency | 40 | 40 | 6550 ms vs static threshold 10000 ms |
| Error Rate | 14 | 30 | 1.87% |
| Checks | 5 | 15 | 99.0% passed |
| Throughput | 8 | 15 | Insufficient history -- neutral score |

### Key Metrics

- **P95**: 6550 ms
- **P99**: 9980 ms
- **Avg**: 1810 ms
- **Error rate**: 1.87%
- **Throughput**: 94.8 rps
- **Total reqs**: 105241
- **Peak VUs**: 850

### Anomalies

_None detected vs historical runs._

### Root Cause Analysis

**1. No significant issues detected**
> Evidence: All metrics within expected ranges based on history
> Action: No action required

### Bottleneck Prediction

Predicted inflection point: **~300 VUs**  
_Latency growth rate accelerates around 300 VUs -- monitor closely above this point_  
_(based on 4 data points across all test types)_

| VUs | P95 (ms) | Bar |
|----:|---------:|-----|
| 150 | 4620 | ######### |
| 200 | 5830 | ########### |
| 300 | 5810 | ########### |
| 600 | 10760 | ##################### |
