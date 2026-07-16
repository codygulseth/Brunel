from datetime import datetime
from typing import Annotated
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

ProjectId = Annotated[UUID, Field(description="Stable project identifier")]
DocumentId = Annotated[UUID, Field(description="Stable source-document identifier")]


class Citation(BaseModel):
    """Traceable location in a versioned source document."""

    model_config = ConfigDict(frozen=True)
    document_id: DocumentId
    document_version: str = Field(min_length=1)
    locator: str = Field(min_length=1, description="Page, sheet, section, or record locator")
    excerpt: str | None = None
    retrieved_at: datetime
