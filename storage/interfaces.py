from typing import Protocol
from pydantic import BaseModel, ConfigDict, Field
from models import ProjectId


class ProjectRecord(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: ProjectId
    name: str = Field(min_length=1)
    project_number: str = Field(min_length=1)


class ProjectRepository(Protocol):
    async def get(self, project_id: ProjectId) -> ProjectRecord | None: ...
    async def save(self, project: ProjectRecord) -> None: ...
