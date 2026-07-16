from datetime import datetime
from pathlib import Path
from typing import Protocol
from pydantic import BaseModel, ConfigDict, Field
from models import DocumentId, ProjectId


class SourceDocument(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: DocumentId
    project_id: ProjectId
    path: Path
    version: str = Field(min_length=1)
    authored_at: datetime | None = None


class ParsedDocument(BaseModel):
    model_config = ConfigDict(frozen=True)
    source: SourceDocument
    text: str
    metadata: dict[str, str] = Field(default_factory=dict)


class DocumentParser(Protocol):
    async def supports(self, source: SourceDocument) -> bool: ...
    async def parse(self, source: SourceDocument) -> ParsedDocument: ...


# TODO(document-intelligence): add format-specific parsers behind DocumentParser.
# TODO(drawing-intelligence): add sheet-aware geometry and callout contracts.
