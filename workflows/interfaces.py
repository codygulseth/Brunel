from typing import Any, Protocol
from pydantic import BaseModel, ConfigDict, Field
from models import Citation, ProjectId


class WorkflowContext(BaseModel):
    model_config = ConfigDict(frozen=True)
    project_id: ProjectId
    inputs: dict[str, Any] = Field(default_factory=dict)


class WorkflowResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    status: str
    outputs: dict[str, Any] = Field(default_factory=dict)
    citations: tuple[Citation, ...] = ()
    requires_human_review: bool = True


class Workflow(Protocol):
    @property
    def name(self) -> str: ...
    async def run(self, context: WorkflowContext) -> WorkflowResult: ...


# TODO(construction-qa): add RFI and submittal workflows after requirements are documented.
# Procurement Intelligence implements deterministic long-lead planning in the canonical
# `procurement` domain; cross-module workflow orchestration remains explicit at service boundaries.
# TODO(safety): safety features must support humans and never claim compliance or approval.
# TODO(commissioning): add readiness and issue-tracking workflows.
