from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ReviewStatus(StrEnum):
    PROPOSED = "proposed"
    UNDER_REVIEW = "under_review"
    CONFIRMED_FOR_TRACKING = "confirmed_for_tracking"
    SATISFIED_AS_CONFIRMED = "satisfied_as_confirmed"
    WAIVED_AS_RECORDED = "waived_as_recorded"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    VOIDED = "voided"


class Evidence(Frozen):
    record_type: str
    record_id: str
    citation: dict[str, Any]
    exact_text: str
    source_date: date | None = None
    human_confirmed: bool = False


class ContractDocument(Frozen):
    id: str
    project_id: str
    source_document_revision_id: str
    contract_relationship_id: str | None = None
    document_type: str
    title: str
    parties_as_stated: tuple[str, ...] = ()
    effective_date_as_stated: date | None = None
    execution_date_as_stated: date | None = None
    revision: int = 1
    supersedes_id: str | None = None
    incorporation_references: tuple[str, ...] = ()
    precedence_language_as_stated: str | None = None
    review_status: ReviewStatus = ReviewStatus.PROPOSED
    evidence: tuple[Evidence, ...]


class ContractRelationship(Frozen):
    id: str
    project_id: str
    parties: tuple[str, ...]
    roles_as_stated: dict[str, str]
    agreement_document_id: str | None = None
    notice_recipients_as_stated: tuple[str, ...] = ()
    governing_document_ids: tuple[str, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    reviewer_disposition: str | None = None


class HierarchyEdge(Frozen):
    id: str
    project_id: str
    source_document_id: str
    target_document_id: str
    relationship: str
    source_language: str
    citation: Evidence
    confidence: float = Field(ge=0, le=1)
    uncertainty: tuple[str, ...] = ()
    reviewer_status: ReviewStatus = ReviewStatus.PROPOSED


class Clause(Frozen):
    id: str
    project_id: str
    document_id: str
    document_revision: int
    clause_number: str
    heading: str | None = None
    full_source_text: str
    normalized_summary: str
    category: str = "unknown"
    parent_clause_id: str | None = None
    defined_terms: tuple[str, ...] = ()
    cross_references: tuple[str, ...] = ()
    applicable_party_as_stated: str | None = None
    triggering_event: str | None = None
    required_action: str | None = None
    time_period: str | None = None
    required_recipient: str | None = None
    delivery_method: str | None = None
    consequence_as_stated: str | None = None
    citation: Evidence
    confidence: float = Field(ge=0, le=1)
    uncertainty: tuple[str, ...] = ()
    review_status: ReviewStatus = ReviewStatus.PROPOSED


class DefinedTerm(Frozen):
    id: str
    project_id: str
    term: str
    definition: str
    document_id: str
    clause_id: str
    citation: Evidence
    conflicting_definition_ids: tuple[str, ...] = ()
    review_status: ReviewStatus = ReviewStatus.PROPOSED


class ContractRequirement(Frozen):
    id: str
    project_id: str
    relationship_id: str | None = None
    title: str
    description: str
    obligated_party_as_stated: str | None = None
    receiving_party_as_stated: str | None = None
    triggering_event: str | None = None
    required_action: str | None = None
    required_content: tuple[str, ...] = ()
    required_recipient: str | None = None
    delivery_method: str | None = None
    time_limit: int | None = None
    calendar_basis: str | None = None
    clause_id: str
    citation: Evidence
    confidence: float = Field(ge=0, le=1)
    uncertainty: tuple[str, ...] = ()
    status: ReviewStatus = ReviewStatus.PROPOSED
    owner: str | None = None
    workflow_links: tuple[dict[str, str], ...] = ()


class DeadlineCalculation(Frozen):
    id: str
    project_id: str
    requirement_id: str
    trigger_date: date | None
    calendar_basis: str | None
    direction: str = "after"
    period_days: int | None
    included_dates: tuple[date, ...] = ()
    excluded_dates: tuple[date, ...] = ()
    calculated_date: date | None = None
    explanation: str
    uncertainty: tuple[str, ...] = ()
    review_required: bool = True
    reviewer_confirmed: bool = False


class NoticeCandidate(Frozen):
    id: str
    project_id: str
    requirement_id: str
    event_record_id: str
    notice_type: str
    recipient_as_stated: str | None = None
    delivery_method_as_stated: str | None = None
    candidate_deadline_id: str | None = None
    evidence: tuple[Evidence, ...]
    conflicts: tuple[str, ...] = ()
    uncertainty: tuple[str, ...] = ()
    status: ReviewStatus = ReviewStatus.PROPOSED
    human_review_required: bool = True


class NoticeDraftRevision(Frozen):
    revision: int
    subject: str
    factual_chronology: tuple[str, ...]
    contract_evidence: tuple[Evidence, ...]
    project_evidence: tuple[Evidence, ...]
    reservation_language: str | None = None
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class NoticeDraft(Frozen):
    id: str
    project_id: str
    candidate_id: str
    sender: str
    recipient: str
    revisions: tuple[NoticeDraftRevision, ...]
    internal_review_status: ReviewStatus = ReviewStatus.PROPOSED
    approved_for_issue_as_recorded: bool = False
    issued_as_recorded: bool = False
    external_delivery_performed: bool = False


class Obligation(Frozen):
    id: str
    project_id: str
    requirement_id: str
    source_record_type: str
    source_record_id: str
    title: str
    owner: str | None = None
    due_date: date | None = None
    status: str = "appears_pending"
    recurrence: str | None = None
    completion_evidence: tuple[Evidence, ...] = ()
    uncertainty: tuple[str, ...] = ()


class ContractEvent(Frozen):
    id: str
    project_id: str
    event_type: str
    description: str
    source_reported_start: date | None = None
    source_reported_end: date | None = None
    linked_record_ids: tuple[str, ...] = ()
    evidence: tuple[Evidence, ...]
    conflicting_evidence: tuple[Evidence, ...] = ()
    reviewer_disposition: str | None = None
    legal_conclusion: bool = False


class Correspondence(Frozen):
    id: str
    project_id: str
    sender: str
    recipients: tuple[str, ...]
    subject: str
    correspondence_date: date
    related_record_ids: tuple[str, ...] = ()
    evidence: tuple[Evidence, ...]
    issued_as_recorded: bool = False
    external_delivery_performed: bool = False


class ConflictFinding(Frozen):
    id: str
    project_id: str
    category: str
    record_ids: tuple[str, ...]
    conflicting_language: tuple[str, ...]
    citations: tuple[Evidence, ...]
    confidence: float = Field(ge=0, le=1)
    uncertainty: tuple[str, ...]
    human_review_required: bool = True


class ChronologyEntry(Frozen):
    id: str
    project_id: str
    event_date: date
    source_date: date | None
    record_type: str
    record_id: str
    description: str
    citations: tuple[Evidence, ...]
    uncertainty: tuple[str, ...] = ()


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


class ContractDashboard(Frozen):
    project_id: str
    documents: int
    clauses_awaiting_review: int
    notice_candidates: int
    obligations_active: int
    obligations_overdue: int
    obligations_without_owner: int
    conflicts: int
    events_awaiting_review: int
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
