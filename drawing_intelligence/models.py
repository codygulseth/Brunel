"""Drawing-specific records attached to Brunel's canonical documents and pages."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class DrawingDiscipline(StrEnum):
    COVER = "cover"
    GENERAL = "general"
    CIVIL = "civil"
    LANDSCAPE = "landscape"
    ARCHITECTURAL = "architectural"
    INTERIORS = "interiors"
    STRUCTURAL = "structural"
    MECHANICAL = "mechanical"
    PLUMBING = "plumbing"
    FIRE_PROTECTION = "fire_protection"
    ELECTRICAL = "electrical"
    ELECTRICAL_POWER = "electrical_power"
    ELECTRICAL_LIGHTING = "electrical_lighting"
    TELECOM = "telecom"
    SECURITY = "security"
    CONTROLS = "controls"
    PROCESS = "process"
    INSTRUMENTATION = "instrumentation"
    COMMISSIONING = "commissioning"
    LIFE_SAFETY = "life_safety"
    FOOD_SERVICE = "food_service"
    EQUIPMENT = "equipment"
    VENDOR = "vendor"
    UNKNOWN = "unknown"


class DrawingReferenceType(StrEnum):
    SHEET = "sheet"
    DETAIL = "detail"
    SECTION = "section"
    ELEVATION = "elevation"
    SCHEDULE = "schedule"
    PLAN = "plan"
    DIAGRAM = "diagram"
    MATCHLINE = "matchline"
    KEYNOTE = "keynote"
    CONTINUATION = "continuation"
    TYPICAL_DETAIL = "typical_detail"
    NOTE = "note"
    UNKNOWN = "unknown"


class ReadabilityStatus(StrEnum):
    VECTOR_TEXT_READABLE = "vector_text_readable"
    PARTIALLY_READABLE = "partially_readable"
    IMAGE_ONLY = "image_only"
    OCR_RECOMMENDED = "OCR_recommended"
    UNREADABLE = "unreadable"
    RENDER_FAILED = "render_failed"
    NON_SHEET = "non_sheet"
    UNKNOWN = "unknown"


class PresenceStatus(StrEnum):
    MATCHED = "matched"
    MISSING_SHEET = "missing_sheet"
    UNINDEXED_SHEET = "unindexed_sheet"
    DUPLICATE_SHEET = "duplicate_sheet"
    TITLE_MISMATCH = "title_mismatch"
    DISCIPLINE_MISMATCH = "discipline_mismatch"
    REVISION_MISMATCH = "revision_mismatch"
    UNIDENTIFIED = "unidentified"
    UNCERTAIN = "uncertain"


class ExtractionMethod(StrEnum):
    NATIVE_PDF_TEXT = "native_pdf_text"
    OCR = "ocr"
    DRAWING_INDEX = "drawing_index"
    TITLE_BLOCK = "title_block"
    HUMAN_CONFIRMED = "human_confirmed"
    CONFIGURED = "configured"


class NormalizedBox(FrozenModel):
    x_min: float = Field(ge=0, le=1)
    y_min: float = Field(ge=0, le=1)
    x_max: float = Field(ge=0, le=1)
    y_max: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def ordered(self):
        if self.x_max <= self.x_min or self.y_max <= self.y_min:
            raise ValueError("box bounds must be ordered")
        return self


class PixelBox(FrozenModel):
    x_min: int = Field(ge=0)
    y_min: int = Field(ge=0)
    x_max: int = Field(gt=0)
    y_max: int = Field(gt=0)

    @model_validator(mode="after")
    def ordered(self):
        if self.x_max <= self.x_min or self.y_max <= self.y_min:
            raise ValueError("box bounds must be ordered")
        return self


class VisualRegion(FrozenModel):
    id: str
    project_id: str
    source_document_id: str
    drawing_set_revision_id: str
    sheet_revision_id: str | None = None
    page_number: int = Field(ge=1)
    render_width: int = Field(gt=0)
    render_height: int = Field(gt=0)
    pixel_box: PixelBox
    normalized_box: NormalizedBox
    region_type: str
    region_label: str
    render_reference: str | None = None
    text_span: str | None = None
    extraction_method: ExtractionMethod
    evidence_strength: float = Field(ge=0, le=1)
    human_confirmed: bool = False


class VisualRegionCitation(FrozenModel):
    drawing_set_revision_id: str
    sheet_revision_id: str | None = None
    sheet_number: str | None = None
    sheet_title: str | None = None
    page_number: int = Field(ge=1)
    region: VisualRegion
    extracted_text: str | None = None
    extraction_method: ExtractionMethod
    evidence_strength: float = Field(ge=0, le=1)


class TitleBlockTemplate(FrozenModel):
    id: str
    name: str
    version: str = "1"
    region: NormalizedBox
    field_regions: dict[str, NormalizedBox] = {}
    applicable_sheet_sizes: tuple[str, ...] = ()
    applicable_firms: tuple[str, ...] = ()
    priority: int = 0
    notes: str | None = None


class DrawingMetadataCandidate(FrozenModel):
    id: str
    field_name: str
    candidate_value: str
    source_text: str
    source_region: VisualRegionCitation
    extraction_method: ExtractionMethod
    confidence: float = Field(ge=0, le=1)
    alternate_values: tuple[str, ...] = ()
    human_confirmed: bool = False


class DrawingMetadataReview(FrozenModel):
    id: str
    project_id: str
    sheet_revision_id: str
    field_name: str
    action: str
    original_candidate_id: str | None = None
    authoritative_value: str | None = None
    reviewer_id: str
    reviewed_at: datetime


class DrawingIndexEntry(FrozenModel):
    id: str
    sheet_number: str
    sheet_title: str | None = None
    discipline_group: str | None = None
    revision: str | None = None
    order: int = Field(ge=1)
    citation: VisualRegionCitation


class DrawingIndex(FrozenModel):
    id: str
    drawing_set_revision_id: str
    entries: tuple[DrawingIndexEntry, ...]
    source_pages: tuple[int, ...]


class DrawingReference(FrozenModel):
    id: str
    project_id: str
    drawing_set_revision_id: str
    source_sheet_revision_id: str
    reference_type: DrawingReferenceType
    reference_label: str
    exact_text: str
    target_sheet_number: str | None = None
    target_view_number: str | None = None
    target_sheet_revision_id: str | None = None
    resolved: bool = False
    citation: VisualRegionCitation
    evidence_strength: float = Field(ge=0, le=1)
    human_review_required: bool = False


class DrawingReadabilityAssessment(FrozenModel):
    page_number: int
    status: ReadabilityStatus
    native_text_characters: int = Field(ge=0)
    native_vector_text_present: bool
    ocr_recommended: bool = False
    warnings: tuple[str, ...] = ()


class OCRTextBlock(FrozenModel):
    text: str
    box: NormalizedBox
    confidence: float = Field(ge=0, le=1)


class OCRResult(FrozenModel):
    id: str
    project_id: str
    sheet_revision_id: str
    provider: str
    provider_version: str
    configuration_version: str
    blocks: tuple[OCRTextBlock, ...]
    created_at: datetime
    successful: bool
    warnings: tuple[str, ...] = ()
    external_provider_used: bool = False


class DrawingSheet(FrozenModel):
    stable_sheet_id: str
    sheet_revision_id: str
    project_id: str
    drawing_set_revision_id: str
    source_document_id: str
    source_page_number: int = Field(ge=1)
    sheet_number: str | None = None
    original_sheet_prefix: str | None = None
    sheet_title: str | None = None
    discipline: DrawingDiscipline = DrawingDiscipline.UNKNOWN
    subdiscipline: str | None = None
    revision: str | None = None
    revision_date: date | None = None
    issue_date: date | None = None
    issue_purpose: str | None = None
    project_name: str | None = None
    project_number: str | None = None
    building: str | None = None
    area: str | None = None
    level: str | None = None
    zone: str | None = None
    designed_by: str | None = None
    drawn_by: str | None = None
    checked_by: str | None = None
    approved_by: str | None = None
    scale_text: str | None = None
    sheet_size: str | None = None
    content_hash: str
    render_reference: str | None = None
    readability: DrawingReadabilityAssessment
    metadata_candidates: tuple[DrawingMetadataCandidate, ...] = ()
    human_confirmed_fields: tuple[str, ...] = ()
    current: bool = True
    supersedes_sheet_revision_id: str | None = None
    warnings: tuple[str, ...] = ()


class DrawingSetRevision(FrozenModel):
    drawing_set_id: str
    revision_id: str
    project_id: str
    source_document_id: str
    set_title: str | None = None
    set_number: str | None = None
    issue_purpose: str | None = None
    issue_date: date | None = None
    revision_label: str | None = None
    revision_sequence: int | None = Field(None, ge=0)
    discipline_coverage: tuple[DrawingDiscipline, ...] = ()
    file_content_hash: str
    total_page_count: int = Field(ge=0)
    identified_sheet_count: int = Field(ge=0)
    unidentified_page_count: int = Field(ge=0)
    drawing_index_present: bool = False
    extraction_status: str = "complete"
    ocr_status: str = "not_requested"
    supersedes_revision_id: str | None = None
    superseded_by_revision_id: str | None = None
    current: bool = True
    created_at: datetime
    created_by: str = "system"
    schema_version: str = "1"
    analysis_version: str = "drawing-foundation-1"
    configuration_version: str = "1"
    external_providers_used: bool = False
    warnings: tuple[str, ...] = ()


class DrawingSetIssue(FrozenModel):
    id: str
    status: PresenceStatus
    message: str
    affected_sheet_revision_ids: tuple[str, ...] = ()
    citations: tuple[VisualRegionCitation, ...] = ()
    severity: str = "warning"
    evidence_strength: float = Field(ge=0, le=1)
    human_review_required: bool = True


class DrawingSetValidationResult(FrozenModel):
    revision_id: str
    issues: tuple[DrawingSetIssue, ...]
    created_at: datetime


class DrawingReferenceGraph(FrozenModel):
    revision_id: str
    node_ids: tuple[str, ...]
    edges: tuple[DrawingReference, ...]


class DrawingSetChange(FrozenModel):
    change_type: str
    sheet_number: str | None = None
    summary: str
    old_citation: VisualRegionCitation | None = None
    new_citation: VisualRegionCitation | None = None
    human_visual_review_required: bool = False


class DrawingSheetComparison(FrozenModel):
    old_sheet_revision_id: str | None = None
    new_sheet_revision_id: str | None = None
    sheet_number: str | None = None
    changes: tuple[DrawingSetChange, ...]
    native_text_changed: bool = False
    visual_or_unparsed_change: bool = False


class DrawingSetComparison(FrozenModel):
    id: str
    project_id: str
    old_revision_id: str
    new_revision_id: str
    created_at: datetime
    changes: tuple[DrawingSetChange, ...]
    sheet_comparisons: tuple[DrawingSheetComparison, ...]
    lineage: tuple[SheetLineage, ...] = ()
    warnings: tuple[str, ...] = ()


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
    created_at: datetime
    status: str = "pending_local_delivery"
    summary: str


class DrawingAnalysis(FrozenModel):
    revision: DrawingSetRevision
    sheets: tuple[DrawingSheet, ...]
    index: DrawingIndex | None = None
    references: tuple[DrawingReference, ...] = ()
    regions: tuple[VisualRegion, ...] = ()
    validation: DrawingSetValidationResult
    graph: DrawingReferenceGraph
    keynotes: tuple[DrawingKeynote, ...] = ()
    title_block_template: TitleBlockTemplate | None = None
    title_block_detection_method: str = "full_page_fallback"
    title_block_human_review_required: bool = True


# Focused supporting records kept separate from authoritative sheet metadata.
class DrawingSet(FrozenModel):
    id: str
    project_id: str
    title: str | None = None


class DrawingPage(FrozenModel):
    source_document_id: str
    page_number: int = Field(ge=1)
    render_reference: str | None = None
    readability: DrawingReadabilityAssessment


class DrawingTitleBlock(FrozenModel):
    template_id: str | None = None
    region: VisualRegion
    detection_method: str
    human_review_required: bool = False
    warnings: tuple[str, ...] = ()


class SheetIdentityAssessment(FrozenModel):
    sheet_revision_id: str
    resolved: bool
    evidence_strength: float = Field(ge=0, le=1)
    conflicts: tuple[str, ...] = ()
    human_review_required: bool = False


class DrawingIndexReconciliation(FrozenModel):
    revision_id: str
    issues: tuple[DrawingSetIssue, ...]


class OCRAssessment(FrozenModel):
    sheet_revision_id: str
    recommended: bool
    reason: str
    provider_available: bool


class KeynoteLegendEntry(FrozenModel):
    id: str
    identifier: str
    text: str
    citation: VisualRegionCitation


class KeynoteOccurrence(FrozenModel):
    id: str
    identifier: str
    sheet_revision_id: str
    citation: VisualRegionCitation
    resolved: bool = False


class DrawingKeynote(FrozenModel):
    identifier: str
    legend: KeynoteLegendEntry | None = None
    occurrences: tuple[KeynoteOccurrence, ...] = ()


class SheetLineage(FrozenModel):
    old_sheet_revision_id: str | None = None
    new_sheet_revision_id: str | None = None
    relationship: str
    evidence_strength: float = Field(ge=0, le=1)
    human_confirmed: bool = False
    human_review_required: bool = False


DrawingSheetRevision = DrawingSheet
DrawingAnalysis.model_rebuild()
DrawingSetComparison.model_rebuild()
