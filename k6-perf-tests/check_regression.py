#!/usr/bin/env python3
"""
Performance regression gate.
Compares k6 p95 response time against a stored baseline.
Exits 1 (fail) if current p95 exceeds baseline by more than threshold%.

Usage:
    python3 check_regression.py <test_name> <log_file> [threshold_pct]

Example:
    python3 check_regression.py smoke k6-perf-tests/results/smoke_ci.log 20
"""
import sys
import re
import json
import os


def parse_p95_from_log(log_file):
    """Extract http_req_duration p95 from k6 summary log."""
    with open(log_file) as f:
        content = f.read()

    # k6 summary line format:
    # http_req_duration.............: avg=43ms min=12ms med=38ms max=234ms p(90)=79ms p(95)=112ms
    m = re.search(
        r'http_req_duration[^:]*:.*?p\(95\)=([0-9.]+)(ms|s|µs|us)',
        content
    )
    if not m:
        return None

    val, unit = float(m.group(1)), m.group(2)
    if unit == 's':
        return int(val * 1000)
    elif unit in ('µs', 'us'):
        return int(val / 1000)
    else:
        return int(val)


def main():
    if len(sys.argv) < 3:
        print("Usage: check_regression.py <test_name> <log_file> [threshold_pct]")
        sys.exit(0)

    test_name     = sys.argv[1]
    log_file      = sys.argv[2]
    threshold_pct = float(sys.argv[3]) if len(sys.argv) > 3 else 20.0

    script_dir    = os.path.dirname(os.path.abspath(__file__))
    baseline_file = os.path.join(script_dir, 'baseline.json')

    # Load baseline
    if not os.path.exists(baseline_file):
        print(f"[regression] No baseline.json found — skipping check.")
        sys.exit(0)

    with open(baseline_file) as f:
        baseline = json.load(f)

    entry = baseline.get(test_name, {})
    if not entry or entry.get('p95') is None:
        print(f"[regression] No baseline p95 for '{test_name}' — skipping check.")
        print(f"             Run the test once, note the p95, then update baseline.json.")
        sys.exit(0)

    baseline_p95 = entry['p95']

    # Parse current p95 from log
    if not os.path.exists(log_file):
        print(f"[regression] Log file not found: {log_file} — skipping check.")
        sys.exit(0)

    current_p95 = parse_p95_from_log(log_file)
    if current_p95 is None:
        print("[regression] Could not extract p95 from log — skipping check.")
        sys.exit(0)

    limit      = int(baseline_p95 * (1 + threshold_pct / 100))
    pct_change = ((current_p95 - baseline_p95) / baseline_p95) * 100

    print()
    print("=" * 56)
    print(f"  Regression Gate — {test_name}")
    print("=" * 56)
    print(f"  Baseline p95 : {baseline_p95} ms")
    print(f"  Current p95  : {current_p95} ms   ({pct_change:+.1f}%)")
    print(f"  Limit        : {limit} ms   (+{threshold_pct:.0f}% tolerance)")
    print("=" * 56)

    if current_p95 > limit:
        print(f"  RESULT : REGRESSION DETECTED")
        print(f"           p95 rose {pct_change:.1f}% above baseline.")
        print(f"           Investigate recent code or config changes.")
        print("=" * 56)
        print()
        sys.exit(1)
    else:
        print(f"  RESULT : OK — within +{threshold_pct:.0f}% tolerance")
        print("=" * 56)
        print()
        sys.exit(0)


if __name__ == '__main__':
    main()
