from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ReviewStatus(StrEnum):
    PROPOSED = "proposed"
    UNDER_REVIEW = "under_review"
    CONFIRMED = "confirmed_by_authorized_user"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    VOIDED = "voided"


class ReadinessStatus(StrEnum):
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    NOT_READY = "not_ready"
    READINESS_CONCERNS = "readiness_concerns"
    READY_FOR_HUMAN_REVIEW = "ready_for_human_review"
    CONFIRMED_READY = "confirmed_ready_by_authorized_user"


class DeficiencyStatus(StrEnum):
    PROPOSED = "proposed"
    UNDER_REVIEW = "under_review"
    OPEN = "open"
    CORRECTION_REPORTED = "correction_reported"
    READY_FOR_VERIFICATION = "ready_for_verification"
    VERIFIED = "verified_by_authorized_reviewer"
    CLOSED = "closed"
    REJECTED = "rejected"
    DEFERRED = "deferred"
    SUPERSEDED = "superseded"
    REOPENED = "reopened"


class Evidence(Frozen):
    record_type: str
    record_id: str
    citation: dict[str, Any]
    excerpt: str
    visual_region: tuple[float, float, float, float] | None = None
    reported_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    human_confirmed: bool = False


class WorkflowLink(Frozen):
    workflow_type: str
    record_id: str
    relationship: str
    human_confirmed: bool = True


class CommissioningSystem(Frozen):
    id: str
    project_id: str
    name: str
    description: str = ""
    discipline: str | None = None
    location: str | None = None
    parent_system_id: str | None = None
    responsible_contractor_as_reported: str | None = None
    commissioning_authority: str | None = None
    status: ReviewStatus = ReviewStatus.PROPOSED
    links: tuple[WorkflowLink, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Asset(Frozen):
    id: str
    project_id: str
    equipment_tag: str
    equipment_type: str
    system_id: str
    manufacturer: str | None = None
    model: str | None = None
    serial_number: str | None = None
    location: str | None = None
    parent_asset_id: str | None = None
    product_lineage: dict[str, str] = {}
    conflicts: tuple[str, ...] = ()
    requirements: tuple[str, ...] = ()
    links: tuple[WorkflowLink, ...] = ()
    evidence: tuple[Evidence, ...] = ()


class Requirement(Frozen):
    id: str
    project_id: str
    original_text: str
    normalized_text: str
    category: str
    system_id: str | None = None
    asset_id: str | None = None
    responsible_party_as_stated: str | None = None
    timing: str | None = None
    prerequisites: tuple[str, ...] = ()
    acceptance_authority_as_stated: str | None = None
    citation: Evidence
    confidence: float = Field(ge=0, le=1)
    uncertainty: tuple[str, ...] = ()
    review_status: ReviewStatus = ReviewStatus.PROPOSED
    reviewer: str | None = None


class Checklist(Frozen):
    id: str
    project_id: str
    revision: int = 1
    system_id: str
    asset_id: str | None = None
    title: str
    items: tuple[dict[str, Any], ...]
    responses: dict[str, dict[str, Any]] = {}
    status: ReviewStatus = ReviewStatus.PROPOSED
    evidence: tuple[Evidence, ...] = ()
    reviewer: str | None = None


class TestProcedure(Frozen):
    id: str
    project_id: str
    revision_id: str
    revision: int
    title: str
    system_id: str
    procedure_type: str
    prerequisites: tuple[str, ...] = ()
    steps: tuple[dict[str, Any], ...]
    acceptance_criteria_as_stated: tuple[str, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    review_status: ReviewStatus = ReviewStatus.PROPOSED
    approved_as_recorded: bool = False


class TestExecution(Frozen):
    id: str
    project_id: str
    procedure_revision_id: str
    system_id: str
    asset_id: str | None = None
    test_date: date
    expected_results: tuple[str, ...]
    reported_results: tuple[str, ...]
    reviewer_confirmed_results: tuple[str, ...] = ()
    reported_outcome: str = "not_reported"
    reviewer_disposition: str | None = None
    instrument_ids: tuple[str, ...] = ()
    deviations: tuple[str, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    retest_of_id: str | None = None


class Instrument(Frozen):
    id: str
    project_id: str
    instrument_type: str
    serial_number: str
    calibration_date: date | None = None
    expiration_date: date | None = None
    certificate: Evidence | None = None


class Deficiency(Frozen):
    id: str
    project_id: str
    title: str
    description: str
    system_id: str
    asset_id: str | None = None
    source_record_id: str | None = None
    severity_proposal: str = "moderate"
    status: DeficiencyStatus = DeficiencyStatus.PROPOSED
    owner: str | None = None
    due_date: date | None = None
    corrective_action_as_reported: str | None = None
    closure_evidence: tuple[Evidence, ...] = ()
    reviewer_disposition: str | None = None
    links: tuple[WorkflowLink, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    supersedes_id: str | None = None
    version: int = 1


class ReadinessAssessment(Frozen):
    id: str
    project_id: str
    system_id: str
    purpose: str
    status: ReadinessStatus
    factors: tuple[str, ...]
    blockers: tuple[str, ...]
    evidence: tuple[Evidence, ...]
    assessed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    policy_version: str = "commissioning-readiness-1"
    human_authorization: bool = False


class TurnoverItem(Frozen):
    id: str
    item_type: str
    required: bool = True
    status: str = "missing"
    record_id: str | None = None
    evidence: tuple[Evidence, ...] = ()


class TurnoverPackage(Frozen):
    id: str
    project_id: str
    package_type: str
    system_id: str | None = None
    revision: int = 1
    status: ReviewStatus = ReviewStatus.PROPOSED
    items: tuple[TurnoverItem, ...]
    completeness_proposal: str = "incomplete"
    reviewer_disposition: str | None = None
    accepted_as_recorded: bool = False
    evidence: tuple[Evidence, ...] = ()


class CloseoutRecord(Frozen):
    id: str
    project_id: str
    record_type: str
    system_id: str | None = None
    asset_id: str | None = None
    attributes: dict[str, Any]
    document_revision_id: str | None = None
    status: ReviewStatus = ReviewStatus.PROPOSED
    conflicts: tuple[str, ...] = ()
    evidence: tuple[Evidence, ...] = ()


class AuditEvent(Frozen):
    id: str
    project_id: str
    event_type: str
    subject_id: str
    actor: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class NotificationRequest(Frozen):
    id: str
    project_id: str
    event_type: str
    subject_id: str
    summary: str
    status: str = "queued_local_only"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CommissioningDashboard(Frozen):
    project_id: str
    systems: int
    assets: int
    requirements_awaiting_review: int
    tests_awaiting_review: int
    failed_or_incomplete_tests: int
    open_deficiencies: int
    readiness_concerns: int
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TurnoverDashboard(Frozen):
    project_id: str
    packages: int
    packages_awaiting_review: int
    missing_items: int
    missing_manuals: int
    missing_warranties: int
    missing_training: int
    missing_as_builts: int
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
