from __future__ import annotations

import os
import stat
from pathlib import Path

import sqlite_utils

from wcag_auditor.models import AuditReport

_DEFAULT_DB_PATH = Path.home() / ".local" / "share" / "wcag-auditor" / "audits.db"


def _get_db_path() -> Path:
    env_path = os.environ.get("WCAG_DB_PATH")
    return Path(env_path) if env_path else _DEFAULT_DB_PATH


def _get_db() -> sqlite_utils.Database:
    """Open the audits DB, applying WAL + 0600 + table-create on first use."""
    db_path = _get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    db = sqlite_utils.Database(str(db_path))

    # WAL lets the CLI keep its handle open while pytest opens its own. Without
    # it the unit tests intermittently hang on macOS when both processes hit
    # the same file. NORMAL sync because we never crash-recover audit history.
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")

    # Audit history can include scanned URLs and node HTML. Owner-only.
    db_path.chmod(stat.S_IRUSR | stat.S_IWUSR)

    if "audits" not in db.table_names():
        db["audits"].create(  # type: ignore[index]
            {
                "id": int,
                "scanned_path": str,
                "timestamp": str,
                "total_violations": int,
                "report_json": str,
            },
            pk="id",
        )

    return db


def save_report(report: AuditReport) -> int:
    """Insert a report row and return its new id."""
    db = _get_db()
    result = db["audits"].insert(  # type: ignore[index]
        {
            "scanned_path": report.scanned_path,
            "timestamp": report.timestamp.isoformat(),
            "total_violations": report.total_violations,
            "report_json": report.model_dump_json(),
        }
    )
    return result.last_pk  # type: ignore[return-value]


def list_reports(limit: int = 20) -> list[dict]:
    """Most recent ``limit`` reports, newest first."""
    db = _get_db()
    rows = db.execute(
        "SELECT id, scanned_path, timestamp, total_violations "
        "FROM audits ORDER BY id DESC LIMIT ?",
        [limit],
    ).fetchall()
    return [
        {
            "id": row[0],
            "scanned_path": row[1],
            "timestamp": row[2],
            "total_violations": row[3],
        }
        for row in rows
    ]


def get_report(report_id: int) -> AuditReport | None:
    db = _get_db()
    rows = db.execute(
        "SELECT report_json FROM audits WHERE id = ?",
        [report_id],
    ).fetchall()
    if not rows:
        return None
    return AuditReport.model_validate_json(rows[0][0])
