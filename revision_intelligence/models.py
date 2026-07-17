"""Validated domain records for deterministic revision comparison."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from document_processing.models import CitationReference, SourceDocument


class ComparisonStatus(StrEnum):
    READY = "ready"
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    NOT_COMPARABLE = "not_comparable"
    INSUFFICIENT_CONTENT = "insufficient_content"
    FAILED = "failed"


class BlockType(StrEnum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    NUMBERED_CLAUSE = "numbered_clause"
    BULLET = "bullet"
    TABLE_ROW = "table_row"
    DRAWING_NOTE = "drawing_note"
    UNKNOWN = "unknown"


class MatchMethod(StrEnum):
    EXACT_IDENTIFIER = "exact_identifier"
    EXACT_TEXT = "exact_text"
    NORMALIZED_TEXT = "normalized_text"
    SIMILARITY = "similarity"
    POSITIONAL = "positional"
    INFERRED = "inferred"
    UNMATCHED = "unmatched"


class ChangeType(StrEnum):
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    MOVED = "moved"
    FORMATTING_ONLY = "formatting_only"
    AMBIGUOUS = "ambiguous"
    UNCHANGED = "unchanged"


class ChangeCategory(StrEnum):
    SCOPE = "scope"
    DESIGN = "design"
    MATERIAL = "material"
    EQUIPMENT = "equipment"
    QUANTITY = "quantity"
    DIMENSION = "dimension"
    SCHEDULE = "schedule"
    PROCUREMENT = "procurement"
    COST = "cost"
    CONTRACT = "contract"
    RESPONSIBILITY = "responsibility"
    QUALITY = "quality"
    SAFETY = "safety"
    CODE = "code"
    TESTING = "testing"
    INSPECTION = "inspection"
    COMMISSIONING = "commissioning"
    APPROVAL_STATUS = "approval_status"
    ADMINISTRATIVE = "administrative"
    UNKNOWN = "unknown"


class ChangeSeverity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATIONAL = "informational"
    UNKNOWN = "unknown"


class EvidenceStrength(StrEnum):
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"


class ChangeReviewStatus(StrEnum):
    UNREVIEWED = "unreviewed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    NEEDS_INFORMATION = "needs_information"
    RESOLVED = "resolved"


class SourceSpan(BaseModel):
    model_config = ConfigDict(frozen=True)
    document_id: str
    page_number: int = Field(ge=1)
    chunk_id: str
    start_offset: int = Field(ge=0)
    end_offset: int = Field(ge=0)
    sheet_number: str | None = None
    specification_section: str | None = None
    source_text: str
    citation: CitationReference


class ComparisonUnit(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    block_type: BlockType
    normalized_text: str
    identifier: str | None = None
    order: int = Field(ge=0)
    span: SourceSpan


class BlockMatch(BaseModel):
    model_config = ConfigDict(frozen=True)
    old_unit: ComparisonUnit
    new_unit: ComparisonUnit
    method: MatchMethod
    score: float = Field(ge=0, le=1)
    ambiguous: bool = False


class AlignmentResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    matches: tuple[BlockMatch, ...] = ()
    added: tuple[ComparisonUnit, ...] = ()
    removed: tuple[ComparisonUnit, ...] = ()
    ambiguous: tuple[BlockMatch, ...] = ()


class ComparabilityAssessment(BaseModel):
    model_config = ConfigDict(frozen=True)
    comparable: bool
    score: float = Field(ge=0, le=1)
    reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    forced: bool = False


class ComparisonRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    project_id: str
    old_document_id: str
    new_document_id: str
    force: bool = False
    include_formatting: bool = False
    use_model: bool = False


class DocumentRevision(BaseModel):
    model_config = ConfigDict(frozen=True)
    document: SourceDocument
    relationship_confirmed: bool = False


class RevisionLineage(BaseModel):
    model_config = ConfigDict(frozen=True)
    project_id: str
    document_family_id: str | None = None
    revisions: tuple[DocumentRevision, ...]
    inferred: bool = False
    warnings: tuple[str, ...] = ()


class TokenDiff(BaseModel):
    model_config = ConfigDict(frozen=True)
    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    replacements: tuple[tuple[str, str], ...] = ()
    signals: tuple[str, ...] = ()


class ChangeEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)
    old_citation: CitationReference | None = None
    new_citation: CitationReference | None = None
    old_excerpt: str | None = None
    new_excerpt: str | None = None
    alignment_method: MatchMethod
    diff: TokenDiff


class ClassificationSignal(BaseModel):
    model_config = ConfigDict(frozen=True)
    rule_id: str
    category: ChangeCategory
    supporting_text: str
    strength: EvidenceStrength


class ChangeImplication(BaseModel):
    model_config = ConfigDict(frozen=True)
    statement: str
    certainty: str = "possible_implication"
    review_required: bool = True


class SignificanceAssessment(BaseModel):
    model_config = ConfigDict(frozen=True)
    severity: ChangeSeverity
    evidence_strength: EvidenceStrength
    explanation: str
    review_required: bool = True


class DocumentChange(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    change_type: ChangeType
    title: str
    categories: tuple[ChangeCategory, ...] = (ChangeCategory.UNKNOWN,)
    severity: ChangeSeverity = ChangeSeverity.UNKNOWN
    evidence_strength: EvidenceStrength = EvidenceStrength.MODERATE
    evidence: ChangeEvidence
    signals: tuple[ClassificationSignal, ...] = ()
    explanation: str
    potentially_affected_disciplines: tuple[str, ...] = ()
    potentially_affected_workflows: tuple[str, ...] = ()
    implications: tuple[ChangeImplication, ...] = ()
    review_required: bool = True
    review_status: ChangeReviewStatus = ChangeReviewStatus.UNREVIEWED
    reviewer_note: str | None = None


class ComparisonSummary(BaseModel):
    model_config = ConfigDict(frozen=True)
    total_changes: int = Field(ge=0)
    added: int = Field(ge=0)
    removed: int = Field(ge=0)
    modified: int = Field(ge=0)
    moved: int = Field(ge=0)
    ambiguous: int = Field(ge=0)
    unchanged_blocks: int = Field(ge=0)
    aligned_blocks: int = Field(ge=0)
    unchanged_percentage: float = Field(ge=0, le=100)
    executive_summary: str


class DocumentComparison(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    project_id: str
    old_document: SourceDocument
    new_document: SourceDocument
    status: ComparisonStatus
    comparability: ComparabilityAssessment
    changes: tuple[DocumentChange, ...]
    summary: ComparisonSummary
    warnings: tuple[str, ...] = ()
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    old_content_hash: str
    new_content_hash: str
    configuration_version: str = "revision-comparison-v1"
    rules_version: str = "construction-rules-v1"
    provider_metadata: dict[str, Any] = Field(default_factory=dict)
    stale: bool = False
