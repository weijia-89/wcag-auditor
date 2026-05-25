#!/usr/bin/env python3
"""Run full CI parity verify (sync, Playwright, axe, lint, unit+smoke).

Canonical SDK/orchestrator verify — not bare ``uv sync && ruff && pytest``.
Mirrors `.github/workflows/ci.yml` and `make verify-ci`.

    uv run python scripts/verify.py
    # or:
    make verify-ci

# sdk-review F1: orchestrator verify must run this script (Playwright + axe before pytest).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _run(cmd: list[str], *, env: dict[str, str] | None = None) -> None:
    print(f"+ {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True, env=env)


def main() -> None:
    _run(["uv", "sync", "--all-groups"])
    _run(["uv", "run", "playwright", "install", "chromium", "--with-deps"])
    _run(["uv", "run", "python", "scripts/download_axe.py"])
    _run(["uv", "run", "ruff", "check", "src/", "tests/"])

    test_env = os.environ.copy()
    test_env["WCAG_NO_SANDBOX"] = "1"
    # sdk-review F2: pytest flags match `.github/workflows/ci.yml` (no quiet/maxfail drift).
    _run(
        ["uv", "run", "pytest", "tests/unit/", "-v"],
        env=test_env,
    )


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        sys.exit(exc.returncode)
