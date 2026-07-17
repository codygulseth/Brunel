"""Atomic JSON persistence for drawing intelligence aggregates."""

import json
import os
from pathlib import Path

from .models import (
    AuditEvent,
    DrawingAnalysis,
    DrawingSetComparison,
    NotificationRequest,
    OCRResult,
)


class JsonDrawingRepository:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _path(self, category: str, identifier: str) -> Path:
        safe = "".join(c for c in identifier if c.isalnum() or c in "-_")
        if not safe or safe != identifier:
            raise ValueError("unsafe identifier")
        return self.root / category / f"{safe}.json"

    def _write(self, path: Path, value: object) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        payload = (
            value.model_dump_json(indent=2)
            if hasattr(value, "model_dump_json")
            else json.dumps(value)
        )
        temporary.write_text(payload, encoding="utf-8")
        os.replace(temporary, path)
        return path

    def save_analysis(self, value: DrawingAnalysis) -> Path:
        path = self._path("analyses", value.revision.revision_id)
        if path.exists():
            current = DrawingAnalysis.model_validate_json(path.read_text(encoding="utf-8"))
            if current != value:
                raise ValueError("drawing analysis revisions are immutable")
            return path
        return self._write(path, value)

    def get_analysis(self, project_id: str, revision_id: str) -> DrawingAnalysis | None:
        path = self._path("analyses", revision_id)
        if not path.exists():
            return None
        value = DrawingAnalysis.model_validate_json(path.read_text(encoding="utf-8"))
        return value if value.revision.project_id == project_id else None

    def list_analyses(self, project_id: str) -> tuple[DrawingAnalysis, ...]:
        folder = self.root / "analyses"
        values = (
            []
            if not folder.exists()
            else [
                DrawingAnalysis.model_validate_json(p.read_text(encoding="utf-8"))
                for p in folder.glob("*.json")
            ]
        )
        return tuple(v for v in values if v.revision.project_id == project_id)

    def replace_after_review(self, value: DrawingAnalysis) -> Path:
        return self._write(self._path("analyses", value.revision.revision_id), value)

    def save_comparison(self, value: DrawingSetComparison) -> Path:
        return self._write(self._path("comparisons", value.id), value)

    def get_comparison(self, project_id: str, comparison_id: str) -> DrawingSetComparison | None:
        path = self._path("comparisons", comparison_id)
        if not path.exists():
            return None
        value = DrawingSetComparison.model_validate_json(path.read_text(encoding="utf-8"))
        return value if value.project_id == project_id else None

    def save_ocr(self, value: OCRResult) -> Path:
        return self._write(self._path("ocr", value.id), value)

    def list_ocr(self, project_id: str, sheet_revision_id: str) -> tuple[OCRResult, ...]:
        folder = self.root / "ocr"
        values = (
            []
            if not folder.exists()
            else [OCRResult.model_validate_json(p.read_text()) for p in folder.glob("*.json")]
        )
        return tuple(
            v
            for v in values
            if v.project_id == project_id and v.sheet_revision_id == sheet_revision_id
        )

    def append_audit(self, value: AuditEvent) -> Path:
        return self._write(self._path("audit", value.id), value)

    def append_notification(self, value: NotificationRequest) -> Path:
        return self._write(self._path("outbox", value.id), value)

    def list_audit(self, project_id: str) -> tuple[AuditEvent, ...]:
        folder = self.root / "audit"
        values = (
            ()
            if not folder.exists()
            else tuple(
                AuditEvent.model_validate_json(path.read_text(encoding="utf-8"))
                for path in folder.glob("*.json")
            )
        )
        return tuple(item for item in values if item.project_id == project_id)

    def list_notifications(self, project_id: str) -> tuple[NotificationRequest, ...]:
        folder = self.root / "outbox"
        values = (
            ()
            if not folder.exists()
            else tuple(
                NotificationRequest.model_validate_json(path.read_text(encoding="utf-8"))
                for path in folder.glob("*.json")
            )
        )
        return tuple(item for item in values if item.project_id == project_id)
