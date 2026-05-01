from __future__ import annotations

import pytest
from pydantic import ValidationError

from wcag_auditor.models import (
    AuditReport,
    AuditResult,
    ImpactLevel,
    ViolationFix,
    ViolationInput,
)


class TestImpactLevel:
    # Values must mirror axe-core's strings exactly. That's the contract.

    def test_enum_values_match_axe_core_strings(self) -> None:
        assert ImpactLevel.CRITICAL.value == "critical"
        assert ImpactLevel.SERIOUS.value == "serious"
        assert ImpactLevel.MODERATE.value == "moderate"
        assert ImpactLevel.MINOR.value == "minor"

    def test_impact_level_from_string(self) -> None:
        assert ImpactLevel("critical") == ImpactLevel.CRITICAL
        assert ImpactLevel("minor") == ImpactLevel.MINOR

    def test_invalid_impact_raises(self) -> None:
        with pytest.raises(ValueError):
            ImpactLevel("invalid-impact")


class TestViolationInput:
    def test_parses_correctly(self) -> None:
        v = ViolationInput(
            id="image-alt",
            description="Images must have alternate text",
            help_url="https://dequeuniversity.com/rules/axe/4.9/image-alt",
            impact=ImpactLevel.CRITICAL,
            nodes=[{"html": "<img src='logo.png'>", "target": ["img"]}],
            wcag_criterion="1.1.1",
        )
        assert v.id == "image-alt"
        assert v.impact == ImpactLevel.CRITICAL
        assert v.wcag_criterion == "1.1.1"
        assert len(v.nodes) == 1

    def test_impact_coerces_from_string(self) -> None:
        v = ViolationInput(
            id="label",
            description="Form elements must have labels",
            help_url="https://dequeuniversity.com/rules/axe/4.9/label",
            impact="serious",  # type: ignore[arg-type]
            nodes=[],
            wcag_criterion="1.3.1",
        )
        assert v.impact == ImpactLevel.SERIOUS

    def test_invalid_impact_raises(self) -> None:
        with pytest.raises(ValidationError):
            ViolationInput(
                id="test",
                description="test",
                help_url="https://example.com",
                impact="not-a-level",  # type: ignore[arg-type]
                nodes=[],
                wcag_criterion="1.1.1",
            )


class TestAuditResult:
    def _make_fix(self) -> ViolationFix:
        return ViolationFix(
            element_selector="img",
            original_html="<img src='logo.png'>",
            fix_html="<img src='logo.png' alt='Company logo'>",
            fix_explanation="Add alt text",
            wcag_criterion="1.1.1",
            impact=ImpactLevel.CRITICAL,
        )

    def test_valid_confidence_score(self) -> None:
        result = AuditResult(
            file_path="test.html",
            wcag_criterion="1.1.1",
            rule_id="image-alt",
            impact=ImpactLevel.CRITICAL,
            fixes=[self._make_fix()],
            explanation="Images need alt text",
            confidence_score=0.95,
        )
        assert result.confidence_score == 0.95

    def test_confidence_score_zero(self) -> None:
        result = AuditResult(
            file_path="test.html",
            wcag_criterion="1.1.1",
            rule_id="image-alt",
            impact=ImpactLevel.CRITICAL,
            fixes=[],
            explanation="",
            confidence_score=0.0,
        )
        assert result.confidence_score == 0.0

    def test_confidence_score_one(self) -> None:
        result = AuditResult(
            file_path="test.html",
            wcag_criterion="1.1.1",
            rule_id="image-alt",
            impact=ImpactLevel.CRITICAL,
            fixes=[],
            explanation="",
            confidence_score=1.0,
        )
        assert result.confidence_score == 1.0

    def test_confidence_score_below_zero_raises(self) -> None:
        with pytest.raises(ValidationError):
            AuditResult(
                file_path="test.html",
                wcag_criterion="1.1.1",
                rule_id="image-alt",
                impact=ImpactLevel.CRITICAL,
                fixes=[],
                explanation="",
                confidence_score=-0.1,
            )

    def test_confidence_score_above_one_raises(self) -> None:
        with pytest.raises(ValidationError):
            AuditResult(
                file_path="test.html",
                wcag_criterion="1.1.1",
                rule_id="image-alt",
                impact=ImpactLevel.CRITICAL,
                fixes=[],
                explanation="",
                confidence_score=1.1,
            )


class TestAuditReportFromResults:
    def _make_result(self, rule_id: str, impact: ImpactLevel) -> AuditResult:
        return AuditResult(
            file_path="test.html",
            wcag_criterion="1.1.1",
            rule_id=rule_id,
            impact=impact,
            fixes=[],
            explanation="",
            confidence_score=0.8,
        )

    def test_counts_correctly(self) -> None:
        results = [
            self._make_result("image-alt", ImpactLevel.CRITICAL),
            self._make_result("image-alt-2", ImpactLevel.CRITICAL),
            self._make_result("label", ImpactLevel.SERIOUS),
            self._make_result("color-contrast", ImpactLevel.MODERATE),
            self._make_result("link-name", ImpactLevel.MINOR),
        ]
        report = AuditReport.from_results("test.html", results)

        assert report.total_violations == 5
        assert report.critical_count == 2
        assert report.serious_count == 1
        assert report.moderate_count == 1
        assert report.minor_count == 1
        assert report.scanned_path == "test.html"
        assert len(report.results) == 5

    def test_empty_results(self) -> None:
        report = AuditReport.from_results("test.html", [])

        assert report.total_violations == 0
        assert report.critical_count == 0
        assert report.serious_count == 0
        assert report.moderate_count == 0
        assert report.minor_count == 0
        assert report.results == []

    def test_timestamp_is_set(self) -> None:
        report = AuditReport.from_results("test.html", [])
        assert report.timestamp is not None
