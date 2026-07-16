"""Page-safe deterministic text chunking."""

from hashlib import sha256

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import CitationReference, DocumentChunk, DocumentPage, SourceDocument


class ChunkingSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    chunk_size: int = Field(default=1_500, ge=50)
    overlap: int = Field(default=200, ge=0)

    @model_validator(mode="after")
    def overlap_is_smaller_than_chunk(self) -> "ChunkingSettings":
        if self.overlap >= self.chunk_size:
            raise ValueError("overlap must be smaller than chunk_size")
        return self


class DeterministicTextChunker:
    def __init__(self, settings: ChunkingSettings | None = None) -> None:
        self.settings = settings or ChunkingSettings()

    def chunk(
        self, document: SourceDocument, pages: tuple[DocumentPage, ...]
    ) -> tuple[DocumentChunk, ...]:
        chunks: list[DocumentChunk] = []
        for page in pages:
            chunks.extend(self._chunk_page(document, page))
        return tuple(chunks)

    def _chunk_page(self, document: SourceDocument, page: DocumentPage) -> list[DocumentChunk]:
        content = page.content
        if not content.strip():
            return []
        chunks: list[DocumentChunk] = []
        start = 0
        while start < len(content):
            end = min(start + self.settings.chunk_size, len(content))
            if end < len(content):
                boundary = content.rfind(" ", start, end)
                if boundary > start:
                    end = boundary
            text = content[start:end].strip()
            if text:
                chunk_id = self._chunk_id(document.document_id, page.page_number, start, end, text)
                citation = CitationReference(
                    document_id=document.document_id,
                    document_name=document.original_filename,
                    page_number=page.page_number,
                    sheet_number=page.sheet_number or document.sheet_number,
                    specification_section=(
                        page.specification_section or document.specification_section
                    ),
                    chunk_id=chunk_id,
                    source_location=f"{document.source_path}#page={page.page_number}",
                )
                chunks.append(
                    DocumentChunk(
                        id=chunk_id,
                        document_id=document.document_id,
                        project_id=document.project_id,
                        page_number=page.page_number,
                        content=text,
                        start_offset=start,
                        end_offset=end,
                        citation=citation,
                    )
                )
            if end >= len(content):
                break
            start = max(end - self.settings.overlap, start + 1)
        return chunks

    @staticmethod
    def _chunk_id(document_id: str, page: int, start: int, end: int, content: str) -> str:
        identity = f"{document_id}\0{page}\0{start}\0{end}\0{content}".encode()
        return f"chk_{sha256(identity).hexdigest()[:24]}"
