#!/usr/bin/env python3
"""
AI-powered post-run analysis for k6 performance tests.

Implements the full AI in performance testing pipeline:
  * Anomaly detection    -- Z-score vs run history; flags latency spikes & error-rate outliers
  * Adaptive thresholds  -- learns mean+2*std from history, replaces fixed percentages (>=5 runs)
  * Release readiness    -- 0-100 score with letter grade (A/B/C/F)
  * Root-cause analysis  -- rule-based hypotheses from metric patterns
  * Bottleneck prediction-- inflection-point VU count from cross-test history
  * GitHub step summary  -- rich markdown posted to Actions job summary

Usage (local):
  python ai_analysis.py --test-type load --log results/load_local.log

Usage (CI):
  python3 ai_analysis.py --test-type smoke --log k6-perf-tests/results/smoke_ci.log --ci
"""

from __future__ import annotations
import argparse
import json
import os
import re
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR   = Path(__file__).parent
HISTORY_FILE = SCRIPT_DIR / "run_history.json"
RESULTS_DIR  = SCRIPT_DIR / "results"

MIN_RUNS_FOR_ADAPTIVE = 5

# Static p95 fallback thresholds (ms) -- used until history has >= 5 runs
STATIC_P95 = {
    "smoke":       300,
    "load":        7000,
    "stress":      11000,
    "spike":       8000,
    "soak":        5500,
    "scalability": 10000,
    "breakpoint":  None,
}

TEST_TYPES = list(STATIC_P95.keys())

# These tests intentionally push the server to its limit -- low scores are expected
# and do NOT indicate a release problem.
LIMIT_FINDING_TESTS = {"stress", "scalability", "breakpoint"}


# ---------------------------------------------------------------------------
# Log parsing
# ---------------------------------------------------------------------------

def _read_log(path: Path) -> str:
    """Read k6 log -- handles UTF-16 LE (Windows PowerShell Tee-Object) and UTF-8 (Linux CI)."""
    raw = path.read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16", errors="replace")
    return raw.decode("utf-8-sig", errors="replace")


def _parse_ms(s: str) -> float | None:
    """Convert k6 duration string (e.g. '2.67s', '312ms', '1m2s') to milliseconds."""
    s = s.strip()
    total = 0.0
    # alternation order matters: try 'ms' before 'm' to avoid short-circuit
    for val, unit in re.findall(r"([\d.]+)(ms|m|h|s)", s):
        v = float(val)
        if unit == "ms": total += v
        elif unit == "s": total += v * 1_000
        elif unit == "m": total += v * 60_000
        elif unit == "h": total += v * 3_600_000
    return total if total else None


def parse_k6_log(path: Path) -> dict:
    """
    Extract summary metrics from a k6 v2 text log.
    Returns empty dict when the file is missing or the summary block is absent.
    """
    try:
        text = _read_log(path)
    except (FileNotFoundError, OSError) as exc:
        print(f"[AI] Cannot read log: {exc}")
        return {}

    m: dict = {}

    # http_req_duration (main line, not the filtered sub-line with extra indent)
    dur = re.search(
        r"^\s{4}http_req_duration[^:]+:\s+"
        r"avg=(\S+)\s+min=(\S+)\s+med=(\S+)\s+max=(\S+)"
        r".*?p\(90\)=(\S+)\s+p\(95\)=(\S+)\s+p\(99\)=(\S+)",
        text, re.MULTILINE,
    )
    if dur:
        m["avg_ms"] = _parse_ms(dur.group(1))
        m["min_ms"] = _parse_ms(dur.group(2))
        m["med_ms"] = _parse_ms(dur.group(3))
        m["max_ms"] = _parse_ms(dur.group(4))
        m["p90_ms"] = _parse_ms(dur.group(5))
        m["p95_ms"] = _parse_ms(dur.group(6))
        m["p99_ms"] = _parse_ms(dur.group(7))

    # http_req_failed  -> 0.00%  0 out of N
    f = re.search(r"http_req_failed[^:]+:\s+([\d.]+)%", text)
    if f:
        m["error_rate"] = float(f.group(1)) / 100.0

    # checks_succeeded -> 100.00% N out of N
    c = re.search(r"checks_succeeded[^:]+:\s+([\d.]+)%", text)
    if c:
        m["checks_pass_rate"] = float(c.group(1)) / 100.0

    # http_reqs        -> N   X.XX/s
    r = re.search(r"http_reqs[^:]+:\s+(\d+)\s+([\d.]+)/s", text)
    if r:
        m["total_reqs"]     = int(r.group(1))
        m["throughput_rps"] = float(r.group(2))

    # vus_max          -> N   min=N  max=N
    # For multi-scenario tests (scalability) k6 reports pool reservation, not peak load.
    # Use the max VU count from the scenario progress lines instead when available.
    scenario_vus = re.findall(r'\]\s+(\d+)\s+VUs\s+\d+m', text)
    if scenario_vus:
        m["vus_max"] = max(int(x) for x in scenario_vus)
    else:
        v = re.search(r"vus_max[^:]+:\s+(\d+)", text)
        if v:
            m["vus_max"] = int(v.group(1))

    return {k: val for k, val in m.items() if val is not None}


# ---------------------------------------------------------------------------
# Run history
# ---------------------------------------------------------------------------

def load_history() -> dict:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8-sig"))
        except Exception:
            pass
    return {}


def save_history(history: dict) -> None:
    HISTORY_FILE.write_text(json.dumps(history, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Anomaly detection
# ---------------------------------------------------------------------------

def detect_anomalies(metrics: dict, past: list) -> list[dict]:
    """
    Z-score anomaly detection against historical runs.
    Requires >= 3 past runs; returns empty list otherwise.
    """
    if len(past) < 3:
        return []

    checks = [
        ("p95_ms",         "P95 latency",  "high"),
        ("error_rate",     "Error rate",   "high"),
        ("throughput_rps", "Throughput",   "low"),
    ]
    results = []
    for field, label, bad_dir in checks:
        cur = metrics.get(field)
        if cur is None:
            continue
        vals = [r[field] for r in past if r.get(field) is not None]
        if len(vals) < 3:
            continue
        mean = statistics.mean(vals)
        std  = statistics.stdev(vals)
        if std < 1e-9:
            continue
        z = (cur - mean) / std
        if abs(z) < 2.0:
            continue
        bad = (z > 0) if bad_dir == "high" else (z < 0)
        results.append({
            "field":    field,
            "label":    label,
            "current":  cur,
            "mean":     mean,
            "z":        z,
            "severity": "HIGH" if abs(z) > 3 else "MEDIUM",
            "bad":      bad,
        })
    return results


# ---------------------------------------------------------------------------
# Adaptive threshold
# ---------------------------------------------------------------------------

def adaptive_p95(past: list) -> float | None:
    """Return mean + 2*std of historical p95 values. None until >= 5 runs."""
    vals = [r["p95_ms"] for r in past if r.get("p95_ms") is not None]
    if len(vals) < MIN_RUNS_FOR_ADAPTIVE:
        return None
    return statistics.mean(vals) + 2 * statistics.stdev(vals)


# ---------------------------------------------------------------------------
# Release readiness score  (0-100)
# ---------------------------------------------------------------------------

def compute_score(metrics: dict, past: list, static_p95_ms: float | None = None,
                  test_type: str = "") -> dict:
    comps: dict[str, tuple[int, int, str]] = {}

    # P95 latency  -- 40 pts
    p95       = metrics.get("p95_ms")
    threshold = adaptive_p95(past) or static_p95_ms
    if p95 is not None and threshold is not None:
        ratio = p95 / threshold
        if ratio <= 0.70:
            pts = 40
        elif ratio <= 1.00:
            pts = int(40 * (1.0 - ratio) / 0.30)
        else:
            pts = max(0, int(40 * (1.0 - (ratio - 1.0) * 2)))
        source = "adaptive" if adaptive_p95(past) else "static"
        comps["P95 Latency"] = (pts, 40, f"{p95:.0f} ms vs {source} threshold {threshold:.0f} ms")
    else:
        comps["P95 Latency"] = (20, 40, "No threshold available -- neutral score")

    # Error rate  -- 30 pts
    err = metrics.get("error_rate", 0.0)
    if err < 0.005:   ep = 30
    elif err < 0.01:  ep = 24
    elif err < 0.05:  ep = 14
    elif err < 0.15:  ep = 5
    else:             ep = 0
    comps["Error Rate"] = (ep, 30, f"{err * 100:.2f}%")

    # Checks pass rate  -- 15 pts
    chk = metrics.get("checks_pass_rate", 1.0)
    if chk >= 1.00:   cp = 15
    elif chk >= 0.99: cp = 10
    elif chk >= 0.95: cp = 5
    else:             cp = 0
    comps["Checks"] = (cp, 15, f"{chk * 100:.1f}% passed")

    # Throughput vs historical  -- 15 pts
    tput      = metrics.get("throughput_rps")
    past_tput = [r["throughput_rps"] for r in past if r.get("throughput_rps") is not None]
    if tput is not None and len(past_tput) >= 3:
        ratio = tput / statistics.mean(past_tput)
        tp = 15 if ratio >= 0.90 else (8 if ratio >= 0.75 else 0)
        comps["Throughput"] = (tp, 15, f"{tput:.1f} rps vs hist mean {statistics.mean(past_tput):.1f} rps")
    else:
        comps["Throughput"] = (8, 15, "Insufficient history -- neutral score")

    total = sum(v[0] for v in comps.values())
    if total >= 90:   grade, verdict = "A", "READY TO RELEASE"
    elif total >= 70: grade, verdict = "B", "ACCEPTABLE -- monitor closely"
    elif total >= 50: grade, verdict = "C", "BORDERLINE -- review before release"
    else:             grade, verdict = "F", "NOT READY -- block release"

    if test_type in LIMIT_FINDING_TESTS:
        verdict = "LIMIT FINDING -- informational only, not a release gate"

    return {"total": total, "grade": grade, "verdict": verdict, "components": comps}


# ---------------------------------------------------------------------------
# Root-cause analysis
# ---------------------------------------------------------------------------

def generate_rca(metrics: dict, past: list) -> list[dict]:
    p95  = metrics.get("p95_ms", 0)
    p99  = metrics.get("p99_ms", 0)
    err  = metrics.get("error_rate", 0)
    tput = metrics.get("throughput_rps", 0)

    past_p95  = [r["p95_ms"] for r in past if r.get("p95_ms") is not None]
    hist_mean = statistics.mean(past_p95) if past_p95 else None
    adap      = adaptive_p95(past)

    hyps: list[dict] = []

    if err > 0.10 and p95 > 8000:
        hyps.append({
            "cause":    "Server resource saturation",
            "evidence": f"{err * 100:.1f}% errors with p95={p95:.0f} ms -- queue overflow or CPU pinned",
            "action":   "Check server CPU/memory at peak; reduce VU ceiling or scale horizontally",
        })

    if p99 and p95 and p99 / p95 > 2.5:
        hyps.append({
            "cause":    "Long-tail outliers (GC pauses or slow DB queries)",
            "evidence": f"p99/p95 ratio = {p99 / p95:.1f}x -- significant outliers beyond typical latency",
            "action":   "Profile DB query plans and JVM GC settings; look for lock contention or missing indexes",
        })

    if err > 0.05 and (adap is None or p95 < adap * 1.2):
        hyps.append({
            "cause":    "Connection or rate-limit rejection",
            "evidence": f"{err * 100:.1f}% errors without proportional latency spike -- upstream rejecting connections",
            "action":   "Check API gateway rate limits, connection pool sizes, load balancer health config",
        })

    if hist_mean and p95 > hist_mean * 1.30 and err < 0.02:
        hyps.append({
            "cause":    "Performance regression (likely a recent deployment)",
            "evidence": (
                f"p95={p95:.0f} ms vs historical mean {hist_mean:.0f} ms "
                f"(+{(p95 / hist_mean - 1) * 100:.0f}%), error rate still low"
            ),
            "action":   "Compare git log between this run and last good baseline; look for N+1 query regressions",
        })

    past_tp = [r["throughput_rps"] for r in past if r.get("throughput_rps") is not None]
    if past_tp and tput and tput < statistics.mean(past_tp) * 0.80:
        hyps.append({
            "cause":    "Throughput degradation",
            "evidence": (
                f"{tput:.1f} rps vs historical mean {statistics.mean(past_tp):.1f} rps "
                f"(>{(1 - tput / statistics.mean(past_tp)) * 100:.0f}% drop)"
            ),
            "action":   "Investigate thread pool exhaustion, connection pool limits, or upstream throttling",
        })

    if not hyps:
        hyps.append({
            "cause":    "No significant issues detected",
            "evidence": "All metrics within expected ranges based on history",
            "action":   "No action required",
        })

    return hyps


# ---------------------------------------------------------------------------
# Bottleneck prediction
# ---------------------------------------------------------------------------

def predict_bottleneck(history: dict) -> dict | None:
    """
    Find the VU count where p95 growth rate accelerates (inflection point).
    Uses (vus_max, p95_ms) pairs from all test types with >= 25 VUs
    (smoke/health-check runs are excluded as they're not production load shapes).
    """
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
    if len(pts) < 4:
        return None

    best_change, best_vus = 0.0, None
    for i in range(1, len(pts) - 1):
        v0, p0 = pts[i - 1]
        v1, p1 = pts[i]
        v2, p2 = pts[i + 1]
        s1 = (p1 - p0) / (v1 - v0) if v1 != v0 else 0.0
        s2 = (p2 - p1) / (v2 - v1) if v2 != v1 else 0.0
        if s2 - s1 > best_change:
            best_change, best_vus = s2 - s1, v1

    if best_vus is None:
        return None
    return {
        "vus":   best_vus,
        "note":  f"Latency growth rate accelerates around {best_vus} VUs -- monitor closely above this point",
        "count": len(pts),
        "curve": pts,
    }


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _badge(grade: str, test_type: str = "") -> str:
    if test_type in LIMIT_FINDING_TESTS:
        return "INFO"
    return {"A": "PASS", "B": "PASS", "C": "WARN", "F": "FAIL"}.get(grade, "")


def build_markdown(
    test_type: str, metrics: dict, score: dict,
    anomalies: list, rca: list, bottleneck: dict | None,
) -> str:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
    g  = score["grade"]
    lines = [
        f"## [{_badge(g, test_type)}] AI Analysis: {test_type.upper()} -- {ts}",
        "",
        f"**Release Score: {score['total']}/100 (Grade {g}) -- {score['verdict']}**",
        "",
        "| Component | Score | Max | Detail |",
        "|-----------|------:|----:|--------|",
    ]
    for name, (pts, mx, detail) in score["components"].items():
        lines.append(f"| {name} | {pts} | {mx} | {detail} |")

    lines += ["", "### Key Metrics", ""]
    for label, key, fmt in [
        ("P95",        "p95_ms",         lambda v: f"{v:.0f} ms"),
        ("P99",        "p99_ms",         lambda v: f"{v:.0f} ms"),
        ("Avg",        "avg_ms",         lambda v: f"{v:.0f} ms"),
        ("Error rate", "error_rate",     lambda v: f"{v * 100:.2f}%"),
        ("Throughput", "throughput_rps", lambda v: f"{v:.1f} rps"),
        ("Total reqs", "total_reqs",     lambda v: str(int(v))),
        ("Peak VUs",   "vus_max",        lambda v: str(int(v))),
    ]:
        val = metrics.get(key)
        if val is not None:
            lines.append(f"- **{label}**: {fmt(val)}")

    if anomalies:
        lines += ["", "### Anomalies Detected", ""]
        for a in anomalies:
            sev  = "HIGH" if a["severity"] == "HIGH" else "MEDIUM"
            arrow = "up" if a["z"] > 0 else "down"
            lines.append(
                f"- **[{sev}] {a['label']}** trending {arrow}: "
                f"z={a['z']:+.2f} (current={a['current']:.1f}, historical mean={a['mean']:.1f})"
            )
    else:
        lines += ["", "### Anomalies", "", "_None detected vs historical runs._"]

    lines += ["", "### Root Cause Analysis", ""]
    for i, h in enumerate(rca, 1):
        lines += [
            f"**{i}. {h['cause']}**",
            f"> Evidence: {h['evidence']}",
            f"> Action: {h['action']}",
            "",
        ]

    if bottleneck:
        lines += [
            "### Bottleneck Prediction",
            "",
            f"Predicted inflection point: **~{bottleneck['vus']} VUs**  ",
            f"_{bottleneck['note']}_  ",
            f"_(based on {bottleneck['count']} data points across all test types)_",
            "",
            "| VUs | P95 (ms) | Bar |",
            "|----:|---------:|-----|",
        ]
        for vus, p95 in bottleneck["curve"]:
            bar = "#" * min(30, int(p95 / 500))
            lines.append(f"| {vus} | {p95:.0f} | {bar} |")
        lines.append("")

    return "\n".join(lines)


def print_console(test_type: str, metrics: dict, score: dict, anomalies: list) -> None:
    sep = "=" * 52
    print(f"\n{sep}")
    print(f"  AI ANALYSIS: {test_type.upper()}")
    print(sep)
    print(f"  Score  : {score['total']}/100  Grade {score['grade']}")
    print(f"  Verdict: {score['verdict']}")
    if metrics.get("p95_ms"):
        print(f"  P95    : {metrics['p95_ms']:.0f} ms")
    if metrics.get("error_rate") is not None:
        print(f"  Errors : {metrics['error_rate'] * 100:.2f}%")
    if metrics.get("throughput_rps"):
        print(f"  RPS    : {metrics['throughput_rps']:.1f}")
    if anomalies:
        print(f"  Anomalies ({len(anomalies)} detected):")
        for a in anomalies:
            print(f"    [{a['severity']}] {a['label']}  z={a['z']:+.2f}")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="AI post-run analysis for k6 tests")
    parser.add_argument("--test-type", required=True, choices=TEST_TYPES)
    parser.add_argument("--log",       required=True, help="Path to k6 log file")
    parser.add_argument("--ci",        action="store_true",
                        help="Append report to GITHUB_STEP_SUMMARY")
    args = parser.parse_args()

    log_path = Path(args.log)
    print(f"[AI] Analyzing {args.test_type} test -- {log_path}")

    metrics = parse_k6_log(log_path)
    if not metrics:
        print(f"[AI] WARNING: no metrics extracted from {log_path} (summary block missing?)")

    history    = load_history()
    past       = [r for r in history.get(args.test_type, []) if isinstance(r, dict)]

    anomalies  = detect_anomalies(metrics, past)
    score      = compute_score(metrics, past, STATIC_P95.get(args.test_type), args.test_type)
    rca        = generate_rca(metrics, past)
    bottleneck = predict_bottleneck(history)

    print_console(args.test_type, metrics, score, anomalies)

    # Markdown report
    RESULTS_DIR.mkdir(exist_ok=True)
    report      = build_markdown(args.test_type, metrics, score, anomalies, rca, bottleneck)
    report_path = RESULTS_DIR / f"ai_report_{args.test_type}.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"[AI] Report saved: {report_path}")

    # GitHub Actions step summary
    if args.ci:
        summary_path = os.environ.get("GITHUB_STEP_SUMMARY", "")
        if summary_path:
            with open(summary_path, "a", encoding="utf-8") as fh:
                fh.write(report + "\n\n")
            print("[AI] Written to GITHUB_STEP_SUMMARY")

    # Update run history
    if metrics:
        record = {
            "timestamp":     datetime.now(timezone.utc).isoformat(),
            "ci":            args.ci,
            "release_score": score["total"],
            "grade":         score["grade"],
            **metrics,
        }
        bucket = history.setdefault(args.test_type, [])
        if isinstance(bucket, list):
            bucket.append(record)
            history[args.test_type] = bucket[-50:]  # keep last 50
        save_history(history)
        n = len(history[args.test_type])
        print(f"[AI] History updated ({n} {args.test_type} run{'s' if n != 1 else ''} stored)")

    # Exit 1 on grade F for release-gate tests only; limit-finding tests never block CI
    is_gate = args.test_type not in LIMIT_FINDING_TESTS
    sys.exit(1 if score["grade"] == "F" and is_gate else 0)


if __name__ == "__main__":
    main()
