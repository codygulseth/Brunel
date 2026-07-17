"""Validated records produced by Brunel's document-ingestion pipeline."""

from datetime import date, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DocumentType(StrEnum):
    DRAWING = "drawing"
    SPECIFICATION = "specification"
    RFI = "rfi"
    SUBMITTAL = "submittal"
    MEETING_MINUTES = "meeting_minutes"
    DAILY_REPORT = "daily_report"
    CONTRACT = "contract"
    SCHEDULE = "schedule"
    CHANGE_ORDER = "change_order"
    PROCUREMENT_LOG = "procurement_log"
    SAFETY = "safety"
    COMMISSIONING = "commissioning"
    CORRESPONDENCE = "correspondence"
    OTHER = "other"
    UNKNOWN = "unknown"


class FileType(StrEnum):
    PDF = "pdf"
    TEXT = "txt"
    MARKDOWN = "md"


class Project(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    name: str | None = None


class DocumentPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    document_id: str = Field(min_length=1)
    page_number: int = Field(ge=1)
    content: str
    sheet_number: str | None = None
    specification_section: str | None = None
    extraction_warnings: tuple[str, ...] = ()


class CitationReference(BaseModel):
    model_config = ConfigDict(frozen=True)

    document_id: str = Field(min_length=1)
    document_name: str = Field(min_length=1)
    page_number: int = Field(ge=1)
    chunk_id: str = Field(min_length=1)
    source_location: str = Field(min_length=1)
    sheet_number: str | None = None
    specification_section: str | None = None


class DocumentChunk(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    page_number: int = Field(ge=1)
    content: str = Field(min_length=1)
    start_offset: int = Field(ge=0)
    end_offset: int = Field(gt=0)
    citation: CitationReference

    @model_validator(mode="after")
    def offsets_are_ordered(self) -> "DocumentChunk":
        if self.end_offset <= self.start_offset:
            raise ValueError("end_offset must be greater than start_offset")
        return self


class SourceDocument(BaseModel):
    model_config = ConfigDict(frozen=True)

    project_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    original_filename: str = Field(min_length=1)
    file_type: FileType
    document_type: DocumentType = DocumentType.UNKNOWN
    document_family_id: str | None = None
    document_number: str | None = None
    discipline: str | None = None
    title: str | None = None
    revision: str | None = None
    revision_sequence: int | None = Field(default=None, ge=0)
    revision_date: date | None = None
    issue_date: date | None = None
    status: str | None = None
    sheet_number: str | None = None
    specification_section: str | None = None
    source_path: Path
    ingestion_timestamp: datetime
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    parent_document_id: str | None = None
    supersedes_document_id: str | None = None
    superseded_by_document_id: str | None = None


class IngestedDocument(BaseModel):
    """Repository aggregate for one immutable ingestion result."""

    model_config = ConfigDict(frozen=True)

    document: SourceDocument
    pages: tuple[DocumentPage, ...]
    chunks: tuple[DocumentChunk, ...]


class IngestionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    document: SourceDocument
    page_count: int = Field(ge=0)
    chunk_count: int = Field(ge=0)
    warnings: tuple[str, ...] = ()
    storage_location: Path | None = None
