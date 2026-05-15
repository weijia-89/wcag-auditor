from __future__ import annotations

import json
from pathlib import Path

import pytest

from wcag_auditor.models import (
    AuditResult,
    ImpactLevel,
    ViolationInput,
)
from wcag_auditor.fix_engine import RuleEngine
from wcag_auditor.eval_metrics import (
    SchemaComplianceMetric,
)

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_GOLDEN_DATASET_PATH = _PROJECT_ROOT / "tests" / "fixtures" / "golden_dataset.json"
_BASELINE_PATH = _PROJECT_ROOT / "eval_baseline.json"


# Warn loudly at import time if eval_baseline.json is all-zeros — contributors
# need to notice that the regression gate is currently a no-op.
def _warn_if_baseline_all_zeros() -> None:
    try:
        data = json.loads(_BASELINE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    numeric_values = [v for k, v in data.items() if not k.startswith("_") and isinstance(v, (int, float))]
    if numeric_values and all(v == 0.0 for v in numeric_values):
        import sys
        print(
            "WARNING: eval_baseline.json is all-zeros — the regression gate is a "
            "no-op until real baseline numbers are committed. Run `make eval-full`.",
            file=sys.stderr,
        )


_warn_if_baseline_all_zeros()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_result_from_violation(violation: ViolationInput, file_path: str) -> AuditResult:
    """Generate a deterministic AuditResult from a ViolationInput using RuleEngine."""
    client = RuleEngine()
    return client.generate_fix(violation, html_context="", file_path=file_path)


def _violation_from_golden_expected(expected: dict, fixture_id: str) -> ViolationInput:
    """Construct a ViolationInput from a golden dataset expected violation entry."""
    return ViolationInput(
        id=expected["id"],
        description=f"Violation for {expected['id']}",
        help_url=f"https://dequeuniversity.com/rules/axe/4.9/{expected['id']}",
        impact=ImpactLevel(expected["impact"]),
        nodes=[{"html": f"<element class='{fixture_id}'>"}],
        wcag_criterion=expected["wcag_criterion"],
    )


# ---------------------------------------------------------------------------
# TestGoldenDatasetIntegrity — must ALL PASS Day 1
# ---------------------------------------------------------------------------

class TestGoldenDatasetIntegrity:
    """Validate the golden dataset is internally consistent and complete.

    All tests in this class MUST pass on Day 1. They do not require Ollama or
    a browser — they only validate the fixture data itself.
    """

    def test_golden_dataset_exists(self) -> None:
        assert _GOLDEN_DATASET_PATH.exists(), (
            f"Golden dataset not found at {_GOLDEN_DATASET_PATH}"
        )

    def test_golden_dataset_is_valid_json(self) -> None:
        data = json.loads(_GOLDEN_DATASET_PATH.read_text(encoding="utf-8"))
        assert isinstance(data, list), "golden_dataset.json must be a JSON array"

    def test_golden_dataset_has_six_records(self, golden_dataset: list[dict]) -> None:
        assert len(golden_dataset) == 6, (
            f"Expected 6 records in golden dataset, got {len(golden_dataset)}"
        )

    def test_each_record_has_required_keys(self, golden_dataset: list[dict]) -> None:
        required_keys = {
            "fixture_id",
            "html_file",
            "axe_expected_violations",
            "expected_fixes",
            "negative_wcag_criteria",
        }
        for record in golden_dataset:
            missing = required_keys - set(record.keys())
            assert not missing, (
                f"Record {record.get('fixture_id', '?')} missing keys: {missing}"
            )

    def test_html_fixture_files_exist(self, golden_dataset: list[dict], project_root: Path) -> None:
        for record in golden_dataset:
            html_path = project_root / record["html_file"]
            assert html_path.exists(), (
                f"HTML fixture file not found: {html_path} (fixture_id={record['fixture_id']})"
            )

    def test_expected_violations_have_required_fields(self, golden_dataset: list[dict]) -> None:
        required_violation_keys = {"id", "impact", "wcag_criterion", "nodes_count"}
        for record in golden_dataset:
            for v in record["axe_expected_violations"]:
                missing = required_violation_keys - set(v.keys())
                assert not missing, (
                    f"Violation in {record['fixture_id']} missing keys: {missing}"
                )

    def test_expected_violations_have_valid_impact(self, golden_dataset: list[dict]) -> None:
        valid_impacts = {level.value for level in ImpactLevel}
        for record in golden_dataset:
            for v in record["axe_expected_violations"]:
                assert v["impact"] in valid_impacts, (
                    f"Invalid impact '{v['impact']}' in {record['fixture_id']}"
                )

    def test_negative_wcag_criteria_are_non_empty(self, golden_dataset: list[dict]) -> None:
        for record in golden_dataset:
            assert len(record["negative_wcag_criteria"]) > 0, (
                f"Record {record['fixture_id']} has empty negative_wcag_criteria"
            )

    def test_negative_criteria_not_in_expected_violations(self, golden_dataset: list[dict]) -> None:
        """Negative criteria must not overlap with criteria expected to be flagged."""
        for record in golden_dataset:
            expected_criteria = {
                v["wcag_criterion"]
                for v in record["axe_expected_violations"]
            }
            negatives = set(record["negative_wcag_criteria"])
            overlap = expected_criteria & negatives
            assert not overlap, (
                f"Record {record['fixture_id']}: criteria appear in both expected and negative sets: {overlap}"
            )

    def test_expected_fixes_have_required_fields(self, golden_dataset: list[dict]) -> None:
        required_fix_keys = {"element_selector", "fix_html", "wcag_criterion", "impact"}
        for record in golden_dataset:
            for fx in record["expected_fixes"]:
                missing = required_fix_keys - set(fx.keys())
                assert not missing, (
                    f"Fix in {record['fixture_id']} missing keys: {missing}"
                )


# ---------------------------------------------------------------------------
# TestBaselineMetricsFile — must PASS Day 1
# ---------------------------------------------------------------------------

class TestBaselineMetricsFile:
    """Validate that eval_baseline.json exists and has the correct structure."""

    def test_baseline_file_exists(self) -> None:
        assert _BASELINE_PATH.exists(), f"Baseline file not found at {_BASELINE_PATH}"

    def test_baseline_is_valid_json(self) -> None:
        data = json.loads(_BASELINE_PATH.read_text(encoding="utf-8"))
        assert isinstance(data, dict)

    def test_baseline_has_required_metric_keys(self) -> None:
        data = json.loads(_BASELINE_PATH.read_text(encoding="utf-8"))
        required_keys = {
            "schema_compliance_rate",
            "criterion_accuracy",
            "fix_applicability",
            "hallucination_rate",
            "false_negative_rate",
            "impact_level_accuracy",
        }
        missing = required_keys - set(data.keys())
        assert not missing, f"Baseline missing metric keys: {missing}"

    def test_baseline_metric_values_are_numeric(self) -> None:
        data = json.loads(_BASELINE_PATH.read_text(encoding="utf-8"))
        numeric_keys = [
            "schema_compliance_rate",
            "criterion_accuracy",
            "fix_applicability",
            "hallucination_rate",
            "false_negative_rate",
            "impact_level_accuracy",
        ]
        for key in numeric_keys:
            assert isinstance(data[key], (int, float)), (
                f"Baseline key '{key}' must be numeric, got {type(data[key])}"
            )

    def test_baseline_has_ci_note(self) -> None:
        data = json.loads(_BASELINE_PATH.read_text(encoding="utf-8"))
        assert "_ci_note" in data, "Baseline should have _ci_note explaining CI scope"


# ---------------------------------------------------------------------------
# TestApplicationContract — Day 1: mock-mode schema tests pass
#                          Sessions 2-4: real LLM tests xfail until implemented
# ---------------------------------------------------------------------------

class TestApplicationContract:
    """Contract tests for the audit pipeline.

    Schema compliance tests run with WCAG_MOCK_AXE=1 and must pass Day 1.
    LLM-quality tests (criterion accuracy, hallucination, fix applicability)
    are xfail until Sessions 2-4 implement the full eval loop.
    """

    def _generate_mock_results(self, golden_dataset: list[dict], project_root: Path) -> list[AuditResult]:
        """Use RuleEngine to generate AuditResult for each expected violation in the dataset."""
        results = []
        for record in golden_dataset:
            for expected_v in record["axe_expected_violations"]:
                violation = _violation_from_golden_expected(expected_v, record["fixture_id"])
                result = _make_result_from_violation(
                    violation,
                    file_path=str(project_root / record["html_file"]),
                )
                results.append(result)
        return results

    def test_schema_compliance_mock_mode(
        self, golden_dataset: list[dict], project_root: Path
    ) -> None:
        """RuleEngine output must be 100% schema-compliant. Runs in CI (WCAG_MOCK_AXE=1)."""
        results = self._generate_mock_results(golden_dataset, project_root)
        assert len(results) > 0, "Expected at least one result from golden dataset"

        metric = SchemaComplianceMetric()
        metric_result = metric.evaluate(results)

        assert metric_result.passed, (
            f"Schema compliance failed: {metric_result.reason}\n"
            f"Score: {metric_result.score:.2f}"
        )
        assert metric_result.score == 1.0, (
            f"RuleEngine must achieve 100% schema compliance, got {metric_result.score:.2f}"
        )

    def test_mock_results_have_non_empty_fixes(
        self, golden_dataset: list[dict], project_root: Path
    ) -> None:
        """RuleEngine must generate at least one fix per violation."""
        results = self._generate_mock_results(golden_dataset, project_root)

        for result in results:
            assert len(result.fixes) >= 1, (
                f"rule_id={result.rule_id}: RuleEngine returned no fixes"
            )

    def test_mock_results_confidence_in_range(
        self, golden_dataset: list[dict], project_root: Path
    ) -> None:
        """RuleEngine confidence scores must be in [0, 1]."""
        results = self._generate_mock_results(golden_dataset, project_root)

        for result in results:
            assert 0.0 <= result.confidence_score <= 1.0, (
                f"rule_id={result.rule_id}: confidence_score {result.confidence_score} out of range"
            )

    def test_mock_results_wcag_criterion_non_empty(
        self, golden_dataset: list[dict], project_root: Path
    ) -> None:
        """RuleEngine must populate wcag_criterion (may be 'unknown' but not empty)."""
        results = self._generate_mock_results(golden_dataset, project_root)

        for result in results:
            assert result.wcag_criterion, (
                f"rule_id={result.rule_id}: wcag_criterion is empty"
            )

    @pytest.mark.xfail(
        reason="Criterion accuracy requires real Ollama eval — Sessions 2-4. Run: make eval-full",
        strict=False,
    )
    def test_criterion_accuracy_real_llm(
        self, golden_dataset: list[dict], mock_llm_active: bool
    ) -> None:
        """Real LLM criterion accuracy must meet threshold. Requires make eval-full."""
        if mock_llm_active:
            pytest.skip("WCAG_MOCK_AXE=1 — skipping real LLM criterion accuracy test")

        # This test requires a running Ollama instance and will be implemented in Session 2.
        pytest.fail("Not yet implemented — complete in Session 2")

    @pytest.mark.xfail(
        reason="Hallucination check on real LLM output requires Sessions 2-4. Run: make eval-full",
        strict=False,
    )
    def test_hallucination_rate_real_llm(
        self, golden_dataset: list[dict], mock_llm_active: bool
    ) -> None:
        """Real LLM hallucination rate must meet threshold. Requires make eval-full."""
        if mock_llm_active:
            pytest.skip("WCAG_MOCK_AXE=1 — skipping real LLM hallucination test")

        pytest.fail("Not yet implemented — complete in Session 3")

    @pytest.mark.xfail(
        reason="Fix applicability requires Playwright + real axe — Sessions 2-4. Run: make eval-full",
        strict=False,
    )
    def test_fix_accuracy_real_llm(
        self, golden_dataset: list[dict], mock_llm_active: bool
    ) -> None:
        """Real LLM fix applicability must meet threshold. Requires make eval-full."""
        if mock_llm_active:
            pytest.skip("WCAG_MOCK_AXE=1 — skipping fix applicability test")

        pytest.fail("Not yet implemented — complete in Session 4")
