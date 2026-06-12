#!/usr/bin/env python3
"""
Autorox Performance Agent
Unified CLI for running, analyzing, and managing all k6 performance tests.

Usage (interactive):
  python perf_agent.py

Usage (command-line):
  python perf_agent.py run smoke
  python perf_agent.py run all
  python perf_agent.py status
  python perf_agent.py report [test_type]
  python perf_agent.py suggest
  python perf_agent.py history
  python perf_agent.py baseline
"""

from __future__ import annotations
import argparse
import importlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR    = Path(__file__).parent
RESULTS_DIR   = SCRIPT_DIR / "results"
HISTORY_FILE  = SCRIPT_DIR / "run_history.json"
BASELINE_FILE = SCRIPT_DIR / "baseline.json"

TESTS = {
    "smoke":       {"script": "smoke-test.js",      "label": "Smoke",       "vus": "5",        "duration": "~2 min",  "heavy": False},
    "load":        {"script": "load-test.js",        "label": "Load",        "vus": "200",      "duration": "~10 min", "heavy": False},
    "stress":      {"script": "stress-test.js",      "label": "Stress",      "vus": "100->600", "duration": "~14 min", "heavy": True},
    "spike":       {"script": "spike-test.js",       "label": "Spike",       "vus": "50->300",  "duration": "~7 min",  "heavy": False},
    "soak":        {"script": "soak-test.js",        "label": "Soak",        "vus": "150",      "duration": "~30 min", "heavy": False},
    "scalability": {"script": "scalability-test.js", "label": "Scalability", "vus": "25->500",  "duration": "~18 min", "heavy": True},
    "breakpoint":  {"script": "breakpoint-test.js",  "label": "Breakpoint",  "vus": "100->2000","duration": "~varies", "heavy": True},
}

RUN_SEQUENCE          = ["smoke", "load", "stress", "spike", "soak", "scalability"]
RECOVERY_AFTER        = {"stress", "scalability", "breakpoint"}
RECOVERY_WAIT_SECS    = 180
HEALTH_CHECK_TIMEOUT  = 30

# ANSI colors -- enabled via ctypes on Windows
def _enable_ansi() -> None:
    try:
        import ctypes
        k32    = ctypes.windll.kernel32
        handle = k32.GetStdHandle(-11)
        mode   = ctypes.c_ulong()
        k32.GetConsoleMode(handle, ctypes.byref(mode))
        k32.SetConsoleMode(handle, mode.value | 4)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
    except Exception:
        pass

_enable_ansi()
_USE_COLOR = sys.stdout.isatty()

class _C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    RED    = "\033[91m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    CYAN   = "\033[96m"
    WHITE  = "\033[97m"

def _c(color: str, text: str) -> str:
    if not _USE_COLOR:
        return text
    return f"{color}{text}{_C.RESET}"

def _sep(char: str = "=", width: int = 56) -> str:
    return char * width


# ---------------------------------------------------------------------------
# Server health check
# ---------------------------------------------------------------------------

def health_check(verbose: bool = True) -> tuple[bool, float, float]:
    """
    Run smoke-test.js with 1 VU for 30 s.
    Returns (healthy, p95_ms, error_rate).
    Server is healthy when p95 < 500 ms and error rate < 5%.
    """
    if verbose:
        print(f"\n{_c(_C.CYAN, 'Health check')} (1 VU, {HEALTH_CHECK_TIMEOUT}s)...", flush=True)

    result = subprocess.run(
        ["k6", "run", str(SCRIPT_DIR / "smoke-test.js"),
         "--vus", "1", f"--duration", f"{HEALTH_CHECK_TIMEOUT}s",
         "--summary-trend-stats", "avg,p(95)", "--quiet"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(SCRIPT_DIR),
    )
    out = result.stdout + result.stderr

    p95_ms, err_rate = 0.0, 0.0

    m = re.search(r"p\(95\)=([\d.]+)(ms|s)", out)
    if m:
        v, u = float(m.group(1)), m.group(2)
        p95_ms = v if u == "ms" else v * 1000

    m = re.search(r"http_req_failed[^:]+:\s+([\d.]+)%", out)
    if m:
        err_rate = float(m.group(1)) / 100.0

    healthy = result.returncode == 0 and p95_ms < 500 and err_rate < 0.05

    if verbose:
        tag = _c(_C.GREEN, "HEALTHY") if healthy else _c(_C.RED, "UNHEALTHY")
        p95_str = f"{p95_ms:.0f} ms" if p95_ms else "N/A"
        print(f"  Status  : {tag}")
        print(f"  P95     : {p95_str}  |  Errors: {err_rate*100:.1f}%")

    return healthy, p95_ms, err_rate


def wait_for_recovery(prev_test: str) -> None:
    """Wait and poll until server is healthy after a heavy test."""
    print(_c(_C.YELLOW, f"\nServer recovery wait after {prev_test} ({RECOVERY_WAIT_SECS}s max)..."))
    waited = 0
    interval = 30
    while waited < RECOVERY_WAIT_SECS:
        time.sleep(interval)
        waited += interval
        healthy, p95, _ = health_check(verbose=False)
        remaining = RECOVERY_WAIT_SECS - waited
        state = "HEALTHY" if healthy else "recovering"
        print(f"  +{waited:3d}s  server={state}  p95={p95:.0f}ms  ({remaining}s remaining)")
        if healthy:
            print(_c(_C.GREEN, "  Server recovered — continuing."))
            return
    print(_c(_C.YELLOW, "  Recovery timeout — proceeding anyway."))


# ---------------------------------------------------------------------------
# Run a single test
# ---------------------------------------------------------------------------

def run_test(test_type: str, skip_health_check: bool = False) -> int:
    """
    Run a k6 test, stream output to terminal + log file, then run AI analysis.
    Returns k6 exit code (0=pass, 99=threshold, 107=login fail).
    """
    cfg = TESTS.get(test_type)
    if cfg is None:
        print(_c(_C.RED, f"Unknown test type: {test_type}"))
        return 1

    script = SCRIPT_DIR / cfg["script"]
    if not script.exists():
        print(_c(_C.RED, f"Script not found: {script.name}"))
        return 1

    RESULTS_DIR.mkdir(exist_ok=True)
    log_file = RESULTS_DIR / f"{test_type}_local.log"

    # Pre-flight health check for heavy tests
    if cfg["heavy"] and not skip_health_check:
        healthy, p95, _ = health_check()
        if not healthy:
            print(_c(_C.RED, f"\nServer unhealthy (p95={p95:.0f}ms) — aborting {test_type} test."))
            print(_c(_C.YELLOW, "Run 'status' to monitor, then retry when server is healthy."))
            return 1

    # Header
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{_sep()}")
    print(f"  {_c(_C.BOLD, cfg['label'].upper() + ' TEST')}"
          f"  |  {cfg['vus']} VUs  |  {cfg['duration']}")
    print(f"  Started: {ts}")
    print(_sep())
    print()

    # k6 run — output goes to terminal AND log file via PowerShell Tee-Object
    ps_cmd = (
        f'k6 run "{script}" '
        f'--summary-trend-stats "avg,min,med,max,p(90),p(95),p(99)" '
        f'2>&1 | Tee-Object -FilePath "{log_file}"; '
        f'exit $LASTEXITCODE'
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_cmd],
        cwd=str(SCRIPT_DIR),
    )
    exit_code = result.returncode

    # Result banner
    print(f"\n{_sep()}")
    if exit_code == 0:
        banner = _c(_C.GREEN, "PASSED -- all thresholds met")
    elif exit_code == 99:
        banner = _c(_C.YELLOW, "THRESHOLDS CROSSED (exit 99)")
    elif exit_code == 107:
        banner = _c(_C.RED, "LOGIN FAILED (exit 107) -- server may be recovering")
    else:
        banner = _c(_C.RED, f"FAILED (exit {exit_code})")
    print(f"  {banner}")
    print(_sep())

    if exit_code == 107:
        return exit_code

    # AI analysis
    if log_file.exists():
        _run_ai_analysis(test_type, log_file)

    return exit_code


def _run_ai_analysis(test_type: str, log_file: Path) -> None:
    """Import ai_analysis and run it inline (no subprocess overhead)."""
    print(f"\n{_c(_C.CYAN, 'AI Analysis...')}")
    try:
        import ai_analysis as ai
        importlib.reload(ai)

        metrics    = ai.parse_k6_log(log_file)
        history    = ai.load_history()
        past       = [r for r in history.get(test_type, []) if isinstance(r, dict)]
        anomalies  = ai.detect_anomalies(metrics, past)
        score      = ai.compute_score(metrics, past, ai.STATIC_P95.get(test_type))
        rca        = ai.generate_rca(metrics, past)
        bottleneck = ai.predict_bottleneck(history)

        ai.print_console(test_type, metrics, score, anomalies)

        report      = ai.build_markdown(test_type, metrics, score, anomalies, rca, bottleneck)
        report_path = RESULTS_DIR / f"ai_report_{test_type}.md"
        report_path.write_text(report, encoding="utf-8")
        print(f"  Report : {report_path.name}")

        if metrics:
            record = {
                "timestamp":     datetime.now(timezone.utc).isoformat(),
                "ci":            False,
                "release_score": score["total"],
                "grade":         score["grade"],
                **metrics,
            }
            # Scalability: k6 pool reservation != actual peak VUs
            if test_type == "scalability" and record.get("vus_max", 0) > 500:
                record["vus_max"] = 500
            bucket = history.setdefault(test_type, [])
            if isinstance(bucket, list):
                bucket.append(record)
                history[test_type] = bucket[-50:]
            ai.save_history(history)

    except Exception as exc:
        print(_c(_C.YELLOW, f"  AI analysis error: {exc}"))


# ---------------------------------------------------------------------------
# Run all tests in sequence
# ---------------------------------------------------------------------------

def run_all() -> None:
    """Run all tests in sequence with recovery waits between heavy tests."""
    print(f"\n{_c(_C.BOLD, 'ALL TESTS -- Sequential run')}")
    print(f"  Sequence: {' -> '.join(RUN_SEQUENCE)}")
    print(f"  Estimated total: ~80 min\n")

    results: dict[str, int] = {}

    for i, test_type in enumerate(RUN_SEQUENCE):
        print(f"\n[{i+1}/{len(RUN_SEQUENCE)}] {_c(_C.BOLD, test_type.upper())}")

        if i > 0 and RUN_SEQUENCE[i - 1] in RECOVERY_AFTER:
            wait_for_recovery(RUN_SEQUENCE[i - 1])

        code = run_test(test_type, skip_health_check=(test_type == "smoke"))
        results[test_type] = code

        if code == 107:
            print(_c(_C.RED, f"\nLogin failed for {test_type}. Stopping sequence."))
            break

    _print_run_summary(results)


def _print_run_summary(results: dict[str, int]) -> None:
    print(f"\n{_sep()}")
    print(f"  {_c(_C.BOLD, 'RUN COMPLETE')}")
    print(_sep("─"))
    for tt, code in results.items():
        if code == 0:   tag = _c(_C.GREEN,  "PASS      ")
        elif code == 99: tag = _c(_C.YELLOW, "THRESHOLD ")
        elif code == 107:tag = _c(_C.RED,    "LOGIN FAIL")
        else:            tag = _c(_C.RED,    f"FAIL({code}) ")
        print(f"  {tt:<14}  {tag}")
    print()


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def show_report(test_type: str | None = None) -> None:
    types = [test_type] if test_type else RUN_SEQUENCE
    found = False
    for tt in types:
        p = RESULTS_DIR / f"ai_report_{tt}.md"
        if p.exists():
            print(f"\n{_sep('─')}")
            print(p.read_text(encoding="utf-8-sig"))
            found = True
        else:
            print(_c(_C.DIM, f"  [{tt}]  No report yet."))
    if not found:
        print("Run tests first to generate AI reports.")


def show_history() -> None:
    if not HISTORY_FILE.exists():
        print("No run history yet.")
        return
    history = json.loads(HISTORY_FILE.read_text(encoding="utf-8-sig"))
    print(f"\n  {'Test':<14} {'Runs':>5}  {'Latest P95':>11}  {'Score':>6}  Grade")
    print(f"  {_sep('-', 52)}")
    for tt in RUN_SEQUENCE:
        runs = [r for r in history.get(tt, []) if isinstance(r, dict)]
        if not runs:
            print(f"  {tt:<14} {'0':>5}  {'—':>11}  {'—':>6}  —")
            continue
        lat   = runs[-1]
        p95   = f"{lat['p95_ms']:.0f} ms" if lat.get("p95_ms") else "—"
        score = str(lat.get("release_score", "—"))
        grade = lat.get("grade", "—")
        gc    = {"A": _C.GREEN, "B": _C.GREEN, "C": _C.YELLOW, "F": _C.RED}.get(grade, _C.WHITE)
        print(f"  {tt:<14} {len(runs):>5}  {p95:>11}  {score:>5}/100  {_c(gc, grade)}")
    print()


def show_baseline() -> None:
    if not BASELINE_FILE.exists():
        print("baseline.json not found.")
        return
    data = json.loads(BASELINE_FILE.read_text(encoding="utf-8-sig"))
    print(f"\n  {'Test':<14} {'P95 Baseline':>14}  {'VUs':>10}")
    print(f"  {_sep('-', 44)}")
    for tt in RUN_SEQUENCE:
        entry = data.get(tt, {})
        p95   = entry.get("p95")
        vus   = str(entry.get("vus", "—"))
        p95_s = f"{p95} ms" if p95 is not None else _c(_C.YELLOW, "not set")
        print(f"  {tt:<14} {p95_s:>14}  {vus:>10}")
    print()


def show_status() -> None:
    healthy, p95, err = health_check()
    show_history()
    show_baseline()


# ---------------------------------------------------------------------------
# Interactive menu
# ---------------------------------------------------------------------------

def _menu_header() -> None:
    print(f"\n{_sep()}")
    print(f"  {_c(_C.BOLD + _C.CYAN, 'AUTOROX PERFORMANCE AGENT')}")
    print(_sep("-"))

    # Quick score summary from history
    if HISTORY_FILE.exists():
        try:
            history = json.loads(HISTORY_FILE.read_text(encoding="utf-8-sig"))
            parts = []
            for tt in RUN_SEQUENCE:
                runs = [r for r in history.get(tt, []) if isinstance(r, dict)]
                if runs:
                    g = runs[-1].get("grade", "?")
                    gc = {"A": _C.GREEN, "B": _C.GREEN, "C": _C.YELLOW, "F": _C.RED}.get(g, _C.WHITE)
                    parts.append(f"{tt[0].upper()}:{_c(gc, g)}")
            if parts:
                print(f"  Scores: {' '.join(parts)}")
        except Exception:
            pass

    print()


def interactive_menu() -> None:
    while True:
        _menu_header()
        print(f"  {_c(_C.BOLD, 'TESTS')}")
        for i, tt in enumerate(RUN_SEQUENCE, 1):
            cfg   = TESTS[tt]
            heavy = _c(_C.YELLOW, " *heavy*") if cfg["heavy"] else ""
            print(f"  {i}.  {cfg['label']:<14} {cfg['vus']:>10} VUs   {cfg['duration']}{heavy}")
        print(f"  7.  Breakpoint      100->2000 VUs  auto-stop  {_c(_C.YELLOW, '*heavy*')}")
        print(f"  8.  Run ALL\n")
        print(f"  {_c(_C.BOLD, 'TOOLS')}")
        print(f"  9.  Server health check")
        print(f"  10. AI reports")
        print(f"  11. Configuration advisor")
        print(f"  12. Run history")
        print(f"  13. Show baselines")
        print(f"\n  0.  Exit\n")

        choice = input("  Select: ").strip()

        if choice == "0":
            print("Bye.")
            break

        elif choice in ("1","2","3","4","5","6"):
            run_test(RUN_SEQUENCE[int(choice) - 1])

        elif choice == "7":
            confirm = input(_c(_C.YELLOW, "  Breakpoint test will push server to failure. Continue? [y/N]: ")).strip().lower()
            if confirm == "y":
                run_test("breakpoint")

        elif choice == "8":
            confirm = input(_c(_C.YELLOW, "  Run ALL tests? (~80 min total) [y/N]: ")).strip().lower()
            if confirm == "y":
                run_all()

        elif choice == "9":
            health_check()

        elif choice == "10":
            tt_input = input("  Test type (blank = all): ").strip() or None
            if tt_input and tt_input not in TESTS:
                print(_c(_C.YELLOW, f"  Unknown test type: {tt_input}"))
            else:
                show_report(tt_input)

        elif choice == "11":
            import suggest_config as sc
            importlib.reload(sc)
            _call_suggest(sc)

        elif choice == "12":
            show_history()

        elif choice == "13":
            show_baseline()

        else:
            print(_c(_C.YELLOW, "  Invalid choice — enter a number from the menu."))


def _call_suggest(sc) -> None:
    """Call suggest_config internals directly (avoids argparse conflict)."""
    history = sc.load_history()
    has_data = any(isinstance(v, list) and v for v in history.values())
    if not has_data:
        print("No run history yet. Run some tests first.")
        return
    print(f"\n{'='*52}")
    print("  INTELLIGENT LOAD CONFIGURATION ADVISOR")
    print(f"{'='*52}")
    for tt in sc.TEST_ORDER:
        runs = history.get(tt, [])
        if isinstance(runs, list):
            sc.analyse(tt, runs)
    sc.bottleneck_report(history)
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    if len(sys.argv) == 1:
        interactive_menu()
        return

    parser = argparse.ArgumentParser(
        prog="perf_agent",
        description="Autorox Performance Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python perf_agent.py run smoke\n"
            "  python perf_agent.py run all\n"
            "  python perf_agent.py status\n"
            "  python perf_agent.py report load\n"
            "  python perf_agent.py history\n"
        ),
    )
    sub = parser.add_subparsers(dest="cmd", metavar="command")

    p = sub.add_parser("run",      help="Run a test: smoke|load|stress|spike|soak|scalability|breakpoint|all")
    p.add_argument("test", choices=list(TESTS.keys()) + ["all"])

    sub.add_parser("status",   help="Server health check")
    sub.add_parser("suggest",  help="Load configuration advisor")
    sub.add_parser("history",  help="Run history summary")
    sub.add_parser("baseline", help="Show current baselines")

    p = sub.add_parser("report", help="Show last AI analysis report")
    p.add_argument("test", nargs="?", choices=list(TESTS.keys()), default=None)

    args = parser.parse_args()

    if args.cmd == "run":
        if args.test == "all":
            run_all()
        else:
            sys.exit(run_test(args.test))

    elif args.cmd == "status":
        healthy, _, _ = health_check()
        sys.exit(0 if healthy else 1)

    elif args.cmd == "report":
        show_report(getattr(args, "test", None))

    elif args.cmd == "suggest":
        import suggest_config as sc
        _call_suggest(sc)

    elif args.cmd == "history":
        show_history()

    elif args.cmd == "baseline":
        show_baseline()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
