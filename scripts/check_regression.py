#!/usr/bin/env python3
"""Regression gate. Compare eval scores against eval_baseline.json and fail if any
metric dropped by more than ``--max-drop``.

    uv run python scripts/check_regression.py \\
        --results eval_results.json \\
        --baseline eval_baseline.json \\
        --max-drop 0.05
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Metric keys we know about. pytest-json-report stores user_properties as
# [["metric_name", score], ...] on each test; we average across all tests
# that publish the same metric.
_METRIC_MAP: dict[str, str] = {
    "schema_compliance_rate": "schema_compliance_rate",
    "criterion_accuracy": "criterion_accuracy",
    "fix_applicability": "fix_applicability",
    "hallucination_rate": "hallucination_rate",
    "false_negative_rate": "false_negative_rate",
    "impact_level_accuracy": "impact_level_accuracy",
}

# CI runs MOCK_LLM=1, no Ollama. Anything else we'd be checking is meaningless
# under mock and would either be 1.0 or 0.0 garbage. Only this one survives.
_CI_SAFE_METRICS: set[str] = {"schema_compliance_rate"}


def _extract_metrics_from_report(results_path: Path) -> dict[str, float]:
    data = json.loads(results_path.read_text(encoding="utf-8"))
    metrics: dict[str, list[float]] = {}

    for test in data.get("tests", []):
        for prop in test.get("user_properties", []):
            if isinstance(prop, (list, tuple)) and len(prop) == 2:
                key, value = prop
                if key in _METRIC_MAP and isinstance(value, (int, float)):
                    metrics.setdefault(key, []).append(float(value))

    return {k: sum(v) / len(v) for k, v in metrics.items()}


def _load_baseline(baseline_path: Path) -> dict[str, float]:
    data = json.loads(baseline_path.read_text(encoding="utf-8"))
    return {
        k: float(v)
        for k, v in data.items()
        if not k.startswith("_") and isinstance(v, (int, float))
    }


def _print_diff_table(
    baseline: dict[str, float],
    current: dict[str, float],
    max_drop: float,
    regressions: list[str],
) -> None:
    col_w = [30, 12, 12, 10, 12]
    header = (
        f"{'Metric':<{col_w[0]}} {'Baseline':>{col_w[1]}} "
        f"{'Current':>{col_w[2]}} {'Delta':>{col_w[3]}} {'Status':>{col_w[4]}}"
    )
    sep = "-" * sum(col_w + [4 * 2])

    print("\n" + sep)
    print(header)
    print(sep)

    for key in sorted(set(baseline) | set(current)):
        if key.startswith("_"):
            continue
        b = baseline.get(key, 0.0)
        c = current.get(key)

        if c is None:
            delta_str = "N/A"
            status = "SKIP"
        else:
            delta = c - b
            delta_str = f"{delta:+.3f}"
            if key in regressions:
                status = "FAIL"
            elif delta < 0:
                status = "WARN"
            else:
                status = "OK"

        c_str = f"{c:.3f}" if c is not None else "N/A"
        print(
            f"{key:<{col_w[0]}} {b:>{col_w[1]}.3f} {c_str:>{col_w[2]}} "
            f"{delta_str:>{col_w[3]}} {status:>{col_w[4]}}"
        )

    print(sep)
    print(f"Max allowed drop: {max_drop:.3f}")
    if regressions:
        print(f"\nREGRESSIONS DETECTED ({len(regressions)}): {', '.join(regressions)}")
    else:
        print("\nNo regressions detected.")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="WCAG Auditor regression gate."
    )
    parser.add_argument("--results", required=True, type=Path,
                        help="Path to pytest-json-report output JSON")
    parser.add_argument("--baseline", required=True, type=Path,
                        help="Path to eval_baseline.json")
    parser.add_argument("--max-drop", type=float, default=0.05,
                        help="Allowed drop before regression fires (default: 0.05)")
    parser.add_argument("--ci", action="store_true",
                        help="CI mode: only check MOCK_LLM-compatible metrics")
    parser.add_argument(
        "--accept-zero-baseline",
        action="store_true",
        help=(
            "Allow the gate to run when every baseline metric is 0.0. "
            "Without this flag, an all-zero baseline is rejected as 'never established'."
        ),
    )
    args = parser.parse_args()

    if not args.results.exists():
        print(f"ERROR: Results file not found: {args.results}", file=sys.stderr)
        sys.exit(2)

    if not args.baseline.exists():
        print(f"ERROR: Baseline file not found: {args.baseline}", file=sys.stderr)
        sys.exit(2)

    baseline = _load_baseline(args.baseline)
    current = _extract_metrics_from_report(args.results)

    if args.ci:
        baseline = {k: v for k, v in baseline.items() if k in _CI_SAFE_METRICS}
        current = {k: v for k, v in current.items() if k in _CI_SAFE_METRICS}

    # B1: an all-zero baseline always passes (drop = 0 - current <= 0). That
    # means the gate exists but cannot fail. Exactly the kind of vibe-safe
    # check we don't want. Refuse unless caller explicitly opts in.
    if baseline and all(v == 0.0 for v in baseline.values()) and not args.accept_zero_baseline:
        print(
            "ERROR: baseline never established. Every metric in "
            f"{args.baseline} is 0.0. Run `make eval-full` and commit real "
            "baseline numbers, or pass `--accept-zero-baseline` to opt in.",
            file=sys.stderr,
        )
        sys.exit(2)

    regressions: list[str] = []
    for key, base_score in baseline.items():
        if key.startswith("_") or key not in current:
            continue
        if base_score - current[key] > args.max_drop:
            regressions.append(key)

    _print_diff_table(baseline, current, args.max_drop, regressions)

    if regressions:
        print(
            f"FAIL: {len(regressions)} metric(s) regressed beyond threshold of {args.max_drop:.3f}",
            file=sys.stderr,
        )
        sys.exit(1)
    print("PASS: All metrics within acceptable range.")


if __name__ == "__main__":
    main()
