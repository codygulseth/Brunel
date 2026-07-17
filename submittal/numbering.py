"""Configurable project-scoped submittal numbering."""

from typing import Protocol

from .repository import JsonSubmittalRepository


class SubmittalNumberingService(Protocol):
    def next_register_number(self, project_id: str, specification_section: str) -> str: ...


class ProjectSubmittalNumberingService:
    def __init__(
        self,
        repository: JsonSubmittalRepository,
        *,
        prefix: str = "SUB",
        digits: int = 3,
        mode: str = "sequential",
    ) -> None:
        self.repository = repository
        self.prefix = prefix
        self.digits = digits
        self.mode = mode

    def next_register_number(self, project_id: str, specification_section: str) -> str:
        prefix = self.prefix
        if self.mode == "specification":
            prefix = specification_section.strip().replace(" ", "") or prefix
        return self.repository.next_number(
            project_id, prefix=prefix, digits=self.digits, sequence="register"
        )
