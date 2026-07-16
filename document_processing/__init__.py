"""Brunel's traceable, provider-neutral document-ingestion foundation."""

from .chunking import ChunkingSettings, DeterministicTextChunker
from .errors import (
    DocumentExtractionError,
    EmptyDocumentError,
    IngestionError,
    SourceFileNotFoundError,
    UnsupportedFileTypeError,
)
from .models import (
    CitationReference,
    DocumentChunk,
    DocumentPage,
    DocumentType,
    FileType,
    IngestedDocument,
    IngestionResult,
    Project,
    SourceDocument,
)
from .service import DocumentIngestionService

__all__ = [
    "ChunkingSettings",
    "CitationReference",
    "DeterministicTextChunker",
    "DocumentChunk",
    "DocumentExtractionError",
    "DocumentIngestionService",
    "DocumentPage",
    "DocumentType",
    "EmptyDocumentError",
    "FileType",
    "IngestedDocument",
    "IngestionError",
    "IngestionResult",
    "Project",
    "SourceDocument",
    "SourceFileNotFoundError",
    "UnsupportedFileTypeError",
]
