# B1: regression gate must refuse to run on an all-zero baseline. Subprocess
# the real script so argparse + sys.exit are exercised end-to-end.
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_SCRIPT_PATH = _PROJECT_ROOT / "scripts" / "check_regression.py"


def _make_results_json(tmp_path: Path, metrics: dict[str, float]) -> Path:
    user_props = [[k, v] for k, v in metrics.items()]
    payload = {"tests": [{"user_properties": user_props}]}
    p = tmp_path / "results.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def _make_baseline(tmp_path: Path, values: dict[str, float]) -> Path:
    p = tmp_path / "baseline.json"
    p.write_text(json.dumps(values), encoding="utf-8")
    return p


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_SCRIPT_PATH), *args],
        capture_output=True,
        text=True,
    )


class TestZeroBaselineGate:

    def test_refuses_when_baseline_all_zeros(self, tmp_path: Path) -> None:
        baseline = _make_baseline(
            tmp_path,
            {
                "schema_compliance_rate": 0.0,
                "criterion_accuracy": 0.0,
                "fix_applicability": 0.0,
            },
        )
        results = _make_results_json(tmp_path, {"schema_compliance_rate": 1.0})

        proc = _run(
            [
                "--results", str(results),
                "--baseline", str(baseline),
            ]
        )

        assert proc.returncode == 2, (
            f"Expected exit 2 on all-zero baseline, got {proc.returncode}\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )
        assert "baseline never established" in proc.stderr

    def test_accept_zero_baseline_flag_lets_it_through(self, tmp_path: Path) -> None:
        baseline = _make_baseline(
            tmp_path,
            {
                "schema_compliance_rate": 0.0,
                "criterion_accuracy": 0.0,
            },
        )
        results = _make_results_json(tmp_path, {"schema_compliance_rate": 1.0})

        proc = _run(
            [
                "--results", str(results),
                "--baseline", str(baseline),
                "--accept-zero-baseline",
            ]
        )

        # With the opt-in flag, gate runs as before; should PASS (no regression).
        assert proc.returncode == 0, (
            f"Expected exit 0 with opt-in flag, got {proc.returncode}\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_real_baseline_runs_normally(self, tmp_path: Path) -> None:
        baseline = _make_baseline(
            tmp_path,
            {
                "schema_compliance_rate": 0.9,
                "criterion_accuracy": 0.85,
            },
        )
        results = _make_results_json(
            tmp_path,
            {
                "schema_compliance_rate": 0.92,
                "criterion_accuracy": 0.86,
            },
        )

        proc = _run(
            [
                "--results", str(results),
                "--baseline", str(baseline),
            ]
        )

        assert proc.returncode == 0, (
            f"Expected exit 0, got {proc.returncode}\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_real_baseline_detects_regression(self, tmp_path: Path) -> None:
        baseline = _make_baseline(
            tmp_path,
            {"schema_compliance_rate": 0.95},
        )
        results = _make_results_json(
            tmp_path,
            {"schema_compliance_rate": 0.50},
        )

        proc = _run(
            [
                "--results", str(results),
                "--baseline", str(baseline),
                "--max-drop", "0.05",
            ]
        )

        assert proc.returncode == 1, (
            f"Expected exit 1 on regression, got {proc.returncode}\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )
