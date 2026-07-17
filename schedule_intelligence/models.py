"""Schedule domain records preserving imported and calculated evidence separately."""

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ScheduleFileFormat(StrEnum):
    CSV = "csv"
    XML = "xml"
    XER = "xer"


class ScheduleType(StrEnum):
    BASELINE = "baseline"
    CONTRACT = "contract"
    UPDATE = "update"
    RECOVERY = "recovery"
    LOOKAHEAD = "lookahead"
    PROCUREMENT = "procurement"
    COMMISSIONING = "commissioning"
    TURNOVER = "turnover"
    SUBCONTRACTOR = "subcontractor"
    OWNER = "owner"
    INTERNAL = "internal"
    UNKNOWN = "unknown"


class ActivityType(StrEnum):
    TASK_DEPENDENT = "task_dependent"
    RESOURCE_DEPENDENT = "resource_dependent"
    LEVEL_OF_EFFORT = "level_of_effort"
    START_MILESTONE = "start_milestone"
    FINISH_MILESTONE = "finish_milestone"
    WBS_SUMMARY = "wbs_summary"
    HAMMOCK = "hammock"
    UNKNOWN = "unknown"


class ActivityStatus(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SUSPENDED = "suspended"
    ABANDONED = "abandoned"
    UNKNOWN = "unknown"


class RelationshipType(StrEnum):
    FS = "finish_to_start"
    SS = "start_to_start"
    FF = "finish_to_finish"
    SF = "start_to_finish"
    UNKNOWN = "unknown"


class Criticality(StrEnum):
    CRITICAL = "critical"
    NEAR_CRITICAL = "near_critical"
    NONCRITICAL = "noncritical"
    INDETERMINATE = "indeterminate"


class ScheduleSourceReference(FrozenModel):
    schedule_revision_id: str
    source_document_id: str
    source_filename: str
    file_format: ScheduleFileFormat
    source_table: str
    source_row: int | None = None
    source_record_key: str | None = None
    source_activity_id: str | None = None
    source_field: str | None = None
    original_value: str | None = None
    normalized_value: str | None = None
    parser_name: str
    parser_version: str
    imported_at: datetime


class ProjectSchedule(FrozenModel):
    id: str
    project_id: str
    name: str
    schedule_type: ScheduleType
    responsible_organization: str | None = None
    scheduler: str | None = None
    contract_schedule_reference: str | None = None
    baseline_revision_id: str | None = None
    current_revision_id: str | None = None
    created_at: datetime
    updated_at: datetime
    schema_version: str = "1"


class ScheduleRevision(FrozenModel):
    id: str
    schedule_id: str
    project_id: str
    source_document_id: str
    source_filename: str
    file_format: ScheduleFileFormat
    content_hash: str
    revision_label: str | None = None
    revision_number: int | None = None
    data_date: date | None = None
    planned_project_start: date | None = None
    planned_project_finish: date | None = None
    forecast_project_finish: date | None = None
    baseline_revision_id: str | None = None
    status: str = "imported"
    imported_at: datetime
    imported_by: str
    parser_name: str
    parser_version: str = "1"
    mapping_version: str = "1"
    configuration_version: str = "1"
    activity_count: int = 0
    milestone_count: int = 0
    relationship_count: int = 0
    calendar_count: int = 0
    wbs_count: int = 0
    constraint_count: int = 0
    warnings: tuple[str, ...] = ()
    supersedes_revision_id: str | None = None
    superseded_by_revision_id: str | None = None
    schema_version: str = "1"


class ScheduleCalendar(FrozenModel):
    id: str
    project_id: str
    revision_id: str
    name: str
    calendar_type: str = "project"
    hours_per_day: float | None = None
    hours_per_week: float | None = None
    workweek: tuple[int, ...] = (0, 1, 2, 3, 4)
    holidays: tuple[date, ...] = ()
    source_fields: dict[str, str] = {}
    warnings: tuple[str, ...] = ()


class ScheduleWBSNode(FrozenModel):
    id: str
    project_id: str
    revision_id: str
    parent_id: str | None = None
    name: str
    code: str
    path: str
    sequence: int = 0
    responsible_party: str | None = None
    source_fields: dict[str, str] = {}


class ScheduleRelationship(FrozenModel):
    id: str
    revision_id: str
    predecessor_id: str
    successor_id: str
    relationship_type: RelationshipType = RelationshipType.FS
    lag: float = 0
    lag_unit: str = "days"
    source_fields: dict[str, str] = {}
    citation: ScheduleSourceReference
    validation_status: str = "valid"


class ScheduleConstraint(FrozenModel):
    constraint_type: str
    constraint_date: date | None = None
    original_type: str
    source_field: str
    citation: ScheduleSourceReference


class WorkflowLink(FrozenModel):
    id: str
    workflow_type: str
    reference: str
    relationship: str
    created_by: str
    created_at: datetime
    human_confirmed: bool = True


class ScheduleActivityRevision(FrozenModel):
    id: str
    activity_identity_id: str
    project_id: str
    schedule_id: str
    schedule_revision_id: str
    source_activity_id: str
    name: str
    activity_type: ActivityType = ActivityType.UNKNOWN
    status: ActivityStatus = ActivityStatus.UNKNOWN
    wbs_id: str | None = None
    wbs_path: str | None = None
    calendar_id: str | None = None
    original_duration: float | None = None
    remaining_duration: float | None = None
    actual_duration: float | None = None
    percent_complete: float | None = Field(default=None, ge=0, le=100)
    planned_start: date | None = None
    planned_finish: date | None = None
    actual_start: date | None = None
    actual_finish: date | None = None
    early_start: date | None = None
    early_finish: date | None = None
    late_start: date | None = None
    late_finish: date | None = None
    forecast_start: date | None = None
    forecast_finish: date | None = None
    baseline_start: date | None = None
    baseline_finish: date | None = None
    source_total_float: float | None = None
    source_free_float: float | None = None
    calculated_total_float: float | None = None
    calculated_free_float: float | None = None
    constraints: tuple[ScheduleConstraint, ...] = ()
    activity_codes: dict[str, str] = {}
    location: str | None = None
    area: str | None = None
    building: str | None = None
    floor: str | None = None
    discipline: str | None = None
    responsible_party: str | None = None
    equipment_tags: tuple[str, ...] = ()
    source_fields: dict[str, str]
    citation: ScheduleSourceReference
    workflow_links: tuple[WorkflowLink, ...] = ()
    human_confirmed: bool = False
    warnings: tuple[str, ...] = ()
    schema_version: str = "1"


class ScheduleQualityIssue(FrozenModel):
    id: str
    category: str
    severity: str
    code: str
    message: str
    activity_id: str | None = None
    human_review_required: bool = True


class ScheduleQualityAssessment(FrozenModel):
    id: str
    project_id: str
    revision_id: str
    issues: tuple[ScheduleQualityIssue, ...]
    assessed_at: datetime
    policy_version: str = "schedule-quality-1"
    certification: bool = False


class ScheduleCalculationResult(FrozenModel):
    id: str
    revision_id: str
    supported: bool
    approximate: bool = False
    calendar_mode: str | None = None
    calculated_metrics: dict[str, dict[str, Any]] = {}
    warnings: tuple[str, ...] = ()
    policy_version: str = "schedule-cpm-1"
    calculated_at: datetime


class CriticalityAssessment(FrozenModel):
    activity_revision_id: str
    classification: Criticality
    method: str
    metric_value: float | None = None
    critical_threshold: float = 0
    near_critical_threshold: float = 20
    evidence_strength: str = "moderate"
    warnings: tuple[str, ...] = ()
    policy_version: str = "criticality-1"


class ActivityLineage(FrozenModel):
    id: str
    project_id: str
    old_activity_revision_id: str | None = None
    new_activity_revision_id: str | None = None
    status: str
    confidence: float = Field(ge=0, le=1)
    reasons: tuple[str, ...]
    candidates: tuple[str, ...] = ()
    reviewer: str | None = None
    reviewed_at: datetime | None = None


class ScheduleActivityChange(FrozenModel):
    id: str
    activity_identity_id: str
    old_activity_revision_id: str | None = None
    new_activity_revision_id: str | None = None
    change_types: tuple[str, ...]
    summary: str
    old_citation: ScheduleSourceReference | None = None
    new_citation: ScheduleSourceReference | None = None
    human_review_required: bool = True


class ScheduleRevisionComparison(FrozenModel):
    id: str
    project_id: str
    schedule_id: str
    old_revision_id: str
    new_revision_id: str
    changes: tuple[ScheduleActivityChange, ...]
    project_finish_change_days: int | None = None
    created_at: datetime
    policy_version: str = "schedule-compare-1"
    limitations: tuple[str, ...] = ()


class FloatHistoryRecord(FrozenModel):
    project_id: str
    id: str
    activity_identity_id: str
    revision_id: str
    data_date: date | None = None
    source_total_float: float | None = None
    calculated_total_float: float | None = None
    source_free_float: float | None = None
    calculated_free_float: float | None = None
    criticality: Criticality = Criticality.INDETERMINATE
    policy_version: str = "criticality-1"


class MilestoneVarianceRecord(FrozenModel):
    id: str
    project_id: str
    activity_identity_id: str
    revision_id: str
    baseline_date: date | None = None
    prior_forecast: date | None = None
    current_forecast: date | None = None
    actual_date: date | None = None
    variance_from_baseline_days: int | None = None
    variance_from_prior_days: int | None = None
    baseline_type: str = "planning_target"
    human_confirmed: bool = False


class SynchronizationProposal(FrozenModel):
    id: str
    project_id: str
    revision_id: str
    activity_revision_id: str
    workflow_type: str
    workflow_reference: str
    existing_date: date | None = None
    proposed_date: date
    difference_days: int | None = None
    relationship: str
    evidence: ScheduleSourceReference
    potential_consequence: str
    review_status: str = "pending"
    reviewer: str | None = None
    reviewed_at: datetime | None = None
    downstream_updated: bool = False


class ScheduleExposure(FrozenModel):
    id: str
    project_id: str
    revision_id: str
    activity_revision_id: str | None = None
    level: str
    exposure_types: tuple[str, ...]
    reasons: tuple[str, ...]
    evidence_strength: str
    confirmed_impact: bool = False
    causation_established: bool = False
    entitlement_established: bool = False


class AuditEvent(FrozenModel):
    id: str
    project_id: str
    event_type: str
    subject_id: str
    actor: str
    created_at: datetime
    metadata: dict[str, str] = {}


class NotificationRequest(FrozenModel):
    id: str
    project_id: str
    event_type: str
    subject_id: str
    summary: str
    created_at: datetime
    status: str = "queued_local_only"


class ScheduleDashboard(FrozenModel):
    project_id: str
    revision_id: str | None
    data_date: date | None
    total_activities: int
    status_counts: dict[str, int]
    critical: int
    near_critical: int
    negative_float: int
    quality_issues: int
    lineage_review_required: int
    pending_synchronization: int
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
