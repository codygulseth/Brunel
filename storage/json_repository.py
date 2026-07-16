"""Local JSON storage adapter for ingested Brunel document aggregates."""

import json
import os
from pathlib import Path

from document_processing.models import IngestedDocument


class JsonDocumentRepository:
    """Stores one validated aggregate per document using atomic file replacement."""

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()

    def save(self, ingested: IngestedDocument) -> Path:
        target = self._path(ingested.document.document_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".json.tmp")
        payload = ingested.model_dump(mode="json")
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8"
        )
        os.replace(temporary, target)
        return target

    def get(self, document_id: str) -> IngestedDocument | None:
        target = self._path(document_id)
        if not target.is_file():
            return None
        return IngestedDocument.model_validate_json(target.read_text(encoding="utf-8"))

    def _path(self, document_id: str) -> Path:
        if not document_id.startswith("doc_") or not document_id[4:].isalnum():
            raise ValueError("Invalid document ID")
        return self.root / "documents" / f"{document_id}.json"
