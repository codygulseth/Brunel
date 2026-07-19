from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ReportStatus(StrEnum):
    DRAFT = "draft"
    UNDER_REVIEW = "under_review"
    REVISIONS_REQUIRED = "revisions_required"
    APPROVED = "approved"
    ACCEPTED = "accepted"
    ISSUED_INTERNAL = "issued_internal"
    CORRECTED = "corrected"
    SUPERSEDED = "superseded"
    VOID = "void"
    VOIDED = "voided"


class SourceType(StrEnum):
    MANUAL = "manual_entry"
    STRUCTURED = "structured_import"
    PDF = "pdf_report"
    TEXT = "text_notes"
    MARKDOWN = "markdown_report"
    CORRECTED = "corrected_report"
    SUPPLEMENTAL = "supplemental_record"


class ObservationType(StrEnum):
    WEATHER = "weather"
    MANPOWER = "manpower"
    WORK = "work_performed"
    EQUIPMENT = "equipment"
    DELIVERY = "delivery"
    INSPECTION = "inspection"
    TEST = "test"
    SAFETY = "safety"
    QUALITY = "quality"
    VISITOR = "visitor"
    EVENT = "significant_event"
    CONSTRAINT = "constraint"
    DISRUPTION = "disruption"
    PHOTO = "photo"


class EvidenceReference(Frozen):
    revision_id: str
    source_document_id: str
    source_filename: str
    source_type: SourceType
    source_locator: str
    exact_excerpt: str
    record_key: str
    imported_at: datetime


class ProjectDay(Frozen):
    id: str
    project_id: str
    day: date
    timezone: str = "UTC"
    shift: str = "day"
    status: ReportStatus = ReportStatus.DRAFT
    current_report_revision_id: str | None = None
    planned_schedule_revision_id: str | None = None
    created_at: datetime
    updated_at: datetime
    schema_version: str = "1"


class DailyReport(Frozen):
    id: str
    project_id: str
    project_day_id: str
    report_number: str | None = None
    status: ReportStatus = ReportStatus.DRAFT
    current_revision_id: str | None = None
    created_at: datetime
    updated_at: datetime
    version: int = 1


class DailyReportRevision(Frozen):
    id: str
    daily_report_id: str
    project_id: str
    source_document_id: str
    source_filename: str | None = None
    revision_number: int
    content_hash: str
    source_type: SourceType
    day: date
    shift: str = "day"
    prepared_by: str | None = None
    reviewed_by: str | None = None
    issued_by: str | None = None
    created_at: datetime
    reviewed_at: datetime | None = None
    issued_at: datetime | None = None
    supersedes_revision_id: str | None = None
    superseded_by_revision_id: str | None = None
    original_text: str = ""
    metadata: dict[str, Any] = {}
    extraction_version: str = "field-deterministic-1"
    schema_version: str = "1"


class FieldObservation(Frozen):
    id: str
    project_id: str
    report_id: str
    revision_id: str
    observation_type: ObservationType
    title: str
    description: str
    status: str = "proposed"
    company: str | None = None
    trade: str | None = None
    crew: str | None = None
    headcount: int | None = None
    regular_hours: float | None = None
    overtime_hours: float | None = None
    area: str | None = None
    room: str | None = None
    system: str | None = None
    equipment_tag: str | None = None
    quantity: float | None = None
    unit: str | None = None
    percent_complete: float | None = Field(default=None, ge=0, le=100)
    delivery_status: str | None = None
    accepted: bool = False
    inspection_result: str | None = None
    severity: str | None = None
    impact_status: str = "observation_only"
    reported_start: date | None = None
    reported_end: date | None = None
    drawing_references: tuple[str, ...] = ()
    specification_references: tuple[str, ...] = ()
    workflow_links: tuple[str, ...] = ()
    citation: EvidenceReference
    human_confirmed: bool = False
    reviewer: str | None = None
    reviewed_at: datetime | None = None
    notes: tuple[str, ...] = ()
    original_proposal_id: str | None = None


class PhotoRecord(Frozen):
    id: str
    project_id: str
    revision_id: str
    file_reference: str
    content_hash: str
    capture_date: datetime | None = None
    uploaded_at: datetime
    area: str | None = None
    room: str | None = None
    system: str | None = None
    equipment_tag: str | None = None
    caption: str | None = None
    visual_region: tuple[float, float, float, float] | None = None
    human_confirmed: bool = False
    visual_analysis_used: bool = False


class ScheduleLinkProposal(Frozen):
    id: str
    project_id: str
    report_id: str
    observation_id: str
    schedule_activity_id: str
    signals: tuple[str, ...]
    strength: float = Field(ge=0, le=1)
    evidence: EvidenceReference
    review_status: str = "pending"
    reviewer: str | None = None
    reviewed_at: datetime | None = None


class ProgressProposal(Frozen):
    id: str
    project_id: str
    report_id: str
    observation_id: str
    schedule_activity_id: str
    reported_status: str
    proposed_schedule_status: str | None = None
    proposed_actual_start: date | None = None
    proposed_actual_finish: date | None = None
    proposed_percent_complete: float | None = None
    evidence: EvidenceReference
    conflicts: tuple[str, ...] = ()
    review_status: str = "pending"
    reviewer: str | None = None
    reviewed_at: datetime | None = None
    schedule_updated: bool = False


class PlannedWork(Frozen):
    id: str
    project_id: str
    report_id: str
    description: str
    planned_start: date
    planned_finish: date | None = None
    source_system: str
    schedule_activity_id: str | None = None
    commitment_id: str | None = None
    area: str | None = None
    trade: str | None = None
    contractor: str | None = None
    planned_quantity: float | None = None
    evidence: EvidenceReference | None = None
    contractually_binding: bool = False


class ReportChange(Frozen):
    change_type: str
    observation_type: str | None = None
    old_observation_id: str | None = None
    new_observation_id: str | None = None
    summary: str
    old_citation: EvidenceReference | None = None
    new_citation: EvidenceReference | None = None


class DailyReportComparison(Frozen):
    id: str
    project_id: str
    old_revision_id: str
    new_revision_id: str
    changes: tuple[ReportChange, ...]
    created_at: datetime


class WeeklyFieldSummary(Frozen):
    id: str
    project_id: str
    week_start: date
    week_end: date
    issued_report_ids: tuple[str, ...]
    metrics: dict[str, int]
    confirmed_observations: tuple[str, ...]
    limitations: tuple[str, ...]
    created_at: datetime


class FieldDashboard(Frozen):
    project_id: str
    reports_issued: int
    reports_awaiting_review: int
    total_manpower: int
    deliveries: int
    partial_or_damaged_deliveries: int
    failed_inspections: int
    open_safety: int
    open_quality: int
    open_constraints: int
    progress_proposals_pending: int
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AuditEvent(Frozen):
    id: str
    project_id: str
    event_type: str
    subject_id: str
    actor: str
    created_at: datetime
    metadata: dict[str, str] = {}


class NotificationRequest(Frozen):
    id: str
    project_id: str
    event_type: str
    subject_id: str
    summary: str
    created_at: datetime
    status: str = "queued_local_only"
