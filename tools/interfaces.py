from typing import Any, Protocol
from pydantic import BaseModel, ConfigDict, Field
from models import Citation, ProjectId


class ToolContext(BaseModel):
    model_config = ConfigDict(frozen=True)
    project_id: ProjectId
    human_approved: bool = False


class ToolResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    data: dict[str, Any] = Field(default_factory=dict)
    citations: tuple[Citation, ...] = ()
    warnings: tuple[str, ...] = ()


class Tool(Protocol):
    @property
    def name(self) -> str: ...
    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> ToolResult: ...


# TODO(administrative-automation): require explicit human approval for external side effects.
