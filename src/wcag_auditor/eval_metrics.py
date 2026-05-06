from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from wcag_auditor.models import AuditResult, ImpactLevel


@dataclass
class MetricResult:
    name: str
    score: float
    passed: bool
    reason: str


class SchemaComplianceMetric:
    """Validate that AuditResult objects parse and obey their schema.

    Score = (results_with_no_failure / total). Empty result list scores 1.0
    (trivially compliant) so a clean run on a clean page doesn't fail the gate.
    """

    def evaluate(self, results: list[AuditResult], threshold: float = 1.0) -> MetricResult:
        if not results:
            return MetricResult(
                name="schema_compliance",
                score=1.0,
                passed=True,
                reason="No results to evaluate.",
            )

        failures: list[str] = []
        for r in results:
            if not isinstance(r, AuditResult):
                failures.append(f"Result is not AuditResult: {type(r)}")
                continue
            if not (0.0 <= r.confidence_score <= 1.0):
                failures.append(f"rule_id={r.rule_id}: confidence_score out of range: {r.confidence_score}")
            if not isinstance(r.fixes, list):
                failures.append(f"rule_id={r.rule_id}: fixes is not a list")
            if not r.wcag_criterion:
                failures.append(f"rule_id={r.rule_id}: wcag_criterion is empty")
            try:
                ImpactLevel(r.impact)
            except ValueError:
                failures.append(f"rule_id={r.rule_id}: invalid impact: {r.impact}")

        score = (len(results) - len(failures)) / len(results)
        reason = f"{len(results) - len(failures)}/{len(results)} results passed schema validation."
        if failures:
            reason += f" Failures: {'; '.join(failures[:5])}"

        return MetricResult(
            name="schema_compliance",
            score=score,
            passed=score >= threshold,
            reason=reason,
        )


class CriterionAccuracyMetric:
    """How often result.wcag_criterion equals the golden expected criterion."""

    def evaluate(
        self,
        results: list[AuditResult],
        expected_criteria: list[str],
        threshold: float = 0.8,
    ) -> MetricResult:
        if not results:
            return MetricResult(
                name="criterion_accuracy",
                score=0.0,
                passed=False,
                reason="No results to evaluate.",
            )

        matched = sum(
            1 for r, exp in zip(results, expected_criteria) if r.wcag_criterion == exp
        )
        score = matched / len(results)
        return MetricResult(
            name="criterion_accuracy",
            score=score,
            passed=score >= threshold,
            reason=f"{matched}/{len(results)} WCAG criteria matched expected values.",
        )


class ImpactAccuracyMetric:
    """Same shape as CriterionAccuracyMetric but for impact level."""

    def evaluate(
        self,
        results: list[AuditResult],
        expected_impacts: list[str],
        threshold: float = 0.8,
    ) -> MetricResult:
        if not results:
            return MetricResult(
                name="impact_accuracy",
                score=0.0,
                passed=False,
                reason="No results to evaluate.",
            )

        matched = sum(
            1 for r, exp in zip(results, expected_impacts) if r.impact.value == exp
        )
        score = matched / len(results)
        return MetricResult(
            name="impact_accuracy",
            score=score,
            passed=score >= threshold,
            reason=f"{matched}/{len(results)} impact levels matched expected values.",
        )


class HallucinationMetric:
    """Structural hallucination check, no LLM-as-judge.

    For every result and every fix, check that its ``wcag_criterion`` is NOT
    in the dataset's ``negative_criteria`` list. Score is 1 - (bad / total).
    """

    def evaluate(
        self,
        results: list[AuditResult],
        negative_criteria: list[str],
        threshold: float = 0.95,
    ) -> MetricResult:
        if not results:
            return MetricResult(
                name="hallucination",
                score=1.0,
                passed=True,
                reason="No results to evaluate.",
            )

        total_checks = 0
        hallucinations: list[str] = []

        for r in results:
            total_checks += 1
            if r.wcag_criterion in negative_criteria:
                hallucinations.append(
                    f"rule_id={r.rule_id}: result criterion {r.wcag_criterion!r} is in negative list"
                )
            for fix in r.fixes:
                total_checks += 1
                if fix.wcag_criterion in negative_criteria:
                    hallucinations.append(
                        f"rule_id={r.rule_id}: fix criterion {fix.wcag_criterion!r} is in negative list"
                    )

        score = (total_checks - len(hallucinations)) / total_checks if total_checks else 1.0
        reason = f"{total_checks - len(hallucinations)}/{total_checks} criterion references are non-hallucinated."
        if hallucinations:
            reason += f" Hallucinations: {'; '.join(hallucinations[:3])}"

        return MetricResult(
            name="hallucination",
            score=score,
            passed=score >= threshold,
            reason=reason,
        )


class FixApplicabilityMetric:
    """Apply a fix, re-run axe, and check the original violation is gone.

    DANGER: launches a browser and writes temp HTML. Never call on untrusted
    HTML. The patched page is served to Chromium with full DOM execution.
    """

    def evaluate_one(self, original_html: str, result: AuditResult) -> bool:
        from playwright.sync_api import sync_playwright

        from wcag_auditor.axe_runner import run_axe

        if not result.fixes:
            return False

        fix = result.fixes[0]
        # Naive substitution. If the LLM hallucinated original_html the
        # `in` check fails and we report unverifiable rather than guessing.
        if fix.original_html and fix.original_html in original_html:
            patched_html = original_html.replace(fix.original_html, fix.fix_html, 1)
        else:
            return False

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".html",
            delete=False,
            encoding="utf-8",
            dir=Path.cwd(),
        ) as f:
            f.write(patched_html)
            temp_path = f.name

        try:
            with sync_playwright() as p:
                launch_args = ["--disable-dev-shm-usage"]
                if os.environ.get("WCAG_NO_SANDBOX") == "1":
                    launch_args.insert(0, "--no-sandbox")
                browser = p.chromium.launch(args=launch_args)
                try:
                    page = browser.new_page()
                    violations = run_axe(page, temp_path)
                finally:
                    browser.close()

            return result.rule_id not in {v.id for v in violations}
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def evaluate(
        self,
        html_files: list[str],
        results: list[AuditResult],
        threshold: float = 0.7,
    ) -> MetricResult:
        if not results:
            return MetricResult(
                name="fix_applicability",
                score=0.0,
                passed=False,
                reason="No results to evaluate.",
            )

        passed_count = 0
        for html_path, result in zip(html_files, results):
            try:
                html = Path(html_path).read_text(encoding="utf-8")
                if self.evaluate_one(html, result):
                    passed_count += 1
            except Exception:  # noqa: BLE001
                # Read errors / browser launch failures count as "fix not
                # verified" rather than aborting the whole metric run.
                pass

        score = passed_count / len(results)
        return MetricResult(
            name="fix_applicability",
            score=score,
            passed=score >= threshold,
            reason=f"{passed_count}/{len(results)} fixes verified to resolve violations.",
        )
