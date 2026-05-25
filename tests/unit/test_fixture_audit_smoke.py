"""End-to-end smoke: axe-core scan + RuleEngine on a curated HTML fixture.

Requires Playwright Chromium and axe.min.js (make install / make download-axe).
No outbound LLM calls — violations come from bundled axe; fixes from RuleEngine.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.unit._golden_image_alt import GOLDEN_FIX_HTML, GOLDEN_RESULT_EXPLANATION
from wcag_auditor.auditor import Auditor
from wcag_auditor.axe_runner import AXE_JS_PATH
from wcag_auditor.fix_engine import RuleEngine

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_FIXTURE = "tests/fixtures/html/missing_alt_001.html"

def _axe_bundle_ready() -> bool:
    if not AXE_JS_PATH.exists():
        return False
    content = AXE_JS_PATH.read_text(encoding="utf-8", errors="replace")
    return "axe-core placeholder" not in content


@pytest.fixture
def project_root() -> Path:
    return _PROJECT_ROOT


class TestFixtureAuditSmoke:
    def test_missing_alt_fixture_end_to_end(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, project_root: Path
    ) -> None:
        pytest.importorskip("playwright")

        if not _axe_bundle_ready():
            # Fail closed: CI must install axe before this smoke gate can pass.
            pytest.fail(
                "axe.min.js not installed — run: make download-axe "
                "(or uv run python scripts/download_axe.py)"
            )

        monkeypatch.chdir(project_root)
        monkeypatch.setenv("WCAG_NO_SANDBOX", "1")
        monkeypatch.setenv("WCAG_DB_PATH", str(tmp_path / "test.db"))

        report = Auditor(fix_engine=RuleEngine()).audit(_FIXTURE, save=False)

        assert report.total_violations >= 1
        image_alt = [r for r in report.results if r.rule_id == "image-alt"]
        assert image_alt, "expected at least one image-alt violation from fixture"

        result = image_alt[0]
        assert result.explanation == GOLDEN_RESULT_EXPLANATION
        assert result.confidence_score == 0.95
        assert len(result.fixes) == 1
        assert result.fixes[0].fix_html == GOLDEN_FIX_HTML
        assert result.fixes[0].element_selector == "img"
