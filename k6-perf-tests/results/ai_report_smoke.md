## [PASS] AI Analysis: SMOKE -- 2026-06-12 15:49 UTC

**Release Score: 73/100 (Grade B) -- ACCEPTABLE -- monitor closely**

| Component | Score | Max | Detail |
|-----------|------:|----:|--------|
| P95 Latency | 20 | 40 | No threshold available -- neutral score |
| Error Rate | 30 | 30 | 0.00% |
| Checks | 15 | 15 | 100.0% passed |
| Throughput | 8 | 15 | Insufficient history -- neutral score |

### Key Metrics

- **Error rate**: 0.00%
- **Peak VUs**: 5

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
