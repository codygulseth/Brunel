from typing import Protocol
from pydantic import BaseModel, ConfigDict, Field
from models import Citation, ProjectId


class RetrievalQuery(BaseModel):
    model_config = ConfigDict(frozen=True)
    project_id: ProjectId
    text: str = Field(min_length=1)
    limit: int = Field(default=10, ge=1, le=100)


class RetrievalResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    content: str
    citation: Citation
    relevance: float = Field(ge=0, le=1)


class Retriever(Protocol):
    async def retrieve(self, query: RetrievalQuery) -> tuple[RetrievalResult, ...]: ...


# TODO(project-memory): define ingestion, indexing, access-control, and freshness policies.
