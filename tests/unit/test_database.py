"""Unit tests for database.py — save_report, list_reports, get_report, WCAG_DB_PATH,
and the 0600 chmod enforced on every _get_db() call.

All tests use tmp_path via WCAG_DB_PATH so they never touch the real user DB.
"""
from __future__ import annotations

import stat
from pathlib import Path

import pytest

from wcag_auditor.database import get_report, list_reports, save_report
from wcag_auditor.models import AuditReport, AuditResult, ImpactLevel, ViolationFix


def _make_fix() -> ViolationFix:
    return ViolationFix(
        element_selector="img",
        original_html="<img src='x'>",
        fix_html="<img src='x' alt='alt text'>",
        fix_explanation="Add alt attribute.",
        wcag_criterion="1.1.1",
        impact=ImpactLevel.CRITICAL,
    )


def _make_result(file_path: str = "test.html") -> AuditResult:
    return AuditResult(
        file_path=file_path,
        wcag_criterion="1.1.1",
        rule_id="image-alt",
        impact=ImpactLevel.CRITICAL,
        fixes=[_make_fix()],
        explanation="Image is missing alt text.",
        confidence_score=0.9,
    )


def _make_report(path: str = "test.html", n_results: int = 1) -> AuditReport:
    results = [_make_result(path) for _ in range(n_results)]
    return AuditReport.from_results(path, results)


class TestSaveReport:
    def test_returns_integer_id(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WCAG_DB_PATH", str(tmp_path / "test.db"))
        report = _make_report()
        report_id = save_report(report)
        assert isinstance(report_id, int)
        assert report_id >= 1

    def test_ids_are_sequential(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WCAG_DB_PATH", str(tmp_path / "test.db"))
        id1 = save_report(_make_report("a.html"))
        id2 = save_report(_make_report("b.html"))
        assert id2 > id1

    def test_saves_correct_scanned_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WCAG_DB_PATH", str(tmp_path / "test.db"))
        report = _make_report("https://example.com")
        save_report(report)
        rows = list_reports(limit=1)
        assert rows[0]["scanned_path"] == "https://example.com"

    def test_saves_total_violations(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WCAG_DB_PATH", str(tmp_path / "test.db"))
        report = _make_report(n_results=3)
        save_report(report)
        rows = list_reports(limit=1)
        assert rows[0]["total_violations"] == 3


class TestGetReport:
    def test_round_trip(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WCAG_DB_PATH", str(tmp_path / "test.db"))
        report = _make_report("roundtrip.html")
        report_id = save_report(report)

        retrieved = get_report(report_id)

        assert retrieved is not None
        assert retrieved.scanned_path == "roundtrip.html"
        assert retrieved.total_violations == 1
        assert retrieved.results[0].rule_id == "image-alt"

    def test_returns_none_for_missing_id(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WCAG_DB_PATH", str(tmp_path / "test.db"))
        # Ensure table exists by saving one report.
        save_report(_make_report())
        result = get_report(99999)
        assert result is None

    def test_preserves_impact_counts(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WCAG_DB_PATH", str(tmp_path / "test.db"))
        report = _make_report(n_results=2)
        report_id = save_report(report)
        retrieved = get_report(report_id)
        assert retrieved is not None
        assert retrieved.critical_count == 2


class TestListReports:
    def test_returns_newest_first(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WCAG_DB_PATH", str(tmp_path / "test.db"))
        save_report(_make_report("first.html"))
        save_report(_make_report("second.html"))

        rows = list_reports(limit=10)
        assert rows[0]["scanned_path"] == "second.html"
        assert rows[1]["scanned_path"] == "first.html"

    def test_respects_limit(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WCAG_DB_PATH", str(tmp_path / "test.db"))
        for i in range(5):
            save_report(_make_report(f"page{i}.html"))

        rows = list_reports(limit=3)
        assert len(rows) == 3

    def test_row_schema(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WCAG_DB_PATH", str(tmp_path / "test.db"))
        save_report(_make_report())

        rows = list_reports(limit=1)
        assert len(rows) == 1
        row = rows[0]
        assert "id" in row
        assert "scanned_path" in row
        assert "timestamp" in row
        assert "total_violations" in row


class TestDbPathOverride:
    def test_wcag_db_path_env_is_respected(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        custom_path = tmp_path / "custom" / "audits.db"
        monkeypatch.setenv("WCAG_DB_PATH", str(custom_path))

        save_report(_make_report())

        assert custom_path.exists(), "DB was not created at WCAG_DB_PATH"


class TestDbPermissions:
    def test_db_file_is_owner_only(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WCAG_DB_PATH", str(tmp_path / "perms.db"))
        save_report(_make_report())

        db_path = tmp_path / "perms.db"
        mode = db_path.stat().st_mode
        # Owner read+write (0o600). Group and other must have no bits set.
        assert mode & stat.S_IRGRP == 0, "Group read bit should not be set"
        assert mode & stat.S_IWGRP == 0, "Group write bit should not be set"
        assert mode & stat.S_IROTH == 0, "Other read bit should not be set"
        assert mode & stat.S_IWOTH == 0, "Other write bit should not be set"
        assert mode & stat.S_IRUSR != 0, "Owner read bit should be set"
        assert mode & stat.S_IWUSR != 0, "Owner write bit should be set"
