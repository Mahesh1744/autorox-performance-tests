#!/usr/bin/env python3
"""
Intelligent load configuration advisor.

Reads run_history.json to recommend optimal VU counts, flag performance trends,
and predict the system bottleneck from the VU-vs-p95 curve.

Usage:
  python suggest_config.py                        # show all test types
  python suggest_config.py --test-type load       # focused advice for one test
"""

from __future__ import annotations
import argparse
import json
import statistics
from pathlib import Path

HISTORY_FILE = Path(__file__).parent / "run_history.json"

TEST_ORDER = ["smoke", "load", "stress", "spike", "soak", "scalability"]


def load_history() -> dict:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8-sig"))
        except Exception:
            pass
    return {}


def _mean(vals: list) -> float:
    return statistics.mean(vals) if vals else 0.0


def analyse(test_type: str, runs: list) -> None:
    if not runs:
        print(f"  [{test_type.upper()}]  No history yet -- run the test to start collecting data.")
        return

    recent = [r for r in runs[-10:] if isinstance(r, dict)]
    p95s   = [r["p95_ms"]         for r in recent if r.get("p95_ms") is not None]
    errs   = [r["error_rate"]     for r in recent if r.get("error_rate") is not None]
    scores = [r["release_score"]  for r in recent if r.get("release_score") is not None]
    tputs  = [r["throughput_rps"] for r in recent if r.get("throughput_rps") is not None]

    print(f"\n  [{test_type.upper()}]  ({len(recent)} recent run{'s' if len(recent) != 1 else ''})")

    # P95 trend
    if p95s:
        mean_p95 = _mean(p95s)
        trend    = p95s[-1] - p95s[0] if len(p95s) > 1 else 0.0
        print(f"  P95:    mean={mean_p95:.0f} ms, latest={p95s[-1]:.0f} ms, trend={trend:+.0f} ms over {len(p95s)} runs")
        if len(p95s) >= 3:
            std = statistics.stdev(p95s)
            print(f"          stdev={std:.0f} ms  (adaptive threshold kicks in after {max(0, 5-len(p95s))} more runs)")
        # Need >= 4 data points before trend warnings are statistically meaningful
        if len(p95s) >= 4:
            if trend > mean_p95 * 0.15:
                print("  WARN:   P95 trending UP -- investigate degradation before increasing load")
            elif trend < mean_p95 * -0.10:
                print("  GOOD:   P95 trending DOWN -- consider increasing VU count by 10-20%")

    # Error rate
    if errs:
        mean_err = _mean(errs)
        print(f"  Errors: mean={mean_err * 100:.2f}%")
        if mean_err > 0.05:
            print("  WARN:   Error rate above 5% -- reduce load or fix errors before scaling up")
        elif mean_err < 0.005 and len(errs) >= 3:
            print("  GOOD:   Error rate consistently below 0.5% -- stable under current config")

    # Release scores
    p95_rising = len(p95s) >= 4 and p95s[-1] > _mean(p95s) * 1.15
    if scores:
        mean_score   = _mean(scores)
        latest_score = scores[-1]
        print(f"  Score:  mean={mean_score:.0f}/100, latest={latest_score}/100")
        if mean_score < 70:
            print("  WARN:   Consistently below 70/100 -- current config is too aggressive")
        elif mean_score >= 90 and latest_score >= 90 and not p95_rising:
            print("  SUGGEST: Consistently A-grade -- safe to increase VUs by 20-30%")
        elif 70 <= mean_score < 80:
            print("  SUGGEST: Borderline B-grade -- keep current VUs, focus on reducing p95")

    # Throughput trend
    if len(tputs) >= 3:
        tput_trend = tputs[-1] - tputs[0]
        if tput_trend < -_mean(tputs) * 0.15:
            print(f"  WARN:   Throughput dropping ({tputs[-1]:.1f} vs {tputs[0]:.1f} rps) "
                  "-- possible thread pool or connection limit")


def bottleneck_report(history: dict) -> None:
    # Exclude sub-25 VU runs (smoke/health checks) -- not meaningful for bottleneck analysis
    pts = sorted(
        {
            (r["vus_max"], r["p95_ms"])
            for runs in history.values()
            if isinstance(runs, list)
            for r in runs
            if r.get("vus_max") and r.get("p95_ms") and r["vus_max"] >= 25
        },
        key=lambda x: x[0],
    )
    if len(pts) < 3:
        print("\n  [BOTTLENECK]  Not enough data points yet (need >= 3 VU levels).")
        return

    print(f"\n  [BOTTLENECK PREDICTION]  VU -> P95 curve ({len(pts)} points):")
    for vus, p95 in pts:
        bar = "#" * min(35, int(p95 / 300))
        print(f"    {vus:5d} VUs  {p95:7.0f} ms  {bar}")

    if len(pts) >= 4:
        best_change, best_vus = 0.0, None
        for i in range(1, len(pts) - 1):
            v0, p0 = pts[i - 1]
            v1, p1 = pts[i]
            v2, p2 = pts[i + 1]
            s1 = (p1 - p0) / (v1 - v0) if v1 != v0 else 0.0
            s2 = (p2 - p1) / (v2 - v1) if v2 != v1 else 0.0
            if s2 - s1 > best_change:
                best_change, best_vus = s2 - s1, v1

        if best_vus:
            print(f"\n  Predicted inflection point: ~{best_vus} VUs")
            print("  Keep steady-state load below this for SLA compliance.")
            print("  Above this point p95 grows non-linearly -- plan capacity accordingly.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Intelligent load configuration advisor")
    parser.add_argument(
        "--test-type",
        choices=TEST_ORDER,
        help="Focus on one test type (default: all)",
    )
    args = parser.parse_args()

    history = load_history()
    has_data = any(
        isinstance(v, list) and v
        for v in history.values()
    )
    if not has_data:
        print("No run history found. Run at least one test and re-check.")
        return

    sep = "=" * 52
    print(f"\n{sep}")
    print("  INTELLIGENT LOAD CONFIGURATION ADVISOR")
    print(f"{sep}")

    if args.test_type:
        analyse(args.test_type, [r for r in history.get(args.test_type, []) if isinstance(r, dict)])
    else:
        for tt in TEST_ORDER:
            runs = history.get(tt, [])
            if isinstance(runs, list):
                analyse(tt, runs)

    bottleneck_report(history)
    print()


if __name__ == "__main__":
    main()
