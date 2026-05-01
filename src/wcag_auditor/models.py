from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class ImpactLevel(str, Enum):
    CRITICAL = "critical"
    SERIOUS = "serious"
    MODERATE = "moderate"
    MINOR = "minor"


class ViolationInput(BaseModel):
    id: str
    description: str
    help_url: str
    impact: ImpactLevel
    nodes: list[dict]
    wcag_criterion: str


class ViolationFix(BaseModel):
    element_selector: str
    original_html: str
    fix_html: str
    fix_explanation: str
    wcag_criterion: str
    impact: ImpactLevel


class AuditResult(BaseModel):
    file_path: str
    wcag_criterion: str
    rule_id: str
    impact: ImpactLevel
    fixes: list[ViolationFix]
    explanation: str
    confidence_score: float = Field(ge=0.0, le=1.0)


class AuditReport(BaseModel):
    scanned_path: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    total_violations: int
    critical_count: int = 0
    serious_count: int = 0
    moderate_count: int = 0
    minor_count: int = 0
    results: list[AuditResult]

    @classmethod
    def from_results(cls, path: str, results: list[AuditResult]) -> AuditReport:
        # one pass, one Counter would be marginally cuter, but this reads fine
        # and keeps the four count fields obvious in the call site
        counts = {level: 0 for level in ImpactLevel}
        for r in results:
            counts[r.impact] += 1
        return cls(
            scanned_path=path,
            total_violations=len(results),
            critical_count=counts[ImpactLevel.CRITICAL],
            serious_count=counts[ImpactLevel.SERIOUS],
            moderate_count=counts[ImpactLevel.MODERATE],
            minor_count=counts[ImpactLevel.MINOR],
            results=results,
        )
