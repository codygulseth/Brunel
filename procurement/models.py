"""Canonical, project-scoped procurement records."""

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ProcurementCategory(StrEnum):
    ELECTRICAL_EQUIPMENT = "electrical_equipment"
    MECHANICAL_EQUIPMENT = "mechanical_equipment"
    GENERATORS = "generators"
    SWITCHGEAR = "switchgear"
    TRANSFORMERS = "transformers"
    UPS = "UPS"
    BATTERIES = "batteries"
    CONTROLS = "controls"
    TELECOM = "telecom"
    SECURITY = "security"
    FIRE_ALARM = "fire_alarm"
    FIRE_PROTECTION = "fire_protection"
    STRUCTURAL_STEEL = "structural_steel"
    PRECAST = "precast"
    CONCRETE_MATERIALS = "concrete_materials"
    ROOFING = "roofing"
    GLAZING = "glazing"
    DOORS_AND_HARDWARE = "doors_and_hardware"
    ELEVATORS = "elevators"
    SPECIALTY_EQUIPMENT = "specialty_equipment"
    OWNER_FURNISHED_EQUIPMENT = "owner_furnished_equipment"
    TEMPORARY_EQUIPMENT = "temporary_equipment"
    COMMISSIONING_EQUIPMENT = "commissioning_equipment"
    SPARE_PARTS = "spare_parts"
    CLOSEOUT_MATERIALS = "closeout_materials"
    OTHER = "other"


class ProcurementStatus(StrEnum):
    CANDIDATE = "candidate"
    PLANNED = "planned"
    AWAITING_INFORMATION = "awaiting_information"
    AWAITING_SUBMITTAL = "awaiting_submittal"
    SUBMITTAL_IN_REVIEW = "submittal_in_review"
    AWAITING_APPROVAL = "awaiting_approval"
    READY_FOR_RELEASE = "ready_for_release"
    RELEASE_PENDING_AUTHORIZATION = "release_pending_authorization"
    RELEASED = "released"
    IN_FABRICATION = "in_fabrication"
    FACTORY_TESTING = "factory_testing"
    READY_TO_SHIP = "ready_to_ship"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    INSPECTION_PENDING = "inspection_pending"
    ACCEPTED = "accepted"
    STORED = "stored"
    INSTALLATION_READY = "installation_ready"
    INSTALLED = "installed"
    CLOSED = "closed"
    BLOCKED = "blocked"
    ON_HOLD = "on_hold"
    CANCELLED = "cancelled"
    SUPERSEDED = "superseded"


class ProcurementPriority(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class ExposureLevel(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATIONAL = "informational"
    UNKNOWN = "unknown"


class EvidenceReference(FrozenModel):
    source_type: str
    source_id: str
    document_id: str | None = None
    document_name: str | None = None
    page_number: int | None = Field(default=None, ge=1)
    chunk_id: str | None = None
    exact_excerpt: str | None = None
    evidence_type: str


class ProcurementCandidate(FrozenModel):
    id: str
    project_id: str
    proposed_title: str
    description: str
    category: ProcurementCategory = ProcurementCategory.OTHER
    user_category: str | None = None
    discipline: str | None = None
    equipment_tag: str | None = None
    manufacturer_candidate: str | None = None
    product_candidate: str | None = None
    quantity_candidate: str | None = None
    responsible_scope_candidate: str | None = None
    lead_time_candidate: str | None = None
    required_on_site_candidate: date | None = None
    dependencies: tuple[str, ...] = ()
    citations: tuple[EvidenceReference, ...]
    extraction_reasons: tuple[str, ...]
    evidence_strength: float = Field(ge=0, le=1)
    review_status: str = "unreviewed"
    reviewer: str | None = None
    reviewed_at: datetime | None = None
    linked_item_id: str | None = None
    human_review_required: bool = True
    created_at: datetime


class LeadTimeEvidence(FrozenModel):
    id: str
    project_id: str
    procurement_item_id: str
    duration: int = Field(gt=0)
    unit: str
    definition: str
    calendar_basis: str = "calendar_days"
    source_type: str
    citation: EvidenceReference | None = None
    provided_by: str | None = None
    effective_date: date | None = None
    expiration_date: date | None = None
    evidence_strength: float = Field(default=0.5, ge=0, le=1)
    confirmed: bool = False
    planning_assumption: bool = True
    supersedes_id: str | None = None
    active: bool = False
    notes: str | None = None
    created_at: datetime

    @property
    def calendar_days(self) -> int:
        return self.duration * 7 if self.unit == "weeks" else self.duration


class RequiredOnSiteRecord(FrozenModel):
    id: str
    value: date
    basis: str
    citation: EvidenceReference | None = None
    confirmed: bool = False
    planning_assumption: bool = True
    effective_date: date | None = None
    supersedes_id: str | None = None


class ProcurementDatePlan(FrozenModel):
    id: str
    project_id: str
    procurement_item_id: str
    required_on_site_date: date | None
    latest_ship_date: date | None = None
    latest_ready_to_ship_date: date | None = None
    latest_fabrication_start: date | None = None
    latest_release_date: date | None = None
    latest_approval_date: date | None = None
    latest_submit_date: date | None = None
    current_float_days: int | None = None
    inputs: dict[str, Any]
    missing_inputs: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    policy_version: str = "procurement-calendar-1"
    calendar_mode: str = "calendar_days"
    calculated_at: datetime


class ProcurementMilestone(FrozenModel):
    id: str
    milestone_type: str
    planned_date: date | None = None
    forecast_date: date | None = None
    actual_date: date | None = None
    status: str = "planned"
    source: str = "human_entry"
    evidence: tuple[EvidenceReference, ...] = ()
    responsible_party: str | None = None
    notes: str | None = None
    human_confirmed: bool = False


class ProcurementDependency(FrozenModel):
    id: str
    dependency_type: str
    target_reference: str
    relationship: str = "blocked_by"
    required_date: date | None = None
    status: str = "open"
    evidence: tuple[EvidenceReference, ...] = ()
    human_confirmed: bool = False


class ProcurementForecast(FrozenModel):
    id: str
    forecast_delivery_date: date | None = None
    forecast_release_date: date | None = None
    confidence: str = "insufficient"
    basis: str
    evidence: tuple[EvidenceReference, ...] = ()
    assumptions: tuple[str, ...] = ()
    created_by: str
    created_at: datetime
    supersedes_id: str | None = None
    human_confirmed: bool = False


class ExposureAssessment(FrozenModel):
    id: str
    level: ExposureLevel
    exposure_types: tuple[str, ...]
    reasons: tuple[str, ...]
    evidence_strength: str
    forecast_confidence: str
    confirmed_project_delay: bool = False
    human_review_required: bool = True
    assessed_at: datetime
    policy_version: str = "procurement-exposure-1"


class ReleaseAuthorization(FrozenModel):
    id: str
    status: str
    authorized_by: str
    reference: str
    created_at: datetime
    expires_at: datetime | None = None


class DeliveryRecord(FrozenModel):
    id: str
    status: str
    delivery_date: date
    quantity_delivered: float | None = None
    partial: bool = False
    damage_noted: bool = False
    missing_items: str | None = None
    receiving_party: str | None = None
    accepted: bool = False
    storage_location: str | None = None
    evidence: tuple[EvidenceReference, ...] = ()
    recorded_by: str
    created_at: datetime


class ProcurementItem(FrozenModel):
    id: str
    project_id: str
    procurement_number: str
    title: str
    description: str = ""
    category: ProcurementCategory = ProcurementCategory.OTHER
    user_category: str | None = None
    discipline: str | None = None
    equipment_tag: str | None = None
    responsible_subcontractor: str | None = None
    supplier: str | None = None
    manufacturer: str | None = None
    product: str | None = None
    model_number: str | None = None
    quantity: float | None = None
    unit: str | None = None
    priority: ProcurementPriority = ProcurementPriority.NORMAL
    criticality: str = "normal"
    status: ProcurementStatus = ProcurementStatus.PLANNED
    required_on_site: RequiredOnSiteRecord | None = None
    active_lead_time_id: str | None = None
    lead_times: tuple[LeadTimeEvidence, ...] = ()
    date_plans: tuple[ProcurementDatePlan, ...] = ()
    milestones: tuple[ProcurementMilestone, ...] = ()
    dependencies: tuple[ProcurementDependency, ...] = ()
    forecasts: tuple[ProcurementForecast, ...] = ()
    exposure_assessments: tuple[ExposureAssessment, ...] = ()
    release_authorizations: tuple[ReleaseAuthorization, ...] = ()
    deliveries: tuple[DeliveryRecord, ...] = ()
    related_submittal_ids: tuple[str, ...] = ()
    related_rfi_ids: tuple[str, ...] = ()
    related_change_ids: tuple[str, ...] = ()
    related_meeting_action_ids: tuple[str, ...] = ()
    related_drawing_ids: tuple[str, ...] = ()
    schedule_activity_ids: tuple[str, ...] = ()
    citations: tuple[EvidenceReference, ...] = ()
    stale_status: str = "current"
    staleness_reasons: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    created_at: datetime
    updated_at: datetime
    version: int = Field(default=1, ge=1)
    schema_version: str = "1"


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


class ProcurementPlanRevision(FrozenModel):
    id: str
    project_id: str
    item_versions: dict[str, int]
    item_snapshots: dict[str, dict[str, Any]]
    content_hash: str
    created_by: str
    created_at: datetime
    configuration_version: str = "1"
    notes: str | None = None


class ProcurementItemChange(FrozenModel):
    item_id: str
    procurement_number: str
    change_type: str
    field: str | None = None
    old_value: Any = None
    new_value: Any = None
    human_review_required: bool = True


class ProcurementPlanComparison(FrozenModel):
    id: str
    project_id: str
    old_plan_id: str
    new_plan_id: str
    changes: tuple[ProcurementItemChange, ...]
    created_at: datetime


class ProcurementDashboard(FrozenModel):
    project_id: str
    total_active: int
    status_counts: dict[str, int]
    exposure_counts: dict[str, int]
    critical_items: int
    missing_lead_times: int
    missing_required_on_site: int
    pending_authorization: int
    overdue_milestones: int
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
