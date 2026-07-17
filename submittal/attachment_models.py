"""Immutable models for attachment content intelligence and human review."""

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from change_workflow.models import ActorReference, ReviewerReference
from document_processing.models import CitationReference
from revision_intelligence.models import EvidenceStrength

from .models import MatrixStatus, SubmittalEvidenceReference


class AttachmentType(StrEnum):
    PRODUCT_DATA = "product_data"
    SHOP_DRAWING = "shop_drawing"
    CALCULATION = "calculation"
    TEST_REPORT = "test_report"
    CERTIFICATE = "certificate"
    WARRANTY = "warranty"
    INSTALLATION_INSTRUCTION = "installation_instruction"
    MAINTENANCE_DATA = "maintenance_data"
    OPERATION_AND_MAINTENANCE = "operation_and_maintenance"
    COORDINATION_DRAWING = "coordination_drawing"
    DELEGATED_DESIGN = "delegated_design"
    SAMPLE_RECORD = "sample_record"
    LETTER = "letter"
    COVER_SHEET = "cover_sheet"
    SUBSTITUTION_REQUEST = "substitution_request"
    MARKUP = "markup"
    RESPONSE = "response"
    UNKNOWN = "unknown"


class AttachmentRole(StrEnum):
    REQUIRED_DOCUMENT = "required_document"
    SUPPORTING_DOCUMENT = "supporting_document"
    MANUFACTURER_DATA = "manufacturer_data"
    DESIGN_DOCUMENT = "design_document"
    CALCULATION_PACKAGE = "calculation_package"
    CERTIFICATION = "certification"
    REVIEWER_MARKUP = "reviewer_markup"
    PRIOR_REVISION = "prior_revision"
    SUPPLEMENTAL = "supplemental"
    UNKNOWN = "unknown"


class ReadabilityStatus(StrEnum):
    READABLE = "readable"
    READABLE_WITH_WARNINGS = "readable_with_warnings"
    PARTIALLY_READABLE = "partially_readable"
    UNREADABLE = "unreadable"
    UNSUPPORTED = "unsupported"
    ENCRYPTED = "encrypted"
    CORRUPT = "corrupt"
    UNKNOWN = "unknown"


class ExtractionStatus(StrEnum):
    COMPLETE = "complete"
    COMPLETE_WITH_WARNINGS = "complete_with_warnings"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"
    NOT_RUN = "not_run"


class DuplicateStatus(StrEnum):
    UNIQUE = "unique"
    EXACT_DUPLICATE = "exact_duplicate"
    PROBABLE_DUPLICATE = "probable_duplicate"
    PARTIAL_DUPLICATE = "partial_duplicate"
    REUSED_ATTACHMENT = "reused_attachment"
    UNCERTAIN = "uncertain"


class SupersessionStatus(StrEnum):
    CONFIRMED = "confirmed_supersession"
    PROBABLE = "probable_supersession"
    POSSIBLE = "possible_supersession"
    UNRELATED = "unrelated"


class ConflictStatus(StrEnum):
    CONFIRMED_TEXT_CONFLICT = "confirmed_text_conflict"
    PROBABLE_CONFLICT = "probable_conflict"
    CONTEXT_MAY_DIFFER = "context_may_differ"
    UNRESOLVED = "unresolved"
    HUMAN_RESOLVED = "human_resolved"


class HumanConfirmationStatus(StrEnum):
    UNREVIEWED = "unreviewed"
    CONFIRMED = "confirmed"
    MODIFIED = "modified"
    REJECTED = "rejected"
    NEEDS_INFORMATION = "needs_information"


class DeviationStatus(StrEnum):
    POSSIBLE_UNDOCUMENTED_DEVIATION = "possible_undocumented_deviation"
    DISCLOSED_DEVIATION = "disclosed_deviation"
    CONTEXT_UNCLEAR = "context_unclear"
    NO_DEVIATION_DETECTED = "no_deviation_detected"
    HUMAN_RESOLVED = "human_resolved"


class PackageAttachmentStalenessStatus(StrEnum):
    CURRENT = "current"
    POTENTIALLY_STALE = "potentially_stale"
    STALE = "stale"
    SUPERSEDED = "superseded"
    RE_REVIEW_REQUIRED = "re_review_required"
    UNKNOWN = "unknown"


class PackageChangeType(StrEnum):
    ATTACHMENT_ADDED = "attachment_added"
    ATTACHMENT_REMOVED = "attachment_removed"
    ATTACHMENT_REPLACED = "attachment_replaced"
    ATTACHMENT_MODIFIED = "attachment_modified"
    MANUFACTURER_CHANGED = "manufacturer_changed"
    PRODUCT_CHANGED = "product_changed"
    MODEL_CHANGED = "model_changed"
    RATING_CHANGED = "rating_changed"
    DIMENSION_CHANGED = "dimension_changed"
    WARRANTY_CHANGED = "warranty_changed"
    CERTIFICATION_CHANGED = "certification_changed"
    REFERENCE_CHANGED = "reference_changed"
    DEVIATION_ADDED = "deviation_added"
    DEVIATION_REMOVED = "deviation_removed"
    REQUIREMENT_STATUS_CHANGED = "requirement_status_changed"
    CONFLICT_ADDED = "conflict_added"
    CONFLICT_RESOLVED = "conflict_resolved"
    UNCHANGED = "unchanged"


class AttachmentEvidenceReference(BaseModel):
    model_config = ConfigDict(frozen=True)
    attachment_id: str
    attachment_revision_id: str
    package_id: str
    package_revision: int = Field(ge=1)
    citation: CitationReference
    excerpt: str = Field(min_length=1)
    evidence_type: str = "submitted_attachment_fact"


class AttachmentIdentity(BaseModel):
    model_config = ConfigDict(frozen=True)
    manufacturer: str | None = None
    product_family: str | None = None
    product_name: str | None = None
    model_number: str | None = None
    catalog_number: str | None = None
    series: str | None = None
    category: str | None = None
    revision: str | None = None
    publication_date: date | None = None
    contact: str | None = None
    website: str | None = None
    country_of_origin: str | None = None
    evidence: tuple[AttachmentEvidenceReference, ...] = ()
    extraction_method: str = "deterministic_text"
    strength: EvidenceStrength = EvidenceStrength.MODERATE
    candidate_alternatives: tuple[str, ...] = ()
    human_confirmed: bool = False


class AttachmentTechnicalAttribute(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    name: str
    value: str
    unit: str | None = None
    normalized_value: str | None = None
    product_context: str | None = None
    table_or_paragraph_context: str | None = None
    evidence: AttachmentEvidenceReference
    extraction_method: str = "deterministic_text"
    strength: EvidenceStrength = EvidenceStrength.MODERATE
    human_confirmed: bool = False


class AttachmentReference(BaseModel):
    model_config = ConfigDict(frozen=True)
    reference_type: str
    value: str
    source: str = "explicit_attachment_text"
    evidence: AttachmentEvidenceReference


class AttachmentQualityIssue(BaseModel):
    model_config = ConfigDict(frozen=True)
    code: str
    message: str
    page_number: int | None = None
    severity: str = "warning"


class AttachmentReadabilityAssessment(BaseModel):
    model_config = ConfigDict(frozen=True)
    status: ReadabilityStatus
    page_count: int = Field(default=0, ge=0)
    pages_successfully_extracted: int = Field(default=0, ge=0)
    pages_with_warnings: tuple[int, ...] = ()
    pages_unavailable: tuple[int, ...] = ()
    issues: tuple[AttachmentQualityIssue, ...] = ()
    explanation: str
    human_review_required: bool = True
    may_support_compliance_mapping: bool = False


class AttachmentClassification(BaseModel):
    model_config = ConfigDict(frozen=True)
    user_declared_type: AttachmentType | None = None
    inferred_type: AttachmentType = AttachmentType.UNKNOWN
    strength: str = "insufficient"
    supporting_signals: tuple[str, ...] = ()
    alternate_types: tuple[AttachmentType, ...] = ()
    disagreement: bool = False
    human_review_required: bool = True


class AttachmentDuplicateAssessment(BaseModel):
    model_config = ConfigDict(frozen=True)
    status: DuplicateStatus
    matching_attachment_ids: tuple[str, ...] = ()
    method: str = "content_hash"
    explanation: str
    content_hashes: tuple[str, ...] = ()
    page_overlap: float | None = Field(default=None, ge=0, le=1)
    recommended_action: str = "Human review; no automatic deletion or exclusion."


class AttachmentMismatchAssessment(BaseModel):
    model_config = ConfigDict(frozen=True)
    mismatch_type: str
    package_evidence: str
    attachment_evidence: AttachmentEvidenceReference | None = None
    severity: str = "warning"
    strength: EvidenceStrength = EvidenceStrength.MODERATE
    human_review_required: bool = True
    blocking: bool = False


class AttachmentSupersession(BaseModel):
    model_config = ConfigDict(frozen=True)
    prior_attachment_revision_id: str
    new_attachment_revision_id: str
    status: SupersessionStatus
    signals: tuple[str, ...]
    user_confirmed: bool = False
    human_review_required: bool = True


class AttachmentConflict(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    package_id: str
    package_revision: int
    conflict_type: str
    subject: str
    values: tuple[str, ...]
    evidence: tuple[AttachmentEvidenceReference, ...]
    status: ConflictStatus = ConflictStatus.UNRESOLVED
    explanation: str
    human_review_required: bool = True
    resolution_note: str | None = None


class PossibleDeviation(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    requirement_id: str
    attribute_name: str
    specified_value: str
    submitted_value: str
    specification_evidence: SubmittalEvidenceReference
    attachment_evidence: AttachmentEvidenceReference
    status: DeviationStatus
    disclosed: bool = False
    explanation: str
    human_review_required: bool = True


class AttachmentExtractionResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    schema_version: int = 1
    id: str
    project_id: str
    package_id: str
    package_revision: int
    attachment_id: str
    attachment_revision_id: str
    source_document_id: str | None = None
    source_content_hash: str
    extractor_name: str = "brunel-deterministic-attachment-extractor"
    extractor_version: str = "1.0"
    configuration_version: str = "attachment-extractor-v1"
    extracted_at: datetime
    extraction_status: ExtractionStatus
    readability: AttachmentReadabilityAssessment
    classification: AttachmentClassification
    identities: tuple[AttachmentIdentity, ...] = ()
    technical_attributes: tuple[AttachmentTechnicalAttribute, ...] = ()
    references: tuple[AttachmentReference, ...] = ()
    warnings: tuple[str, ...] = ()
    deterministic: bool = True
    model_provider: str | None = None
    human_confirmed: bool = False


class AttachmentRevision(BaseModel):
    model_config = ConfigDict(frozen=True)
    schema_version: int = 1
    id: str
    attachment_id: str
    project_id: str
    package_id: str
    package_revision: int = Field(ge=1)
    source_document_id: str | None = None
    original_filename: str
    display_name: str
    mime_type: str
    file_extension: str
    file_size: int = Field(ge=0)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    storage_reference: str
    user_declared_type: AttachmentType | None = None
    inferred_type: AttachmentType = AttachmentType.UNKNOWN
    role: AttachmentRole = AttachmentRole.UNKNOWN
    revision_label: str | None = None
    publication_date: date | None = None
    uploaded_at: datetime
    uploaded_by: ActorReference
    page_count: int = Field(default=0, ge=0)
    extraction_status: ExtractionStatus = ExtractionStatus.NOT_RUN
    readability_status: ReadabilityStatus = ReadabilityStatus.UNKNOWN
    extraction_result_id: str | None = None
    supersedes_attachment_revision_id: str | None = None
    superseded_by_attachment_revision_id: str | None = None
    active: bool = True


class SubmittalAttachment(BaseModel):
    model_config = ConfigDict(frozen=True)
    schema_version: int = 1
    version: int = Field(default=1, ge=1)
    id: str
    project_id: str
    package_id: str
    display_name: str
    active_revision_id: str
    revisions: tuple[AttachmentRevision, ...]
    created_at: datetime
    updated_at: datetime


class AttachmentIngestionResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    attachment: SubmittalAttachment
    revision: AttachmentRevision
    extraction: AttachmentExtractionResult | None = None
    duplicate: AttachmentDuplicateAssessment
    mismatches: tuple[AttachmentMismatchAssessment, ...] = ()
    supersession: AttachmentSupersession | None = None
    evidence_set_id: str | None = None
    warnings: tuple[str, ...] = ()


class MissingAttachmentIssue(BaseModel):
    model_config = ConfigDict(frozen=True)
    requirement_id: str
    missing_type: AttachmentType
    requirement_evidence: SubmittalEvidenceReference
    package_evidence_state: str
    blocking: bool = True
    human_review_required: bool = True
    suggested_action: str


class ComplianceMappingReview(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    reviewer: ReviewerReference
    confirmation_status: HumanConfirmationStatus
    confirmed_status: MatrixStatus | None = None
    note: str | None = None
    added_evidence: tuple[AttachmentEvidenceReference, ...] = ()
    removed_evidence_ids: tuple[str, ...] = ()
    reviewed_at: datetime


class ProposedComplianceMapping(BaseModel):
    model_config = ConfigDict(frozen=True)
    schema_version: int = 1
    id: str
    project_id: str
    package_id: str
    package_revision: int
    requirement_id: str
    specification_section: str
    specification_evidence: SubmittalEvidenceReference
    proposed_status: MatrixStatus
    proposed_explanation: str
    supporting_evidence: tuple[AttachmentEvidenceReference, ...] = ()
    missing_evidence: tuple[str, ...] = ()
    conflicting_evidence_ids: tuple[str, ...] = ()
    possible_deviation_ids: tuple[str, ...] = ()
    evidence_strength: str = "insufficient"
    extraction_version: str = "1.0"
    mapping_policy_version: str = "deterministic-cited-mapping-v1"
    human_confirmation_status: HumanConfirmationStatus = HumanConfirmationStatus.UNREVIEWED
    confirmed_status: MatrixStatus | None = None
    reviews: tuple[ComplianceMappingReview, ...] = ()
    human_review_required: bool = True


class PackageEvidenceSet(BaseModel):
    model_config = ConfigDict(frozen=True)
    schema_version: int = 1
    id: str
    project_id: str
    package_id: str
    package_revision: int
    attachment_revision_ids: tuple[str, ...]
    attachment_content_hashes: tuple[str, ...]
    extraction_result_ids: tuple[str, ...]
    requirement_ids: tuple[str, ...]
    requirement_set_version: str
    mapping_policy_version: str
    extraction_policy_version: str
    created_at: datetime
    evidence_set_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    readability_summary: dict[str, int] = Field(default_factory=dict)
    missing_attachments: tuple[MissingAttachmentIssue, ...] = ()
    conflicts: tuple[AttachmentConflict, ...] = ()
    mismatches: tuple[AttachmentMismatchAssessment, ...] = ()
    possible_deviations: tuple[PossibleDeviation, ...] = ()
    compliance_mappings: tuple[ProposedComplianceMapping, ...] = ()
    human_review_complete: bool = False
    supersedes_evidence_set_id: str | None = None


class PackageAttachmentSummary(BaseModel):
    model_config = ConfigDict(frozen=True)
    project_id: str
    package_id: str
    package_revision: int
    attachment_count: int
    active_revision_count: int
    readable_count: int
    unsupported_count: int
    duplicate_count: int
    missing_count: int
    mismatch_count: int
    conflict_count: int
    deviation_count: int
    unreviewed_mapping_count: int
    evidence_set_id: str | None = None
    evidence_set_hash: str | None = None


class PackageAttachmentStalenessAssessment(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    project_id: str
    package_id: str
    package_revision: int
    status: PackageAttachmentStalenessStatus
    reasons: tuple[str, ...]
    previous_evidence_set_hash: str | None = None
    current_evidence_set_hash: str | None = None
    assessed_by: ActorReference
    assessed_at: datetime
    prior_approval_preserved: bool = True
    official_disposition_preserved: bool = True
    human_review_required: bool = True
    acknowledged_by: ActorReference | None = None
    acknowledged_at: datetime | None = None


class AttachmentSetChange(BaseModel):
    model_config = ConfigDict(frozen=True)
    change_type: PackageChangeType
    subject: str
    old_value: str | None = None
    new_value: str | None = None
    old_evidence: tuple[AttachmentEvidenceReference, ...] = ()
    new_evidence: tuple[AttachmentEvidenceReference, ...] = ()
    human_review_required: bool = True


class PackageRevisionComparison(BaseModel):
    model_config = ConfigDict(frozen=True)
    schema_version: int = 1
    id: str
    project_id: str
    package_id: str
    old_package_revision: int
    new_package_revision: int
    old_evidence_set_id: str
    new_evidence_set_id: str
    old_evidence_set_hash: str
    new_evidence_set_hash: str
    changes: tuple[AttachmentSetChange, ...]
    summary: dict[str, int]
    re_review_required: bool
    compared_at: datetime


class AttachmentSearchResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    attachment_id: str
    attachment_revision_id: str
    package_id: str
    score: int
    excerpts: tuple[AttachmentEvidenceReference, ...]


class AttachmentQuestionAnswer(BaseModel):
    model_config = ConfigDict(frozen=True)
    answer: str
    specification_citations: tuple[SubmittalEvidenceReference, ...] = ()
    attachment_citations: tuple[AttachmentEvidenceReference, ...] = ()
    distinctions: tuple[str, ...] = ()
    sufficient: bool = False
