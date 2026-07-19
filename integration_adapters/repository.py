import os
from pathlib import Path
from typing import Any
from pydantic import BaseModel
from .models import (
    AuditEvent,
    ExportExecution,
    ExportProposal,
    ExternalIdentityMapping,
    ImportSession,
    IntegrationConflict,
    IntegrationConnection,
    NormalizedRecord,
    NotificationRequest,
    RawExternalRecord,
    Reconciliation,
    SecretReference,
)


class JsonIntegrationRepository:
    TYPES: dict[str, type[BaseModel]] = {
        "connections": IntegrationConnection,
        "secrets": SecretReference,
        "sessions": ImportSession,
        "raw": RawExternalRecord,
        "normalized": NormalizedRecord,
        "mappings": ExternalIdentityMapping,
        "conflicts": IntegrationConflict,
        "proposals": ExportProposal,
        "executions": ExportExecution,
        "reconciliations": Reconciliation,
        "audit": AuditEvent,
        "outbox": NotificationRequest,
    }

    def __init__(self, root: Path):
        self.root = root.expanduser().resolve()

    def save(
        self, category: str, identifier: str, value: BaseModel, immutable: bool = False
    ) -> None:
        if not identifier.replace("-", "").replace("_", "").isalnum():
            raise ValueError("Unsafe integration identifier")
        path = self.root / category / f"{identifier}.json"
        if category == "sessions" and path.exists():
            current = self.TYPES[category].model_validate_json(path.read_text(encoding="utf-8"))
            if current.completed_at is not None and current != value:
                raise ValueError("Completed import session is immutable")
        if immutable and path.exists():
            if self.TYPES[category].model_validate_json(path.read_text(encoding="utf-8")) != value:
                raise ValueError("Immutable integration record cannot be changed")
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        temp.write_text(value.model_dump_json(indent=2), encoding="utf-8")
        os.replace(temp, path)

    def get(
        self, category: str, identifier: str, organization_id: str, project_id: str | None = None
    ) -> Any | None:
        path = self.root / category / f"{identifier}.json"
        if not path.exists():
            return None
        value = self.TYPES[category].model_validate_json(path.read_text(encoding="utf-8"))
        if getattr(value, "organization_id", None) != organization_id:
            return None
        value_project = getattr(value, "project_id", None)
        return value if project_id is None or value_project == project_id else None

    def list(
        self, category: str, organization_id: str, project_id: str | None = None
    ) -> tuple[Any, ...]:
        folder = self.root / category
        if not folder.exists():
            return ()
        result = []
        for path in sorted(folder.glob("*.json")):
            value = self.TYPES[category].model_validate_json(path.read_text(encoding="utf-8"))
            if getattr(value, "organization_id", None) == organization_id and (
                project_id is None or getattr(value, "project_id", None) == project_id
            ):
                result.append(value)
        return tuple(result)
