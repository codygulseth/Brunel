from typing import Protocol
from pydantic import BaseModel, ConfigDict, Field


class Prompt(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    template: str = Field(min_length=1)


class PromptRepository(Protocol):
    def get(self, name: str, version: str | None = None) -> Prompt: ...


# TODO(prompts): store reviewed, versioned prompts here only when model-backed features begin.
