"""Project-scoped numbering abstraction for future document-control adapters."""

from typing import Protocol

from .repository import JsonRFIRepository


class RFINumberingService(Protocol):
    def next_number(self, project_id: str) -> str: ...


class ProjectRFINumberingService:
    def __init__(self, repository: JsonRFIRepository, prefix: str = "RFI", digits: int = 3) -> None:
        self.repository = repository
        self.prefix = prefix
        self.digits = digits

    def next_number(self, project_id: str) -> str:
        return self.repository.next_number(project_id, self.prefix, self.digits)
