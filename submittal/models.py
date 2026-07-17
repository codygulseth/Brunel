"""Canonical evidence-backed submittal domain models."""

from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from change_workflow.models import ActorReference, ImpactCertainty, ReviewerReference
from document_processing.models import CitationReference
from revision_intelligence.models import EvidenceStrength


class SubmittalType(StrEnum):
    PRODUCT_DATA = "product_data"
    SHOP_DRAWING = "shop_drawing"
    SAMPLE = "sample"
    MOCKUP = "mockup"
    CERTIFICATE = "certificate"
    TEST_REPORT = "test_report"
    CALCULATION = "calculation"
    COORDINATION_DRAWING = "coordination_drawing"
    QUALITY_CONTROL_PLAN = "quality_control_plan"
    INSTALLATION_INSTRUCTION = "installation_instruction"
    WARRANTY = "warranty"
    OPERATION_AND_MAINTENANCE = "operation_and_maintenance"
    CLOSEOUT = "closeout"
    DELEGATED_DESIGN = "delegated_design"
    SUBSTITUTION_REQUEST = "substitution_request"
    INFORMATIONAL = "informational"
    OTHER = "other"


class RequirementCategory(StrEnum):
    ACTION = "action"
    INFORMATIONAL = "informational"
    CLOSEOUT = "closeout"
    DEFERRED = "deferred"
    DELEGATED_DESIGN = "delegated_design"


class CandidateStatus(StrEnum):
    PENDING_REVIEW = "pending_review"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    NOT_APPLICABLE = "not_applicable"
    DEFERRED = "deferred"
    MERGED = "merged"
    SPLIT = "split"


class RequirementReviewDecision(StrEnum):
    ACCEPT = "accept"
    REJECT = "reject"
    NOT_APPLICABLE = "not_applicable"
    DEFER = "defer"


class SubmittalStatus(StrEnum):
    CANDIDATE = "candidate"
    PLANNED = "planned"
    NOT_STARTED = "not_started"
    IN_PREPARATION = "in_preparation"
    PENDING_SUBCONTRACTOR = "pending_subcontractor"
    PENDING_INTERNAL_REVIEW = "pending_internal_review"
    REVISIONS_REQUIRED_INTERNAL = "revisions_required_internal"
    READY_TO_SUBMIT = "ready_to_submit"
    SUBMITTED = "submitted"
    UNDER_DESIGN_REVIEW = "under_design_review"
    APPROVED = "approved"
    APPROVED_AS_NOTED = "approved_as_noted"
    REVISE_AND_RESUBMIT = "revise_and_resubmit"
    REJECTED = "rejected"
    INFORMATIONAL_RECEIVED = "informational_received"
    SUPERSEDED = "superseded"
    PROCUREMENT_RELEASED = "procurement_released"
    CLOSED = "closed"
    VOID = "void"


class SubmittalPriority(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATIONAL = "informational"


class Criticality(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"
    UNKNOWN = "unknown"


class CompletenessStatus(StrEnum):
    COMPLETE = "complete"
    COMPLETE_WITH_WARNINGS = "complete_with_warnings"
    INCOMPLETE = "incomplete"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"


class CompletenessSeverity(StrEnum):
    BLOCKING = "blocking"
    WARNING = "warning"
    INFORMATIONAL = "informational"


class MatrixStatus(StrEnum):
    ADDRESSED = "addressed"
    PARTIALLY_ADDRESSED = "partially_addressed"
    NOT_ADDRESSED = "not_addressed"
    DEVIATION_DISCLOSED = "deviation_disclosed"
    NOT_APPLICABLE = "not_applicable"
    UNCLEAR = "unclear"


class InternalReviewDecision(StrEnum):
    APPROVED_FOR_SUBMISSION = "approved_for_submission"
    REVISIONS_REQUIRED = "revisions_required"
    REJECTED = "rejected"
    NEEDS_INFORMATION = "needs_information"


class OfficialDisposition(StrEnum):
    APPROVED = "approved"
    APPROVED_AS_NOTED = "approved_as_noted"
    REVISE_AND_RESUBMIT = "revise_and_resubmit"
    REJECTED = "rejected"
    REVIEWED = "reviewed"
    NO_EXCEPTION_TAKEN = "no_exception_taken"
    MAKE_CORRECTIONS_NOTED = "make_corrections_noted"
    INFORMATIONAL_ONLY = "informational_only"
    NOT_REVIEWED = "not_reviewed"
    VOID = "void"


class PackageReviewStatus(StrEnum):
    DRAFT = "draft"
    PENDING_INTERNAL_REVIEW = "pending_internal_review"
    REVISIONS_REQUIRED = "revisions_required"
    APPROVED_FOR_SUBMISSION = "approved_for_submission"
    ISSUED = "issued"
    RESPONSE_RECEIVED = "response_received"
    SUPERSEDED = "superseded"


class ProcurementExposureStatus(StrEnum):
    ON_TRACK = "on_track"
    APPROACHING_DEADLINE = "approaching_deadline"
    AT_RISK = "at_risk"
    OVERDUE = "overdue"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"


class StalenessStatus(StrEnum):
    CURRENT = "current"
    POTENTIALLY_STALE = "potentially_stale"
    STALE = "stale"
    SUPERSEDED = "superseded"
    REVIEW_REQUIRED = "review_required"
    UNKNOWN = "unknown"


class SubstitutionStatus(StrEnum):
    DRAFT = "draft"
    PENDING_INTERNAL_REVIEW = "pending_internal_review"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    APPROVED_WITH_CONDITIONS = "approved_with_conditions"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class SubmittalEvidenceReference(BaseModel):
    model_config = ConfigDict(frozen=True)
    citation: CitationReference
    excerpt: str = Field(min_length=1)
    evidence_type: str = "specification_requirement"


class SubmittalRequirementCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)
    schema_version: int = 1
    version: int = Field(default=1, ge=1)
    id: str
    project_id: str
    document_id: str
    specification_section: str
    specification_title: str | None = None
    paragraph_reference: str | None = None
    submittal_type: SubmittalType
    category: RequirementCategory
    description: str
    required_documentation: tuple[str, ...]
    discipline: str | None = None
    frequency_or_timing: str | None = None
    evidence_strength: EvidenceStrength = EvidenceStrength.STRONG
    warnings: tuple[str, ...] = ()
    human_review_required: bool = True
    evidence: SubmittalEvidenceReference
    status: CandidateStatus = CandidateStatus.PENDING_REVIEW
    created_at: datetime
    updated_at: datetime
    legacy_related_item_id: str | None = None


class RequirementReview(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    candidate_id: str
    decision: RequirementReviewDecision
    reviewer: ActorReference
    explanation: str
    created_at: datetime
    resulting_register_item_id: str | None = None


class SubmittalRequirement(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    candidate_id: str | None = None
    specification_section: str
    paragraph_reference: str | None = None
    submittal_type: SubmittalType
    category: RequirementCategory
    description: str
    required_documentation: tuple[str, ...]
    evidence: tuple[SubmittalEvidenceReference, ...]


class SubmittalProduct(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    project_id: str | None = None
    model_number: str | None = None
    category: str | None = None
    technical_data_references: tuple[str, ...] = ()
    warranty_metadata: dict[str, str] = Field(default_factory=dict)
    supplier: str | None = None
    country_of_origin: str | None = None
    lead_time_days: int | None = Field(default=None, ge=0)
    approved: bool = False
    substitution_status: SubstitutionStatus | None = None
    related_specification_sections: tuple[str, ...] = ()
    related_submittal_ids: tuple[str, ...] = ()
    related_procurement_item_ids: tuple[str, ...] = ()


class SubmittalManufacturer(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    project_id: str
    website: str | None = None
    contact_reference: str | None = None


class AttachmentMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    filename: str
    document_type: SubmittalType
    storage_reference: str
    content_hash: str | None = None
    signed_or_stamped: bool = False
    description: str | None = None


class ProcurementDependency(BaseModel):
    model_config = ConfigDict(frozen=True)
    required_on_site_date: date | None = None
    latest_acceptable_approval_date: date | None = None
    procurement_release_date: date | None = None
    fabrication_lead_days: int | None = Field(default=None, ge=0)
    shipping_days: int | None = Field(default=None, ge=0)
    procurement_processing_days: int | None = Field(default=None, ge=0)
    review_duration_days: int | None = Field(default=None, ge=0)
    resubmittal_duration_days: int | None = Field(default=None, ge=0)
    buffer_days: int | None = Field(default=None, ge=0)
    derived_latest_release_date: date | None = None
    derived_latest_submit_date: date | None = None
    long_lead: bool = False
    approval_dependency: bool = True
    related_procurement_action: str | None = None
    exposure_status: ProcurementExposureStatus = ProcurementExposureStatus.UNKNOWN
    calculation_basis: str = "calendar_days"


class ScheduleRelationship(BaseModel):
    model_config = ConfigDict(frozen=True)
    activity_id: str
    activity_name: str
    relationship: str
    required_approval_date: date | None = None
    required_on_site_date: date | None = None
    constraint_description: str | None = None
    source: str = "user_entered"
    confidence: str = "human_provided"


class SubmittalRegisterItem(BaseModel):
    model_config = ConfigDict(frozen=True)
    schema_version: int = 1
    version: int = Field(default=1, ge=1)
    id: str
    project_id: str
    register_number: str
    specification_section: str
    specification_title: str | None = None
    description: str
    requirements: tuple[SubmittalRequirement, ...]
    discipline: str | None = None
    responsible_subcontractor: str | None = None
    internal_reviewer: ReviewerReference | None = None
    design_reviewer: str | None = None
    required_on_site_date: date | None = None
    planned_procurement_release_date: date | None = None
    planned_submit_date: date | None = None
    actual_submit_date: date | None = None
    required_response_date: date | None = None
    actual_response_date: date | None = None
    status: SubmittalStatus = SubmittalStatus.PLANNED
    priority: SubmittalPriority = SubmittalPriority.MEDIUM
    procurement_criticality: Criticality = Criticality.UNKNOWN
    schedule_criticality: Criticality = Criticality.UNKNOWN
    lead_time_days: int | None = Field(default=None, ge=0)
    review_duration_allowance_days: int | None = Field(default=None, ge=0)
    resubmittal_allowance_days: int | None = Field(default=None, ge=0)
    drawing_references: tuple[str, ...] = ()
    locations: tuple[str, ...] = ()
    equipment_references: tuple[str, ...] = ()
    related_project_change_ids: tuple[str, ...] = ()
    related_rfi_ids: tuple[str, ...] = ()
    related_procurement_item_ids: tuple[str, ...] = ()
    related_schedule_activity_ids: tuple[str, ...] = ()
    package_ids: tuple[str, ...] = ()
    procurement: ProcurementDependency = ProcurementDependency()
    schedule_relationships: tuple[ScheduleRelationship, ...] = ()
    notes: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    created_by: ActorReference
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None = None
    legacy_related_item_id: str | None = None
    idempotency_key: str | None = None


class SubmittalPackageRevision(BaseModel):
    model_config = ConfigDict(frozen=True)
    revision: int = Field(ge=1)
    title: str
    description: str
    submitter: str
    responsible_subcontractor: str | None = None
    manufacturer: SubmittalManufacturer | None = None
    product: SubmittalProduct | None = None
    included_types: tuple[SubmittalType, ...] = ()
    attachments: tuple[AttachmentMetadata, ...] = ()
    deviations: tuple[str, ...] = ()
    drawing_references: tuple[str, ...] = ()
    related_rfi_ids: tuple[str, ...] = ()
    related_project_change_ids: tuple[str, ...] = ()
    evidence: tuple[SubmittalEvidenceReference, ...] = ()
    correction_checklist: tuple[str, ...] = ()
    content_hash: str
    created_by: ActorReference
    created_at: datetime
    change_summary: str
    internally_approved: bool = False
    issued_at: datetime | None = None


class CompletenessIssue(BaseModel):
    model_config = ConfigDict(frozen=True)
    code: str
    severity: CompletenessSeverity
    message: str
    requirement_id: str | None = None
    citation: SubmittalEvidenceReference | None = None
    blocks_routing: bool = False
    recommended_action: str


class SubmittalCompletenessAssessment(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    package_id: str
    package_revision: int
    status: CompletenessStatus
    issues: tuple[CompletenessIssue, ...]
    performed_by: ActorReference
    performed_at: datetime
    technical_compliance_determined: bool = False


class ComplianceMatrixEntry(BaseModel):
    model_config = ConfigDict(frozen=True)
    requirement_id: str
    requirement_text: str
    citation: SubmittalEvidenceReference
    submitted_evidence: tuple[str, ...] = ()
    submitted_document_references: tuple[str, ...] = ()
    status: MatrixStatus
    reviewer_note: str | None = None
    confidence: str = "deterministic"
    human_review_required: bool = True


class SubmittalInternalReview(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    package_revision: int
    round_number: int
    reviewer: ReviewerReference
    decision: InternalReviewDecision
    comments: str | None = None
    required_corrections: tuple[str, ...] = ()
    reviewed_at: datetime
    approved_content_hash: str | None = None


class SubmittalResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    package_id: str
    package_revision: int
    responding_organization: str
    responding_person: str | None = None
    date_received: date
    disposition: OfficialDisposition
    original_disposition_text: str
    review_comments: tuple[str, ...] = ()
    required_corrections: tuple[str, ...] = ()
    markup_attachments: tuple[AttachmentMetadata, ...] = ()
    drawing_references: tuple[str, ...] = ()
    specification_references: tuple[str, ...] = ()
    evidence: tuple[SubmittalEvidenceReference, ...] = ()
    supersedes_response_id: str | None = None
    official: bool = True
    created_by: ActorReference
    created_at: datetime


class SubmittalResponseAnalysis(BaseModel):
    model_config = ConfigDict(frozen=True)
    official_response_id: str | None = None
    disposition: OfficialDisposition | None = None
    required_corrections: tuple[str, ...] = ()
    conditional_approval: bool = False
    resubmittal_required: bool = False
    procurement_release_eligible: bool = False
    potential_schedule_impact: bool = False
    related_rfi_need: bool = False
    field_use_restricted: bool = False
    citations: tuple[SubmittalEvidenceReference, ...] = ()
    inference_label: str = "Brunel deterministic inference requiring human confirmation"


class SubmittalStalenessAssessment(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    status: StalenessStatus
    reasons: tuple[str, ...]
    source_references: tuple[str, ...] = ()
    assessed_by: ActorReference
    assessed_at: datetime
    prior_approval_preserved: bool = True
    human_review_required: bool = True


class SubmittalStalenessReason(BaseModel):
    model_config = ConfigDict(frozen=True)
    code: str
    description: str
    source_reference: str | None = None
    evidence: tuple[SubmittalEvidenceReference, ...] = ()


class PackageRegenerationRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    project_id: str
    package_id: str
    reason: SubmittalStalenessReason
    requested_by: ActorReference
    requested_at: datetime
    status: str = "pending_human_review"


class SubstitutionRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    specified_product: str
    proposed_substitute: str
    reason: str
    product_comparison: dict[str, str] = Field(default_factory=dict)
    cost_impact: ImpactCertainty = ImpactCertainty.UNKNOWN
    schedule_impact: ImpactCertainty = ImpactCertainty.UNKNOWN
    warranty_impact: str | None = None
    maintenance_impact: str | None = None
    required_documentation: tuple[str, ...] = ()
    evidence: tuple[SubmittalEvidenceReference, ...] = ()
    status: SubstitutionStatus = SubstitutionStatus.DRAFT
    official_decision: str | None = None


class SubmittalPackage(BaseModel):
    model_config = ConfigDict(frozen=True)
    schema_version: int = 1
    version: int = Field(default=1, ge=1)
    id: str
    project_id: str
    package_number: str
    register_item_ids: tuple[str, ...]
    current_revision: int = Field(default=1, ge=1)
    revisions: tuple[SubmittalPackageRevision, ...]
    internal_review_status: PackageReviewStatus = PackageReviewStatus.DRAFT
    official_review_status: OfficialDisposition | None = None
    completeness_assessments: tuple[SubmittalCompletenessAssessment, ...] = ()
    compliance_matrix: tuple[ComplianceMatrixEntry, ...] = ()
    internal_reviews: tuple[SubmittalInternalReview, ...] = ()
    official_responses: tuple[SubmittalResponse, ...] = ()
    staleness_assessments: tuple[SubmittalStalenessAssessment, ...] = ()
    substitution_request: SubstitutionRequest | None = None
    procurement_release_confirmed: bool = False
    created_at: datetime
    updated_at: datetime


class RequirementExtractionResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    project_id: str
    candidate_ids: tuple[str, ...]
    extracted: int
    reused: int
    provider: str = "deterministic"
    warnings: tuple[str, ...] = ()


class RequirementAdmissionResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    candidate_id: str
    decision: RequirementReviewDecision
    register_item_id: str | None = None
    duplicate_register_item_id: str | None = None


class SubmittalAuditEvent(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    project_id: str
    entity_type: str
    entity_id: str
    event_type: str
    actor: ActorReference
    timestamp: datetime
    previous_state: str | None = None
    new_state: str | None = None
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SubmittalDashboard(BaseModel):
    model_config = ConfigDict(frozen=True)
    project_id: str
    metrics: dict[str, int | float]
    by_discipline: dict[str, int] = Field(default_factory=dict)
    by_subcontractor: dict[str, int] = Field(default_factory=dict)
    by_specification_section: dict[str, int] = Field(default_factory=dict)
    oldest_outstanding: tuple[SubmittalRegisterItem, ...] = ()
