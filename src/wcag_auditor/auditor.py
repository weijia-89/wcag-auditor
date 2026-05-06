from __future__ import annotations

import os
import sys
from pathlib import Path

from rich import print as rprint

from wcag_auditor.axe_runner import run_axe, run_axe_from_json
from wcag_auditor.database import save_report
from wcag_auditor.llm_client import LLMClientProtocol, _sanitize_html_for_prompt, get_client
from wcag_auditor.models import AuditReport, AuditResult, ViolationInput

# WCAG_LLM_BATCH_SIZE controls how many violations are processed per logical
# "batch" pass. The current implementation is still sequential — this env var
# establishes the interface so future async work can honour it without changing
# the call site. Default 0 means "process all violations in one batch" (no
# splitting). Set to a positive integer to log per-batch progress clearly.
_DEFAULT_BATCH_SIZE = 0


def _is_url(path_or_url: str) -> bool:
    return path_or_url.startswith(("http://", "https://"))


def _read_html_context(path_or_url: str) -> str:
    """First 3KB of the file, or empty string for URLs / unreadable files."""
    if _is_url(path_or_url):
        return ""
    try:
        return Path(path_or_url).read_text(encoding="utf-8", errors="replace")[:3000]
    except OSError:
        return ""


def _find_axe_sidecar(path_or_url: str) -> str | None:
    if _is_url(path_or_url):
        return None
    sidecar = Path(path_or_url).with_suffix(".axe.json")
    return str(sidecar) if sidecar.exists() else None


class Auditor:
    """Orchestrates axe-core scanning and LLM fix generation.

    Pass a custom ``llm_client`` to swap the LLM (for tests, alternate
    backends, or canary runs). The default falls through to ``get_client()``
    which honours the ``MOCK_LLM=1`` env var.
    """

    def __init__(
        self,
        llm_client: LLMClientProtocol | None = None,
        timeout_ms: int = 15_000,
    ) -> None:
        self._llm = llm_client if llm_client is not None else get_client()
        self._timeout_ms = timeout_ms

    def audit(self, path_or_url: str, save: bool = True) -> AuditReport:
        """Run a full audit on a file or URL and return the report.

        When MOCK_LLM=1 is set we skip Playwright entirely and look for a
        ``.axe.json`` sidecar next to the input. Missing sidecar in mock mode
        means an empty report (no errors); useful for the CI smoke path.
        """
        mock_mode = os.environ.get("MOCK_LLM") == "1"

        rprint(f"[bold blue]Auditing:[/bold blue] {path_or_url}", file=sys.stderr)

        if mock_mode:
            violations = self._get_violations_mock(path_or_url)
        else:
            violations = self._get_violations_real(path_or_url)

        rprint(f"[bold]Found {len(violations)} violation(s)[/bold]", file=sys.stderr)

        raw_html = _read_html_context(path_or_url)
        html_context = _sanitize_html_for_prompt(raw_html) if raw_html else ""
        results: list[AuditResult] = []

        batch_size = int(os.environ.get("WCAG_LLM_BATCH_SIZE", _DEFAULT_BATCH_SIZE))
        if batch_size > 0:
            rprint(
                f"[dim]  Batch size: {batch_size} (sequential; batching interface established)[/dim]",
                file=sys.stderr,
            )

        for i, violation in enumerate(violations, 1):
            rprint(
                f"  [{i}/{len(violations)}] Generating fix for [yellow]{violation.id}[/yellow]...",
                file=sys.stderr,
            )
            try:
                result = self._llm.generate_fix(violation, html_context, path_or_url)
                results.append(result)
            except Exception as exc:  # noqa: BLE001
                # One bad violation should not abort the whole audit. Log it,
                # drop the result, keep going. The report's total_violations
                # will be lower than len(violations) when this happens; that
                # is the signal something went wrong without breaking the run.
                rprint(
                    f"  [red]Warning:[/red] LLM fix failed for {violation.id}: {exc}",
                    file=sys.stderr,
                )

        report = AuditReport.from_results(path_or_url, results)

        if save:
            report_id = save_report(report)
            rprint(f"[green]Saved report #{report_id}[/green]", file=sys.stderr)

        return report

    def _get_violations_mock(self, path_or_url: str) -> list[ViolationInput]:
        sidecar = _find_axe_sidecar(path_or_url)
        if sidecar:
            rprint(f"[dim]  (MOCK_LLM=1) Loading axe sidecar: {sidecar}[/dim]", file=sys.stderr)
            return run_axe_from_json(sidecar)
        rprint(
            "[dim]  (MOCK_LLM=1) No .axe.json sidecar found; returning empty violations[/dim]",
            file=sys.stderr,
        )
        return []

    def _get_violations_real(self, path_or_url: str) -> list[ViolationInput]:
        # Local import: keeps the test suite from paying Playwright's import
        # cost, and lets MOCK_LLM=1 work on machines that don't have the
        # browser binary installed at all.
        from playwright.sync_api import sync_playwright

        # B9: --no-sandbox is opt-in. Default keeps the Chromium sandbox
        # because most users running this on a laptop are pointing it at
        # untrusted URLs. Docker / CI flips WCAG_NO_SANDBOX=1.
        launch_args = ["--disable-dev-shm-usage"]
        if os.environ.get("WCAG_NO_SANDBOX") == "1":
            launch_args.insert(0, "--no-sandbox")

        violations: list[ViolationInput] = []
        with sync_playwright() as p:
            browser = p.chromium.launch(args=launch_args)
            try:
                page = browser.new_page()
                violations = run_axe(page, path_or_url, timeout_ms=self._timeout_ms)
            finally:
                browser.close()

        return violations
