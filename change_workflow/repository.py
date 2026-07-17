"""Atomic local JSON repositories with project isolation and optimistic versions."""

import json
import os
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from .errors import ConcurrencyError
from .models import AuditEvent, NotificationRequest, ProjectChange

RecordT = TypeVar("RecordT", bound=BaseModel)


class JsonChangeWorkflowRepository:
    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()

    def save_change(self, change: ProjectChange, *, expected_version: int | None = None) -> Path:
        path = self._safe_path("changes", change.id)
        if path.is_file() and expected_version is not None:
            current = ProjectChange.model_validate_json(path.read_text(encoding="utf-8"))
            if current.version != expected_version:
                raise ConcurrencyError("Project change was updated by another operation")
        self._atomic_write(path, change.model_dump(mode="json"))
        return path

    def get_change(self, project_id: str, change_id: str) -> ProjectChange | None:
        path = self._safe_path("changes", change_id)
        if not path.is_file():
            return None
        item = ProjectChange.model_validate_json(path.read_text(encoding="utf-8"))
        return item if item.project_id == project_id else None

    def list_changes(self, project_id: str) -> tuple[ProjectChange, ...]:
        return tuple(
            item
            for item in self._read_all("changes", ProjectChange)
            if item.project_id == project_id
        )

    def append_audit(self, event: AuditEvent) -> Path:
        path = self._safe_path("audit", event.id)
        if path.exists():
            raise ConcurrencyError("Audit events are append-only")
        self._atomic_write(path, event.model_dump(mode="json"))
        return path

    def list_audit(self, project_id: str, entity_id: str | None = None) -> tuple[AuditEvent, ...]:
        events = (
            item for item in self._read_all("audit", AuditEvent) if item.project_id == project_id
        )
        return tuple(item for item in events if entity_id is None or item.entity_id == entity_id)

    def queue_notification(self, request: NotificationRequest) -> Path:
        path = self._safe_path("outbox", request.id)
        if not path.exists():
            self._atomic_write(path, request.model_dump(mode="json"))
        return path

    def list_notifications(self, project_id: str) -> tuple[NotificationRequest, ...]:
        return tuple(
            item
            for item in self._read_all("outbox", NotificationRequest)
            if item.project_id == project_id
        )

    def _read_all(self, kind: str, model: type[RecordT]) -> tuple[RecordT, ...]:
        directory = self.root / kind
        if not directory.is_dir():
            return ()
        return tuple(
            model.model_validate_json(path.read_text(encoding="utf-8"))
            for path in sorted(directory.glob("*.json"))
        )

    def _safe_path(self, kind: str, identifier: str) -> Path:
        if not identifier or not identifier.replace("_", "").replace("-", "").isalnum():
            raise ValueError("Invalid record identifier")
        return self.root / kind / f"{identifier}.json"

    @staticmethod
    def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, path)
