## [PASS] AI Analysis: LOAD -- 2026-06-11 21:33 UTC

**Release Score: 75/100 (Grade B) -- ACCEPTABLE -- monitor closely**

| Component | Score | Max | Detail |
|-----------|------:|----:|--------|
| P95 Latency | 22 | 40 | 5830 ms vs static threshold 7000 ms |
| Error Rate | 30 | 30 | 0.00% |
| Checks | 15 | 15 | 100.0% passed |
| Throughput | 8 | 15 | Insufficient history -- neutral score |

### Key Metrics

- **P95**: 5830 ms
- **P99**: 7650 ms
- **Avg**: 2670 ms
- **Error rate**: 0.00%
- **Throughput**: 53.5 rps
- **Total reqs**: 32451
- **Peak VUs**: 200

### Anomalies

_None detected vs historical runs._

### Root Cause Analysis

**1. No significant issues detected**
> Evidence: All metrics within expected ranges based on history
> Action: No action required

### Bottleneck Prediction

Predicted inflection point: **~5 VUs**  
_Latency growth rate accelerates around 5 VUs -- monitor closely above this point_  
_(based on 6 data points across all test types)_

| VUs | P95 (ms) | Bar |
|----:|---------:|-----|
| 5 | 81 |  |
| 5 | 269 |  |
| 150 | 4620 | ######### |
| 200 | 5830 | ########### |
| 300 | 5810 | ########### |
| 600 | 10760 | ##################### |
