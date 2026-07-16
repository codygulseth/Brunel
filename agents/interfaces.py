from typing import Protocol
from pydantic import BaseModel, ConfigDict, Field
from models import Citation, ProjectId


class AgentContext(BaseModel):
    model_config = ConfigDict(frozen=True)
    project_id: ProjectId
    request: str = Field(min_length=1)
    human_review_required: bool = True


class AgentResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    summary: str
    citations: tuple[Citation, ...] = ()
    warnings: tuple[str, ...] = ()


class Agent(Protocol):
    """Stable extension point for future narrow, testable assistants."""

    @property
    def name(self) -> str: ...
    async def run(self, context: AgentContext) -> AgentResult: ...
