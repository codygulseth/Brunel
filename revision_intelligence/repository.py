"""Atomic project-scoped JSON persistence for comparison results."""

import json
import os
from pathlib import Path

from .models import DocumentComparison


class JsonComparisonRepository:
    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()

    def save(self, comparison: DocumentComparison) -> Path:
        path = self._path(comparison.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(comparison.model_dump(mode="json"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(temporary, path)
        return path

    def get(self, comparison_id: str) -> DocumentComparison | None:
        path = self._path(comparison_id)
        return (
            DocumentComparison.model_validate_json(path.read_text(encoding="utf-8"))
            if path.is_file()
            else None
        )

    def list_by_project(self, project_id: str) -> tuple[DocumentComparison, ...]:
        directory = self.root / "comparisons"
        if not directory.is_dir():
            return ()
        items = tuple(
            DocumentComparison.model_validate_json(path.read_text(encoding="utf-8"))
            for path in sorted(directory.glob("cmp_*.json"))
        )
        return tuple(item for item in items if item.project_id == project_id)

    def find_by_document(self, project_id: str, document_id: str) -> tuple[DocumentComparison, ...]:
        return tuple(
            item
            for item in self.list_by_project(project_id)
            if document_id in {item.old_document.document_id, item.new_document.document_id}
        )

    def _path(self, comparison_id: str) -> Path:
        if not comparison_id.startswith("cmp_") or not comparison_id[4:].isalnum():
            raise ValueError("Invalid comparison ID")
        return self.root / "comparisons" / f"{comparison_id}.json"
