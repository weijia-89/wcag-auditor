from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from wcag_auditor.axe_runner import (
    _check_http_url_safe,
    _extract_wcag_criterion,
    _path_to_url,
    run_axe,
    run_axe_from_json,
)
from wcag_auditor.models import ImpactLevel


class TestExtractWcagCriterion:
    def test_wcag111(self) -> None:
        assert _extract_wcag_criterion(["wcag111"]) == "1.1.1"

    def test_wcag143(self) -> None:
        assert _extract_wcag_criterion(["wcag143"]) == "1.4.3"

    def test_wcag412(self) -> None:
        assert _extract_wcag_criterion(["wcag412"]) == "4.1.2"

    def test_wcag211(self) -> None:
        assert _extract_wcag_criterion(["wcag211"]) == "2.1.1"

    def test_wcag244(self) -> None:
        assert _extract_wcag_criterion(["wcag244"]) == "2.4.4"

    def test_best_practice_returns_unknown(self) -> None:
        assert _extract_wcag_criterion(["best-practice"]) == "unknown"

    def test_empty_tags_returns_unknown(self) -> None:
        assert _extract_wcag_criterion([]) == "unknown"

    def test_unrecognized_tag_returns_unknown(self) -> None:
        assert _extract_wcag_criterion(["cat", "section508"]) == "unknown"

    def test_picks_first_wcag_tag_from_mixed_list(self) -> None:
        # Should pick the first matching WCAG tag
        result = _extract_wcag_criterion(["best-practice", "wcag111", "wcag143"])
        assert result == "1.1.1"

    def test_wcag_with_extra_tags_ignored(self) -> None:
        assert _extract_wcag_criterion(["wcag2a", "wcag143", "cat.text-alternatives"]) == "1.4.3"


class TestRunAxeFromJson:
    @pytest.fixture(autouse=True)
    def _chdir_to_tmp(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """run_axe_from_json rejects paths outside cwd (path-traversal guard).
        Tests write fixtures to tmp_path, so chdir there first."""
        monkeypatch.chdir(tmp_path)

    def test_loads_violations_list(self, tmp_path: Path) -> None:
        violations_data = [
            {
                "id": "image-alt",
                "description": "Images must have alternate text",
                "helpUrl": "https://dequeuniversity.com/rules/axe/4.9/image-alt",
                "impact": "critical",
                "tags": ["wcag111", "cat.text-alternatives"],
                "nodes": [{"html": "<img src='logo.png'>", "target": ["img"]}],
            }
        ]
        json_file = tmp_path / "violations.json"
        json_file.write_text(json.dumps(violations_data), encoding="utf-8")

        violations = run_axe_from_json(str(json_file))

        assert len(violations) == 1
        assert violations[0].id == "image-alt"
        assert violations[0].impact == ImpactLevel.CRITICAL
        assert violations[0].wcag_criterion == "1.1.1"
        assert len(violations[0].nodes) == 1

    def test_loads_full_axe_results_object(self, tmp_path: Path) -> None:
        # Dict-with-violations shape is what `axe.run().toJSON()` returns.
        full_axe_results = {
            "testEngine": {"name": "axe-core", "version": "4.9.0"},
            "violations": [
                {
                    "id": "label",
                    "description": "Form elements must have labels",
                    "helpUrl": "https://dequeuniversity.com/rules/axe/4.9/label",
                    "impact": "serious",
                    "tags": ["wcag131", "wcag111"],
                    "nodes": [],
                }
            ],
            "passes": [],
        }
        json_file = tmp_path / "full_results.json"
        json_file.write_text(json.dumps(full_axe_results), encoding="utf-8")

        violations = run_axe_from_json(str(json_file))

        assert len(violations) == 1
        assert violations[0].id == "label"
        assert violations[0].impact == ImpactLevel.SERIOUS

    def test_invalid_json_raises(self, tmp_path: Path) -> None:
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not valid json {{{", encoding="utf-8")

        with pytest.raises(json.JSONDecodeError):
            run_axe_from_json(str(bad_file))

    def test_unexpected_structure_raises(self, tmp_path: Path) -> None:
        json_file = tmp_path / "weird.json"
        json_file.write_text(json.dumps({"unexpected": "shape"}), encoding="utf-8")

        with pytest.raises(ValueError, match="Cannot parse axe JSON"):
            run_axe_from_json(str(json_file))

    def test_handles_null_impact(self, tmp_path: Path) -> None:
        # axe sets impact=None for best-practice rules; should default to MINOR.
        violations_data = [
            {
                "id": "best-practice-rule",
                "description": "A best-practice rule",
                "helpUrl": "https://example.com",
                "impact": None,
                "tags": ["best-practice"],
                "nodes": [],
            }
        ]
        json_file = tmp_path / "null_impact.json"
        json_file.write_text(json.dumps(violations_data), encoding="utf-8")

        violations = run_axe_from_json(str(json_file))
        assert violations[0].impact == ImpactLevel.MINOR


class TestRunAxePlaceholderGuard:
    # sdk-review F2: guard tested via isolated tmp stub; repo does not ship axe.min.js.

    def test_raises_when_axe_is_placeholder(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import wcag_auditor.axe_runner as axe_module

        placeholder = tmp_path / "axe.min.js"
        placeholder.write_text(
            "/* axe-core placeholder */\nthrow new Error('Run make download-axe');\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(axe_module, "AXE_JS_PATH", placeholder)
        mock_page = MagicMock()
        with pytest.raises(FileNotFoundError, match="axe-core|placeholder"):
            run_axe(mock_page, "https://example.com")

    def test_raises_when_axe_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import wcag_auditor.axe_runner as axe_module

        monkeypatch.setattr(axe_module, "AXE_JS_PATH", Path("/nonexistent/axe.min.js"))
        mock_page = MagicMock()

        with pytest.raises(FileNotFoundError, match="axe-core not found"):
            run_axe(mock_page, "https://example.com")


class TestPathToUrlConfinement:
    # B2: paths outside cwd should be rejected unless WCAG_ALLOW_FILE_OUTSIDE_CWD=1.

    def test_happy_path_inside_cwd(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        html = tmp_path / "page.html"
        html.write_text("<html></html>", encoding="utf-8")

        url = _path_to_url(str(html))
        assert url.startswith("file://")
        assert "page.html" in url

    def test_rejects_path_outside_cwd(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # cwd as a subdir makes the parent count as "outside". Analogous to
        # `wcag-auditor audit /etc/shadow` from a project subdirectory.
        sub = tmp_path / "inside"
        sub.mkdir()
        monkeypatch.chdir(sub)
        # Ensure override is not set
        monkeypatch.delenv("WCAG_ALLOW_FILE_OUTSIDE_CWD", raising=False)

        outside = tmp_path / "outside.html"
        outside.write_text("<html></html>", encoding="utf-8")

        with pytest.raises(ValueError, match="outside the current working directory"):
            _path_to_url(str(outside))

    def test_override_allows_outside_cwd(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sub = tmp_path / "inside"
        sub.mkdir()
        monkeypatch.chdir(sub)
        monkeypatch.setenv("WCAG_ALLOW_FILE_OUTSIDE_CWD", "1")

        outside = tmp_path / "outside.html"
        outside.write_text("<html></html>", encoding="utf-8")

        url = _path_to_url(str(outside))
        assert url.startswith("file://")

    def test_http_url_passes_through_unchanged(self) -> None:
        # http(s) goes through the SSRF guard separately, not cwd confinement.
        assert _path_to_url("https://example.com") == "https://example.com"
        assert _path_to_url("http://example.com/page") == "http://example.com/page"


class TestHttpUrlSsrfGuard:
    # B11: link-local / loopback / RFC1918 are blocked by default.

    def test_public_url_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("WCAG_ALLOW_LOCALHOST", raising=False)
        monkeypatch.delenv("WCAG_ALLOW_PRIVATE_NET", raising=False)
        _check_http_url_safe("https://example.com/path")

    def test_link_local_169_254_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Cloud metadata IP. Never allowed, no override.
        monkeypatch.delenv("WCAG_ALLOW_LOCALHOST", raising=False)
        monkeypatch.delenv("WCAG_ALLOW_PRIVATE_NET", raising=False)
        with pytest.raises(ValueError, match="link-local"):
            _check_http_url_safe("http://169.254.169.254/latest/meta-data/")

    def test_loopback_127_blocked_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("WCAG_ALLOW_LOCALHOST", raising=False)
        with pytest.raises(ValueError, match="loopback"):
            _check_http_url_safe("http://127.0.0.1:8080/")

    def test_loopback_allowed_with_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WCAG_ALLOW_LOCALHOST", "1")
        _check_http_url_safe("http://127.0.0.1:8080/")

    def test_localhost_hostname_blocked_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("WCAG_ALLOW_LOCALHOST", raising=False)
        with pytest.raises(ValueError, match="localhost"):
            _check_http_url_safe("http://localhost:3000/")

    def test_localhost_hostname_allowed_with_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WCAG_ALLOW_LOCALHOST", "1")
        _check_http_url_safe("http://localhost:3000/")

    def test_rfc1918_blocked_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("WCAG_ALLOW_PRIVATE_NET", raising=False)
        for url in (
            "http://10.0.0.5/",
            "http://172.16.1.1/",
            "http://192.168.1.1/",
        ):
            with pytest.raises(ValueError, match="private RFC1918"):
                _check_http_url_safe(url)

    def test_rfc1918_allowed_with_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WCAG_ALLOW_PRIVATE_NET", "1")
        _check_http_url_safe("http://10.0.0.5/")
        _check_http_url_safe("http://192.168.1.1/")
