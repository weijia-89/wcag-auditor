"""Golden regression for deterministic RuleEngine template output.

No network, no Playwright, no LLM — locks the image-alt fix shape so template
drift fails CI before it reaches consumers.
"""
from __future__ import annotations

from tests.unit._golden_image_alt import (
    GOLDEN_FIX_EXPLANATION,
    GOLDEN_FIX_HTML,
    GOLDEN_RESULT_EXPLANATION,
)
from wcag_auditor.fix_engine import RuleEngine
from wcag_auditor.models import ImpactLevel, ViolationInput

# Stable ViolationInput mirroring missing_alt_001.html's first image-alt node.
_MISSING_ALT_VIOLATION = ViolationInput(
    id="image-alt",
    description="Images must have alternate text",
    help_url="https://dequeuniversity.com/rules/axe/4.10/image-alt",
    impact=ImpactLevel.CRITICAL,
    nodes=[{"html": "<img src=\"logo.png\">"}],
    wcag_criterion="1.1.1",
)

class TestImageAltTemplateRegression:
    def test_image_alt_fix_html_is_stable(self) -> None:
        result = RuleEngine().generate_fix(
            _MISSING_ALT_VIOLATION,
            html_context="",
            file_path="tests/fixtures/html/missing_alt_001.html",
        )

        assert result.rule_id == "image-alt"
        assert result.wcag_criterion == "1.1.1"
        assert result.impact == ImpactLevel.CRITICAL
        assert result.confidence_score == 0.95
        assert result.explanation == GOLDEN_RESULT_EXPLANATION
        assert len(result.fixes) == 1

        fix = result.fixes[0]
        assert fix.element_selector == "img"
        assert fix.fix_html == GOLDEN_FIX_HTML
        assert fix.fix_explanation == GOLDEN_FIX_EXPLANATION
        assert fix.original_html == '<img src="logo.png">'

    def test_image_alt_output_is_byte_identical_on_repeat(self) -> None:
        engine = RuleEngine()
        first = engine.generate_fix(
            _MISSING_ALT_VIOLATION, "", "tests/fixtures/html/missing_alt_001.html"
        )
        second = engine.generate_fix(
            _MISSING_ALT_VIOLATION, "", "tests/fixtures/html/missing_alt_001.html"
        )
        assert first.model_dump() == second.model_dump()
