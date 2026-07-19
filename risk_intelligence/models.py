"""Immutable risk intelligence records.  Proposals are never determinations."""

from datetime import UTC, date, datetime
from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class RiskStatus(StrEnum):
    PROPOSED = "proposed"
    UNDER_REVIEW = "under_review"
    CONFIRMED_FOR_MONITORING = "confirmed_for_monitoring"
    REJECTED = "rejected"
    MITIGATED = "mitigated"
    CLOSED = "closed"
    SUPERSEDED = "superseded"
    REOPENED = "reopened"


class RiskLevel(StrEnum):
    INFORMATIONAL = "informational"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL_REVIEW_REQUIRED = "critical_review_required"


class LinkStrength(StrEnum):
    STRONG = "strong"
    WEAK_CANDIDATE = "weak_candidate"


class Evidence(Frozen):
    """A source reference, intentionally generic so it links canonical domains."""

    record_type: str
    record_id: str
    citation: dict[str, object]
    excerpt: str
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: str | None = None
    location: str | None = None
    system: str | None = None


class Correlation(Frozen):
    id: str
    project_id: str
    left_record_id: str
    right_record_id: str
    signals: tuple[str, ...]
    strength: LinkStrength
    confidence: float = Field(ge=0, le=1)
    uncertainty: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    human_review_required: bool = True


class RiskScore(Frozen):
    severity: RiskLevel
    likelihood: RiskLevel
    factors: tuple[str, ...]
    confidence: float = Field(ge=0, le=1)
    uncertainty: tuple[str, ...] = ()
    policy_version: str = "risk-score-1"


class Mitigation(Frozen):
    id: str
    project_id: str
    risk_id: str
    description: str
    owner: str | None = None
    due_date: date | None = None
    status: str = "proposed"
    completion_evidence: tuple[Evidence, ...] = ()
    reviewer: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RiskCandidate(Frozen):
    id: str
    project_id: str
    title: str
    description: str
    original_source_wording: str
    category: str = "unknown"
    status: RiskStatus = RiskStatus.PROPOSED
    score: RiskScore
    evidence: tuple[Evidence, ...]
    correlations: tuple[Correlation, ...] = ()
    linked_record_ids: tuple[str, ...] = ()
    affected_scope: str | None = None
    location: str | None = None
    contractor_or_trade: str | None = None
    reviewer: str | None = None
    reviewer_disposition: str | None = None
    owner: str | None = None
    review_date: date | None = None
    mitigation_ids: tuple[str, ...] = ()
    supersedes_id: str | None = None
    superseded_by_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    version: int = 1


class CommitmentView(Frozen):
    """A normalized view; it never owns or duplicates its source workflow record."""

    id: str
    project_id: str
    source_record_type: str
    source_record_id: str
    title: str
    owner: str | None = None
    due_date: date | None = None
    status: str = "open"
    dependencies: tuple[str, ...] = ()
    citations: tuple[Evidence, ...] = ()
    completion_evidence: tuple[Evidence, ...] = ()
    completion_confirmed: bool = False
    carry_forward_count: int = 0
    uncertainty: tuple[str, ...] = ()


class DependencyEdge(Frozen):
    id: str
    project_id: str
    source_id: str
    target_id: str
    relationship: str
    evidence: tuple[Evidence, ...]
    resolved: bool = False
    human_confirmed: bool = False


class AuditEvent(Frozen):
    id: str
    project_id: str
    event_type: str
    subject_id: str
    actor: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, str] = {}


class NotificationRequest(Frozen):
    id: str
    project_id: str
    event_type: str
    subject_id: str
    summary: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: str = "queued_local_only"


class RiskDashboard(Frozen):
    project_id: str
    proposed: int
    confirmed: int
    high_priority_review: int
    overdue_commitments: int
    commitments_without_owner: int
    unresolved_dependencies: int
    stale_risks: int
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
