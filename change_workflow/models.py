"""Domain records for operational revision review and project change management."""

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from document_processing.models import CitationReference
from revision_intelligence.models import ChangeSeverity, EvidenceStrength


class ChangeOrigin(StrEnum):
    REVISION_FINDING = "revision_finding"
    RFI = "rfi"
    SUBMITTAL = "submittal"
    PROCUREMENT = "procurement"
    SCHEDULE = "schedule"
    OWNER_DECISION = "owner_decision"
    MEETING_ACTION = "meeting_action"
    FIELD_CONDITION = "field_condition"
    DESIGN_DIRECTIVE = "design_directive"
    CHANGE_ORDER = "change_order"
    MANUAL = "manual"
    UNKNOWN = "unknown"


class ChangePriority(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATIONAL = "informational"


class ChangeStatus(StrEnum):
    NEW = "new"
    UNREVIEWED = "unreviewed"
    ASSIGNED = "assigned"
    UNDER_REVIEW = "under_review"
    NEEDS_INFORMATION = "needs_information"
    ACTION_REQUIRED = "action_required"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    RESOLVED = "resolved"
    CLOSED = "closed"
    SUPERSEDED = "superseded"
    CANCELLED = "cancelled"


class ChangeDisposition(StrEnum):
    ACCEPTED_AS_CHANGE = "accepted_as_change"
    REJECTED_NOT_MATERIAL = "rejected_not_material"
    DUPLICATE = "duplicate"
    INFORMATIONAL_ONLY = "informational_only"
    REQUIRES_RFI = "requires_rfi"
    REQUIRES_SUBMITTAL = "requires_submittal"
    REQUIRES_PROCUREMENT_ACTION = "requires_procurement_action"
    REQUIRES_SCHEDULE_ACTION = "requires_schedule_action"
    REQUIRES_OWNER_DECISION = "requires_owner_decision"
    REQUIRES_CHANGE_ORDER_REVIEW = "requires_change_order_review"
    REQUIRES_FIELD_COORDINATION = "requires_field_coordination"
    REQUIRES_QUALITY_REVIEW = "requires_quality_review"
    REQUIRES_SAFETY_REVIEW = "requires_safety_review"
    REQUIRES_COMMISSIONING_REVIEW = "requires_commissioning_review"
    NEEDS_INFORMATION = "needs_information"
    SUPERSEDED = "superseded"
    NO_ACTION_REQUIRED = "no_action_required"
    UNRESOLVED = "unresolved"


class ImpactCertainty(StrEnum):
    CONFIRMED = "confirmed"
    LIKELY = "likely"
    POSSIBLE = "possible"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


class WorkflowType(StrEnum):
    RFI = "rfi"
    SUBMITTAL = "submittal"
    PROCUREMENT_ITEM = "procurement_item"
    SCHEDULE_ACTIVITY = "schedule_activity"
    OWNER_DECISION = "owner_decision"
    MEETING_ACTION = "meeting_action"
    CHANGE_EVENT = "change_event"
    CHANGE_ORDER = "change_order"
    QUALITY_ITEM = "quality_item"
    SAFETY_ITEM = "safety_item"
    COMMISSIONING_ITEM = "commissioning_item"
    FIELD_ISSUE = "field_issue"
    EXTERNAL_REFERENCE = "external_reference"


class RelationshipType(StrEnum):
    AFFECTS = "affects"
    CAUSED_BY = "caused_by"
    REQUIRES = "requires"
    RESOLVES = "resolves"
    SUPERSEDES = "supersedes"
    DUPLICATES = "duplicates"
    INFORMS = "informs"
    BLOCKS = "blocks"
    DEPENDS_ON = "depends_on"
    RELATED_TO = "related_to"


class NoteType(StrEnum):
    GENERAL = "general"
    REVIEW = "review"
    QUESTION = "question"
    RESPONSE = "response"
    DECISION = "decision"
    ASSIGNMENT = "assignment"
    ESCALATION = "escalation"
    RESOLUTION = "resolution"
    SYSTEM = "system"


class AuditEventType(StrEnum):
    CHANGE_CREATED = "change_created"
    FINDING_ADMITTED = "finding_admitted"
    FINDING_EXCLUDED = "finding_excluded"
    ASSIGNMENT_CHANGED = "assignment_changed"
    STATUS_TRANSITION = "status_transition"
    DISPOSITION_CHANGED = "disposition_changed"
    NOTE_ADDED = "note_added"
    LINK_CREATED = "link_created"
    LINK_REMOVED = "link_removed"
    RELATED_ITEM_CREATED = "related_item_created"
    RESOLUTION_RECORDED = "resolution_recorded"
    CHANGE_REOPENED = "change_reopened"
    COMPARISON_STALE = "comparison_stale"
    COMPARISON_REGENERATED = "comparison_regenerated"
    NOTIFICATION_REQUESTED = "notification_requested"


class ActorReference(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)


class ReviewerReference(ActorReference):
    email: str | None = None
    team: str | None = None
    discipline: str | None = None


class ChangeAssignment(BaseModel):
    model_config = ConfigDict(frozen=True)
    assignee: ReviewerReference
    assigned_by: ActorReference
    assigned_at: datetime
    due_date: date | None = None
    note: str | None = None
    primary: bool = True
    active: bool = True
    suggested: bool = False


class ChangeEvidenceReference(BaseModel):
    model_config = ConfigDict(frozen=True)
    comparison_id: str
    finding_id: str
    old_document_id: str | None = None
    new_document_id: str | None = None
    old_citation: CitationReference | None = None
    new_citation: CitationReference | None = None
    evidence_hash: str


class ChangeNote(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    author: ActorReference
    created_at: datetime
    text: str = Field(min_length=1, max_length=10_000)
    note_type: NoteType = NoteType.GENERAL
    transition_id: str | None = None


class ChangeWorkflowLink(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    workflow_type: WorkflowType
    reference: str = Field(min_length=1)
    display_label: str
    relationship: RelationshipType
    created_by: ActorReference
    created_at: datetime
    url: str | None = None
    notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("url")
    @classmethod
    def safe_url(cls, value: str | None) -> str | None:
        if value is not None and not value.casefold().startswith(("https://", "http://")):
            raise ValueError("Workflow URLs must use http or https")
        return value


class RelatedItemStatus(StrEnum):
    DRAFT = "draft"
    OPEN = "open"
    PENDING_REVIEW = "pending_review"
    SUBMITTED = "submitted"
    ANSWERED = "answered"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class RelatedItem(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    project_id: str
    project_change_id: str
    workflow_type: WorkflowType
    title: str
    description: str
    status: RelatedItemStatus = RelatedItemStatus.DRAFT
    owner: ReviewerReference | None = None
    due_date: date | None = None
    evidence: ChangeEvidenceReference
    created_at: datetime
    updated_at: datetime


class DispositionRecord(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    disposition: ChangeDisposition
    reviewer: ActorReference
    created_at: datetime
    explanation: str = Field(min_length=1)
    cost_impact: ImpactCertainty = ImpactCertainty.UNKNOWN
    schedule_impact: ImpactCertainty = ImpactCertainty.UNKNOWN
    scope_impact: ImpactCertainty = ImpactCertainty.UNKNOWN
    formal_change_management_required: bool = False


class AuditEvent(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    project_id: str
    entity_type: str
    entity_id: str
    actor: ActorReference
    timestamp: datetime
    event_type: AuditEventType
    previous_state: str | None = None
    new_state: str | None = None
    reason: str | None = None
    correlation_id: str
    source: str = "service"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectChange(BaseModel):
    model_config = ConfigDict(frozen=True)
    schema_version: int = 1
    version: int = Field(default=1, ge=1)
    id: str
    project_id: str
    origin: ChangeOrigin
    title: str
    description: str
    priority: ChangePriority
    status: ChangeStatus = ChangeStatus.UNREVIEWED
    disposition: ChangeDisposition = ChangeDisposition.UNRESOLVED
    evidence: ChangeEvidenceReference
    assignments: tuple[ChangeAssignment, ...] = ()
    notes: tuple[ChangeNote, ...] = ()
    dispositions: tuple[DispositionRecord, ...] = ()
    links: tuple[ChangeWorkflowLink, ...] = ()
    related_items: tuple[RelatedItem, ...] = ()
    affected_disciplines: tuple[str, ...] = ()
    affected_workflows: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None = None
    closed_at: datetime | None = None
    resolution_summary: str | None = None
    source_stale: bool = False
    stale_acknowledged: bool = False
    human_review_required: bool = True
    evidence_strength: EvidenceStrength
    potential_significance: ChangeSeverity
    external_reference: str | None = None


class AdmissionDecision(BaseModel):
    model_config = ConfigDict(frozen=True)
    finding_id: str
    admitted: bool
    reasons: tuple[str, ...]
    policy_version: str


class RegisterGenerationResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    comparison_id: str
    evaluated: int
    admitted: int
    excluded: int
    reused: int
    change_ids: tuple[str, ...]
    decisions: tuple[AdmissionDecision, ...]
    warnings: tuple[str, ...] = ()


class DashboardMetric(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    count: int = Field(ge=0)


class ProjectChangeDashboard(BaseModel):
    model_config = ConfigDict(frozen=True)
    project_id: str
    metrics: tuple[DashboardMetric, ...]
    priority_queue: tuple[ProjectChange, ...]
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class NotificationType(StrEnum):
    ASSIGNMENT_CREATED = "assignment_created"
    DUE_DATE_APPROACHING = "due_date_approaching"
    ITEM_OVERDUE = "item_overdue"
    CRITICAL_CHANGE_ADMITTED = "critical_change_admitted"
    INFORMATION_REQUESTED = "information_requested"
    RELATED_ITEM_CREATED = "related_item_created"
    COMPARISON_STALE = "comparison_stale"
    COMPARISON_REGENERATED = "comparison_regenerated"
    STATUS_CHANGED = "status_changed"
    RESOLUTION_COMPLETED = "resolution_completed"


class NotificationStatus(StrEnum):
    QUEUED = "queued"
    DELIVERED = "delivered"
    FAILED = "failed"
    SUPPRESSED = "suppressed"


class NotificationRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    project_id: str
    change_id: str
    event_id: str
    recipient: ReviewerReference
    notification_type: NotificationType
    created_at: datetime
    status: NotificationStatus = NotificationStatus.QUEUED
    payload: dict[str, str] = Field(default_factory=dict)
