"""Replaceable interfaces for each document-ingestion stage."""

from pathlib import Path
from typing import Protocol

from .loaders import LoadedFile
from .models import DocumentChunk, DocumentPage, FileType, IngestedDocument, SourceDocument


class FileLoader(Protocol):
    def load(self, path: Path) -> LoadedFile: ...


class PageExtractor(Protocol):
    file_type: FileType

    def extract(self, loaded: LoadedFile, document_id: str) -> tuple[DocumentPage, ...]: ...


class DocumentChunker(Protocol):
    def chunk(
        self, document: SourceDocument, pages: tuple[DocumentPage, ...]
    ) -> tuple[DocumentChunk, ...]: ...


class DocumentRepository(Protocol):
    def save(self, ingested: IngestedDocument) -> Path: ...

    def get(self, document_id: str) -> IngestedDocument | None: ...
