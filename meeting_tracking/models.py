"""Meeting, review, action, decision, and minutes domain records."""

from datetime import date, datetime, time
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class MeetingType(StrEnum):
    OWNER_ARCHITECT_CONTRACTOR = "owner_architect_contractor"
    SUBCONTRACTOR = "subcontractor"
    COORDINATION = "coordination"
    DESIGN = "design"
    PRECONSTRUCTION = "preconstruction"
    PROCUREMENT = "procurement"
    SCHEDULE = "schedule"
    SAFETY = "safety"
    QUALITY = "quality"
    COMMISSIONING = "commissioning"
    TURNOVER = "turnover"
    EXECUTIVE = "executive"
    INTERNAL = "internal"
    DAILY_HUDDLE = "daily_huddle"
    WEEKLY_PROJECT = "weekly_project"
    OTHER = "other"


class MeetingStatus(StrEnum):
    PLANNED = "planned"
    OCCURRED = "occurred"
    DRAFT_MINUTES = "draft_minutes"
    UNDER_REVIEW = "under_review"
    ISSUED = "issued"
    SUPERSEDED = "superseded"
    CANCELLED = "cancelled"


class RecordType(StrEnum):
    AGENDA = "agenda"
    RAW_NOTES = "raw_notes"
    TRANSCRIPT = "transcript"
    DRAFT_MINUTES = "draft_minutes"
    ISSUED_MINUTES = "issued_minutes"
    CORRECTED_MINUTES = "corrected_minutes"
    SUPPLEMENTAL_RECORD = "supplemental_record"


class MeetingItemType(StrEnum):
    ACTION_ITEM = "action_item"
    DECISION = "decision"
    QUESTION = "question"
    ISSUE = "issue"
    RISK = "risk"
    BLOCKER = "blocker"
    COMMITMENT = "commitment"
    DEPENDENCY = "dependency"
    INFORMATION = "information"
    CHANGE_NOTICE = "change_notice"
    OWNER_DECISION_REQUEST = "owner_decision_request"
    RFI_CANDIDATE = "rfi_candidate"
    SUBMITTAL_ACTION = "submittal_action"
    PROCUREMENT_ACTION = "procurement_action"
    SCHEDULE_ACTION = "schedule_action"
    SAFETY_ACTION = "safety_action"
    QUALITY_ACTION = "quality_action"
    COMMISSIONING_ACTION = "commissioning_action"
    UNKNOWN = "unknown"


class ReviewStatus(StrEnum):
    UNREVIEWED = "unreviewed"
    CONFIRMED = "confirmed"
    MODIFIED = "modified"
    REJECTED = "rejected"
    NEEDS_INFORMATION = "needs_information"
    DUPLICATE = "duplicate"
    MERGED = "merged"
    SPLIT = "split"
    SUPERSEDED = "superseded"


class ActionStatus(StrEnum):
    NEW = "new"
    UNASSIGNED = "unassigned"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    WAITING = "waiting"
    BLOCKED = "blocked"
    OVERDUE = "overdue"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    SUPERSEDED = "superseded"
    DEFERRED = "deferred"


class DecisionStatus(StrEnum):
    PROPOSED = "proposed"
    PENDING_CONFIRMATION = "pending_confirmation"
    CONFIRMED = "confirmed"
    SUPERSEDED = "superseded"
    REVERSED = "reversed"
    DEFERRED = "deferred"
    REJECTED = "rejected"
    VOID = "void"


class MinutesStatus(StrEnum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    REVISIONS_REQUIRED = "revisions_required"
    APPROVED = "approved"
    ISSUED = "issued"
    CORRECTED = "corrected"
    SUPERSEDED = "superseded"
    VOID = "void"


class MeetingEvidenceReference(FrozenModel):
    document_id: str
    document_name: str
    page_number: int = Field(ge=1)
    chunk_id: str
    source_location: str
    exact_excerpt: str
    evidence_type: str = "raw_meeting_record"


class MeetingSeries(FrozenModel):
    id: str
    project_id: str
    name: str
    meeting_type: MeetingType
    recurrence_description: str | None = None
    default_participants: tuple[str, ...] = ()
    default_owner: str | None = None
    default_agenda_template: str | None = None
    carry_forward_policy: str = "open_actions"
    numbering_format: str = "{number:03d}"
    active: bool = True
    created_at: datetime
    updated_at: datetime


class MeetingAttendee(FrozenModel):
    name: str
    role: str | None = None
    organization: str | None = None
    email: str | None = None
    attendance_status: str = "unknown"
    meeting_role: str = "attendee"
    citation: MeetingEvidenceReference | None = None
    human_confirmed: bool = False


class MeetingOrganization(FrozenModel):
    name: str
    citation: MeetingEvidenceReference
    human_confirmed: bool = False


class MeetingMetadataCandidate(FrozenModel):
    field_name: str
    candidate_value: str
    citation: MeetingEvidenceReference
    extraction_method: str = "deterministic_native_text"
    evidence_strength: float = Field(ge=0, le=1)
    alternate_candidates: tuple[str, ...] = ()
    human_confirmed: bool = False


class Meeting(FrozenModel):
    id: str
    project_id: str
    title: str
    meeting_type: MeetingType = MeetingType.OTHER
    meeting_series_id: str | None = None
    meeting_number: str | None = None
    meeting_date: date | None = None
    start_time: time | None = None
    end_time: time | None = None
    timezone: str | None = None
    location: str | None = None
    virtual_reference: str | None = None
    meeting_owner: str | None = None
    recorder: str | None = None
    chair: str | None = None
    status: MeetingStatus = MeetingStatus.PLANNED
    source_document_ids: tuple[str, ...] = ()
    current_record_revision_id: str | None = None
    previous_meeting_id: str | None = None
    next_meeting_id: str | None = None
    attendees: tuple[MeetingAttendee, ...] = ()
    next_meeting_date: date | None = None
    created_at: datetime
    updated_at: datetime
    schema_version: str = "1"


class MeetingRecordRevision(FrozenModel):
    id: str
    meeting_id: str
    project_id: str
    source_document_id: str
    revision_number: int = Field(ge=1)
    content_hash: str
    record_type: RecordType
    created_by: str
    created_at: datetime
    approved_at: datetime | None = None
    supersedes_revision_id: str | None = None
    superseded_by_revision_id: str | None = None
    extraction_version: str = "meeting-deterministic-1"
    current_status: str = "ingested"


class MeetingAgendaItem(FrozenModel):
    id: str
    sequence: int = Field(ge=1)
    heading: str
    status: str = "discussed"
    citation: MeetingEvidenceReference


class DueDateCandidate(FrozenModel):
    original_text: str
    parsed_date: date | None = None
    interpretation_method: str
    reference_date: date | None = None
    ambiguous: bool = False
    human_confirmed: bool = False


class ExtractedMeetingItem(FrozenModel):
    id: str
    project_id: str
    meeting_id: str
    record_revision_id: str
    item_type: MeetingItemType
    title: str
    description: str
    owner_candidate: str | None = None
    organization_candidate: str | None = None
    due_date_candidate: DueDateCandidate | None = None
    priority_candidate: str | None = None
    topic_reference: str | None = None
    citations: tuple[MeetingEvidenceReference, ...]
    related_identifiers: tuple[str, ...] = ()
    extraction_strength: float = Field(ge=0, le=1)
    extraction_reason: str
    ambiguities: tuple[str, ...] = ()
    human_review_required: bool = True
    review_status: ReviewStatus = ReviewStatus.UNREVIEWED
    original_candidate_id: str | None = None


class WorkflowLink(FrozenModel):
    id: str
    workflow_type: str
    reference: str
    relationship: str = "related_to"
    created_at: datetime
    created_by: str


class ProjectAction(FrozenModel):
    id: str
    project_id: str
    source_meeting_id: str | None = None
    source_record_revision_id: str | None = None
    source_candidate_id: str | None = None
    title: str
    description: str
    owner_id: str | None = None
    owner_name: str | None = None
    organization: str | None = None
    secondary_owners: tuple[str, ...] = ()
    due_date: date | None = None
    original_due_date_text: str | None = None
    priority: str = "normal"
    status: ActionStatus = ActionStatus.NEW
    discipline: str | None = None
    topic: str | None = None
    dependencies: tuple[str, ...] = ()
    links: tuple[WorkflowLink, ...] = ()
    citations: tuple[MeetingEvidenceReference, ...] = ()
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None
    completion_evidence: str | None = None
    resolution_note: str | None = None
    carry_forward_count: int = Field(default=0, ge=0)
    last_mentioned_meeting_id: str | None = None
    tags: tuple[str, ...] = ()
    version: int = Field(default=1, ge=1)
    schema_version: str = "1"


class ProjectDecision(FrozenModel):
    id: str
    project_id: str
    meeting_id: str | None = None
    record_revision_id: str | None = None
    source_candidate_id: str | None = None
    decision_text: str
    decision_type: str = "other"
    authority: str | None = None
    decision_date: date | None = None
    status: DecisionStatus = DecisionStatus.PENDING_CONFIRMATION
    citations: tuple[MeetingEvidenceReference, ...] = ()
    links: tuple[WorkflowLink, ...] = ()
    supersedes_decision_id: str | None = None
    superseded_by_decision_id: str | None = None
    reviewer_id: str | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class MeetingCommitment(FrozenModel):
    id: str
    project_id: str
    meeting_id: str
    committing_party: str | None = None
    description: str
    due_date: date | None = None
    related_action_id: str | None = None
    citation: MeetingEvidenceReference
    confirmation_status: ReviewStatus = ReviewStatus.UNREVIEWED
    fulfillment_status: str = "open"


class MeetingDependency(FrozenModel):
    id: str
    project_id: str
    meeting_id: str
    source_item_id: str
    target_reference: str | None = None
    relationship: str = "depends_on"
    citation: MeetingEvidenceReference
    evidence_strength: float = Field(ge=0, le=1)
    human_confirmed: bool = False


class DecisionConflict(FrozenModel):
    id: str
    project_id: str
    decision_ids: tuple[str, str]
    status: str = "possible_conflict"
    explanation: str
    human_resolution_required: bool = True


class MinutesRevision(FrozenModel):
    id: str
    project_id: str
    meeting_id: str
    revision_number: int
    status: MinutesStatus
    markdown: str
    content_hash: str
    created_at: datetime
    created_by: str
    approved_at: datetime | None = None
    issued_at: datetime | None = None
    supersedes_revision_id: str | None = None


class MeetingItemChange(FrozenModel):
    change_type: str
    summary: str
    old_citation: MeetingEvidenceReference | None = None
    new_citation: MeetingEvidenceReference | None = None


class MeetingRecordComparison(FrozenModel):
    id: str
    project_id: str
    old_record_revision_id: str
    new_record_revision_id: str
    changes: tuple[MeetingItemChange, ...]
    created_at: datetime


class AuditEvent(FrozenModel):
    id: str
    project_id: str
    event_type: str
    subject_id: str
    actor_id: str
    created_at: datetime
    metadata: dict[str, str] = {}


class NotificationRequest(FrozenModel):
    id: str
    project_id: str
    event_type: str
    subject_id: str
    summary: str
    created_at: datetime
    status: str = "pending_local_delivery"


class MeetingAnalysis(FrozenModel):
    record_revision_id: str
    agenda: tuple[MeetingAgendaItem, ...] = ()
    candidates: tuple[ExtractedMeetingItem, ...] = ()
    metadata_candidates: tuple[MeetingMetadataCandidate, ...] = ()
    attendees: tuple[MeetingAttendee, ...] = ()
    organizations: tuple[MeetingOrganization, ...] = ()
    analyzed_at: datetime
    analyzer_version: str = "meeting-deterministic-1"
    parser_version: str = "1"
    date_parser_version: str = "1"
    model_provider: str | None = None
    external_provider_used: bool = False
    warnings: tuple[str, ...] = ()


class ActionDashboard(FrozenModel):
    total_open: int
    unassigned: int
    due_today: int
    due_soon: int
    overdue: int
    blocked: int
    waiting: int
    repeatedly_carried: int
    decisions_awaiting_confirmation: int
    conflicts: int
    actions: tuple[ProjectAction, ...]
