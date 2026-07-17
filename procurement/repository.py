"""Atomic JSON persistence for procurement operational records."""

import os
from pathlib import Path

from pydantic import BaseModel

from .models import (
    AuditEvent,
    NotificationRequest,
    ProcurementCandidate,
    ProcurementItem,
    ProcurementPlanComparison,
    ProcurementPlanRevision,
)


class JsonProcurementRepository:
    TYPES = {
        "candidates": ProcurementCandidate,
        "items": ProcurementItem,
        "plans": ProcurementPlanRevision,
        "comparisons": ProcurementPlanComparison,
        "audit": AuditEvent,
        "outbox": NotificationRequest,
    }

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()

    @staticmethod
    def _safe(value: str) -> str:
        if not value or any(
            c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
            for c in value
        ):
            raise ValueError("Unsafe record identifier")
        return value

    def save(
        self, category: str, identifier: str, value: BaseModel, *, immutable: bool = False
    ) -> None:
        model = self.TYPES[category]
        target = self.root / category / f"{self._safe(identifier)}.json"
        if immutable and target.exists():
            old = model.model_validate_json(target.read_text(encoding="utf-8"))
            if old != value:
                raise ValueError("Immutable procurement record cannot be changed")
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix(".tmp")
        temp.write_text(value.model_dump_json(indent=2), encoding="utf-8")
        os.replace(temp, target)

    def get(self, category: str, identifier: str, project_id: str):
        target = self.root / category / f"{self._safe(identifier)}.json"
        if not target.exists():
            return None
        try:
            value = self.TYPES[category].model_validate_json(target.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return value if value.project_id == project_id else None

    def list(self, category: str, project_id: str):
        folder = self.root / category
        if not folder.exists():
            return ()
        values = []
        for path in sorted(folder.glob("*.json")):
            try:
                value = self.TYPES[category].model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if value.project_id == project_id:
                values.append(value)
        return tuple(values)
