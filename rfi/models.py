"""Canonical evidence-backed request-for-information domain models."""

from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from change_workflow.models import ActorReference, ImpactCertainty, ReviewerReference
from document_processing.models import CitationReference


class RFIStatus(StrEnum):
    DRAFT = "draft"
    PENDING_INTERNAL_REVIEW = "pending_internal_review"
    REVISIONS_REQUIRED = "revisions_required"
    APPROVED_FOR_ISSUE = "approved_for_issue"
    ISSUED = "issued"
    ACKNOWLEDGED = "acknowledged"
    UNDER_REVIEW = "under_review"
    RESPONSE_RECEIVED = "response_received"
    CLARIFICATION_REQUIRED = "clarification_required"
    ANSWERED = "answered"
    RESOLVED = "resolved"
    CLOSED = "closed"
    VOID = "void"
    SUPERSEDED = "superseded"


class RFIPriority(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RFIReviewDecision(StrEnum):
    APPROVED = "approved"
    REVISIONS_REQUIRED = "revisions_required"
    REJECTED = "rejected"
    NEEDS_INFORMATION = "needs_information"


class RFIResponseType(StrEnum):
    OFFICIAL = "official"
    DRAFT = "draft"
    PARTIAL = "partial"
    CLARIFICATION = "clarification"
    REVISED = "revised"
    NO_CHANGE = "no_change"
    VOID = "void"


class RFIImpactType(StrEnum):
    COST = "cost"
    SCHEDULE = "schedule"
    SCOPE = "scope"
    PROCUREMENT = "procurement"
    QUALITY = "quality"
    SAFETY = "safety"
    TESTING = "testing"
    COMMISSIONING = "commissioning"
    OWNER_DECISION = "owner_decision"
    FIELD_COORDINATION = "field_coordination"


class RFIQualitySeverity(StrEnum):
    BLOCKING = "blocking"
    WARNING = "warning"
    INFORMATIONAL = "informational"


class RFIEvidenceReference(BaseModel):
    model_config = ConfigDict(frozen=True)
    citation: CitationReference
    excerpt: str = Field(min_length=1)
    evidence_type: str = "source_document"


class RFIRevision(BaseModel):
    model_config = ConfigDict(frozen=True)
    number: int = Field(ge=1)
    subject: str
    question: str
    background: str
    suggested_resolution: str | None = None
    evidence: tuple[RFIEvidenceReference, ...]
    created_by: ActorReference
    created_at: datetime
    change_summary: str
    approved: bool = False
    content_hash: str


class RFIReview(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    reviewer: ReviewerReference
    decision: RFIReviewDecision
    comments: str | None = None
    created_at: datetime
    revision_number: int


class RFIResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    response_type: RFIResponseType
    responding_party: str
    response_date: date
    text: str = Field(min_length=1)
    citations: tuple[RFIEvidenceReference, ...] = ()
    drawing_references: tuple[str, ...] = ()
    specification_references: tuple[str, ...] = ()
    attachment_metadata: tuple[dict[str, str], ...] = ()
    supersedes_response_id: str | None = None
    created_by: ActorReference
    created_at: datetime


class RFIImpactAssessment(BaseModel):
    model_config = ConfigDict(frozen=True)
    impact_type: RFIImpactType
    certainty: ImpactCertainty
    description: str
    identified_by: ActorReference
    created_at: datetime
    evidence: tuple[RFIEvidenceReference, ...] = ()
    related_project_change_id: str | None = None
    related_workflow_item: str | None = None
    confirmed_value: str | None = None


class RFIStatusHistory(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    previous_status: RFIStatus | None
    new_status: RFIStatus
    actor: ActorReference
    timestamp: datetime
    reason: str | None = None


class RFI(BaseModel):
    model_config = ConfigDict(frozen=True)
    schema_version: int = 1
    version: int = Field(default=1, ge=1)
    id: str
    project_id: str
    number: str
    subject: str = Field(min_length=1)
    question: str = Field(min_length=1)
    background: str = ""
    suggested_resolution: str | None = None
    status: RFIStatus = RFIStatus.DRAFT
    priority: RFIPriority = RFIPriority.MEDIUM
    discipline: str | None = None
    location: str | None = None
    room_number: str | None = None
    area: str | None = None
    drawing_references: tuple[str, ...] = ()
    specification_references: tuple[str, ...] = ()
    evidence: tuple[RFIEvidenceReference, ...] = ()
    created_by: ActorReference
    assigned_reviewer: ReviewerReference | None = None
    responsible_party: str | None = None
    recipients: tuple[str, ...] = ()
    distribution_list: tuple[str, ...] = ()
    related_project_change_ids: tuple[str, ...] = ()
    related_comparison_ids: tuple[str, ...] = ()
    related_finding_ids: tuple[str, ...] = ()
    related_submittal_ids: tuple[str, ...] = ()
    related_procurement_item_ids: tuple[str, ...] = ()
    related_schedule_activity_ids: tuple[str, ...] = ()
    related_owner_decision_ids: tuple[str, ...] = ()
    impacts: tuple[RFIImpactAssessment, ...] = ()
    revisions: tuple[RFIRevision, ...] = ()
    reviews: tuple[RFIReview, ...] = ()
    responses: tuple[RFIResponse, ...] = ()
    status_history: tuple[RFIStatusHistory, ...] = ()
    created_at: datetime
    updated_at: datetime
    issued_at: datetime | None = None
    required_date: date | None = None
    answered_at: datetime | None = None
    resolved_at: datetime | None = None
    closed_at: datetime | None = None
    resolution_summary: str | None = None
    tags: tuple[str, ...] = ()
    external_reference: str | None = None
    legacy_related_item_id: str | None = None


class RFIDraftRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    project_id: str
    project_change_id: str
    instructions: str | None = None
    responsible_party: str | None = None
    required_date: date | None = None


class RFIQualityIssue(BaseModel):
    model_config = ConfigDict(frozen=True)
    code: str
    severity: RFIQualitySeverity
    message: str


class RFIQualityAssessment(BaseModel):
    model_config = ConfigDict(frozen=True)
    valid: bool
    issues: tuple[RFIQualityIssue, ...] = ()


class RFIDuplicateAssessment(BaseModel):
    model_config = ConfigDict(frozen=True)
    possible_duplicate_ids: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    strength: str = "none"
    recommended_review_action: str = "No duplicate indicators found."


class RFIDraftResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    rfi: RFI
    quality: RFIQualityAssessment
    duplicates: RFIDuplicateAssessment
    provider: str = "deterministic"
    warnings: tuple[str, ...] = ()


class RFIResponseAnalysis(BaseModel):
    model_config = ConfigDict(frozen=True)
    complete: bool
    addressed_question: bool
    potential_impacts: tuple[RFIImpactType, ...] = ()
    may_resolve_project_change: bool = False
    explanation: str


class RFIDashboard(BaseModel):
    model_config = ConfigDict(frozen=True)
    project_id: str
    metrics: dict[str, int | float]
    oldest_open: tuple[RFI, ...] = ()


class RFIAuditEvent(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    project_id: str
    rfi_id: str
    event_type: str
    actor: ActorReference
    timestamp: datetime
    previous_state: str | None = None
    new_state: str | None = None
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
