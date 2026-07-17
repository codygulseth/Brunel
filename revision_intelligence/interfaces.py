from typing import Protocol

from .models import DocumentChange, DocumentComparison


class ComparisonRepository(Protocol):
    def save(self, comparison: DocumentComparison) -> object: ...
    def get(self, comparison_id: str) -> DocumentComparison | None: ...
    def list_by_project(self, project_id: str) -> tuple[DocumentComparison, ...]: ...
    def find_by_document(
        self, project_id: str, document_id: str
    ) -> tuple[DocumentComparison, ...]: ...


class RevisionAnalysisProvider(Protocol):
    """Optional provider limited to already validated deterministic findings."""

    name: str

    def summarize(self, changes: tuple[DocumentChange, ...]) -> str: ...
