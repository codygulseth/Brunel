"""Validated retrieval and grounded-answer records."""

from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from document_processing.models import CitationReference, DocumentChunk, DocumentType


class AnswerStatus(StrEnum):
    ANSWERED = "answered"
    PARTIALLY_ANSWERED = "partially_answered"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    FAILED = "failed"


class EvidenceLevel(StrEnum):
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    INSUFFICIENT = "insufficient"
    CONFLICTING = "conflicting"


class ProjectQuestion(BaseModel):
    model_config = ConfigDict(frozen=True)

    project_id: str = Field(min_length=1)
    question: str = Field(min_length=2)

    @field_validator("project_id", mode="before")
    @classmethod
    def stringify_project_id(cls, value: str | UUID) -> str:
        return str(value)


class RetrievalFilters(BaseModel):
    model_config = ConfigDict(frozen=True)

    document_type: DocumentType | None = None
    document_id: str | None = None
    page_number: int | None = Field(default=None, ge=1)
    sheet_number: str | None = None
    specification_section: str | None = None


class RetrievalQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    project_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    limit: int = Field(default=10, ge=1, le=100)
    minimum_relevance: float = Field(default=0.05, ge=0, le=1)
    filters: RetrievalFilters = RetrievalFilters()

    @field_validator("project_id", mode="before")
    @classmethod
    def stringify_project_id(cls, value: str | UUID) -> str:
        return str(value)


class RetrievedEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    chunk: DocumentChunk
    document_title: str | None = None
    document_type: DocumentType
    relevance_score: float = Field(ge=0, le=1)
    matched_terms: tuple[str, ...] = ()
    matched_identifiers: tuple[str, ...] = ()


class RetrievalResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    query: RetrievalQuery
    normalized_terms: tuple[str, ...]
    evidence: tuple[RetrievedEvidence, ...]
    candidates_considered: int = Field(ge=0)
    duplicates_removed: int = Field(ge=0)


class AnswerCitation(BaseModel):
    model_config = ConfigDict(frozen=True)

    citation_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    document_name: str = Field(min_length=1)
    document_title: str | None = None
    page_number: int = Field(ge=1)
    sheet_number: str | None = None
    specification_section: str | None = None
    chunk_id: str = Field(min_length=1)
    source_location: str = Field(min_length=1)
    excerpt: str = Field(min_length=1)

    @classmethod
    def from_source(
        cls,
        source: CitationReference,
        *,
        citation_id: str,
        excerpt: str,
        document_title: str | None,
    ) -> "AnswerCitation":
        return cls(
            citation_id=citation_id,
            document_id=source.document_id,
            document_name=source.document_name,
            document_title=document_title,
            page_number=source.page_number,
            sheet_number=source.sheet_number,
            specification_section=source.specification_section,
            chunk_id=source.chunk_id,
            source_location=source.source_location,
            excerpt=excerpt,
        )


class EvidenceAssessment(BaseModel):
    model_config = ConfigDict(frozen=True)

    level: EvidenceLevel
    summary: str
    reasons: tuple[str, ...] = ()
    supporting_chunk_count: int = Field(ge=0)
    exact_identifier_match: bool = False
    source_metadata_complete: bool = False
    depends_on_inference: bool = False


class AnswerDraft(BaseModel):
    """Provider output validated before citations are attached."""

    model_config = ConfigDict(frozen=True)

    answer: str = Field(min_length=1)
    status: AnswerStatus
    cited_chunk_ids: tuple[str, ...] = ()
    evidence_summary: str
    unresolved_questions: tuple[str, ...] = ()
    depends_on_inference: bool = False


class GroundedAnswer(BaseModel):
    model_config = ConfigDict(frozen=True)

    question: ProjectQuestion
    answer: str
    status: AnswerStatus
    citations: tuple[AnswerCitation, ...] = ()
    evidence_summary: str
    evidence_assessment: EvidenceAssessment
    unresolved_questions: tuple[str, ...] = ()
    retrieval_metadata: dict[str, Any] = Field(default_factory=dict)
