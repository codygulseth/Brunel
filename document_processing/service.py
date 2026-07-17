"""Application service coordinating Brunel's document-ingestion stages."""

import logging
from collections.abc import Callable
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path

from .chunking import DeterministicTextChunker
from .extractors import ExtractorRegistry
from .interfaces import DocumentChunker, DocumentRepository, FileLoader
from .loaders import LocalFileLoader
from .metadata import ConservativeMetadataExtractor
from .models import DocumentType, IngestedDocument, IngestionResult, SourceDocument

logger = logging.getLogger(__name__)


class DocumentIngestionService:
    def __init__(
        self,
        repository: DocumentRepository,
        *,
        loader: FileLoader | None = None,
        extractors: ExtractorRegistry | None = None,
        metadata_extractor: ConservativeMetadataExtractor | None = None,
        chunker: DocumentChunker | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.loader = loader or LocalFileLoader()
        self.extractors = extractors or ExtractorRegistry()
        self.metadata_extractor = metadata_extractor or ConservativeMetadataExtractor()
        self.chunker = chunker or DeterministicTextChunker()
        self.clock = clock or (lambda: datetime.now(UTC))

    def ingest(
        self,
        *,
        project_id: str,
        file_path: Path,
        document_type: DocumentType | None = None,
        document_family_id: str | None = None,
        document_number: str | None = None,
        discipline: str | None = None,
        title: str | None = None,
        revision: str | None = None,
        revision_sequence: int | None = None,
        revision_date: date | None = None,
        issue_date: date | None = None,
        status: str | None = None,
        sheet_number: str | None = None,
        specification_section: str | None = None,
        parent_document_id: str | None = None,
        supersedes_document_id: str | None = None,
    ) -> IngestionResult:
        if not project_id.strip():
            raise ValueError("project_id must not be empty")
        loaded = self.loader.load(file_path)
        document_id = self._document_id(project_id, loaded.filename, loaded.content_hash)
        logger.info(
            "document_ingestion_started",
            extra={
                "project_id": project_id,
                "document_id": document_id,
                "file_type": loaded.file_type,
            },
        )
        extractor = self.extractors.get(loaded.file_type)
        pages = extractor.extract(loaded, document_id)
        first_page_text = pages[0].content if pages else ""
        normalized = self.metadata_extractor.extract(
            path=loaded.path,
            file_type=loaded.file_type,
            first_page_text=first_page_text,
            document_type=document_type,
            title=title,
            revision=revision,
            revision_date=revision_date,
            sheet_number=sheet_number,
            specification_section=specification_section,
        )
        document = SourceDocument(
            project_id=project_id,
            document_id=document_id,
            original_filename=loaded.filename,
            file_type=loaded.file_type,
            document_type=normalized.document_type,
            document_family_id=document_family_id,
            document_number=document_number,
            discipline=discipline,
            title=normalized.title,
            revision=normalized.revision,
            revision_sequence=revision_sequence,
            revision_date=normalized.revision_date,
            issue_date=issue_date,
            status=status,
            sheet_number=normalized.sheet_number,
            specification_section=normalized.specification_section,
            source_path=loaded.path,
            ingestion_timestamp=self.clock(),
            content_hash=loaded.content_hash,
            parent_document_id=parent_document_id,
            supersedes_document_id=supersedes_document_id or parent_document_id,
        )
        chunks = self.chunker.chunk(document, pages)
        warnings = tuple(warning for page in pages for warning in page.extraction_warnings)
        if not pages:
            warnings = ("PDF contains no pages",)
        ingested = IngestedDocument(document=document, pages=pages, chunks=chunks)
        storage_location = self.repository.save(ingested)
        logger.info(
            "document_ingestion_completed",
            extra={
                "project_id": project_id,
                "document_id": document_id,
                "page_count": len(pages),
                "chunk_count": len(chunks),
                "warning_count": len(warnings),
            },
        )
        return IngestionResult(
            document=document,
            page_count=len(pages),
            chunk_count=len(chunks),
            warnings=warnings,
            storage_location=storage_location,
        )

    @staticmethod
    def _document_id(project_id: str, filename: str, content_hash: str) -> str:
        identity = f"{project_id.strip()}\0{filename}\0{content_hash}".encode()
        return f"doc_{sha256(identity).hexdigest()[:24]}"
