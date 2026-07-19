import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .models import (
    Asset,
    AuditEvent,
    Checklist,
    CloseoutRecord,
    CommissioningSystem,
    Deficiency,
    Instrument,
    NotificationRequest,
    ReadinessAssessment,
    Requirement,
    TestExecution,
    TestProcedure,
    TurnoverPackage,
)


class JsonCommissioningRepository:
    TYPES: dict[str, type[BaseModel]] = {
        "systems": CommissioningSystem,
        "assets": Asset,
        "requirements": Requirement,
        "checklists": Checklist,
        "procedures": TestProcedure,
        "executions": TestExecution,
        "instruments": Instrument,
        "deficiencies": Deficiency,
        "readiness": ReadinessAssessment,
        "packages": TurnoverPackage,
        "closeout": CloseoutRecord,
        "audit": AuditEvent,
        "outbox": NotificationRequest,
    }

    def __init__(self, root: Path):
        self.root = root.expanduser().resolve()

    def save(
        self, category: str, identifier: str, value: BaseModel, immutable: bool = False
    ) -> None:
        if not identifier.replace("-", "").replace("_", "").isalnum():
            raise ValueError("Unsafe commissioning record identifier")
        path = self.root / category / f"{identifier}.json"
        if immutable and path.exists():
            current = self.TYPES[category].model_validate_json(path.read_text(encoding="utf-8"))
            if current != value:
                raise ValueError("Immutable commissioning revision cannot be changed")
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        temp.write_text(value.model_dump_json(indent=2), encoding="utf-8")
        os.replace(temp, path)

    def get(self, category: str, identifier: str, project_id: str) -> Any | None:
        path = self.root / category / f"{identifier}.json"
        if not path.exists():
            return None
        value = self.TYPES[category].model_validate_json(path.read_text(encoding="utf-8"))
        return value if value.project_id == project_id else None

    def list(self, category: str, project_id: str) -> tuple[Any, ...]:
        folder = self.root / category
        if not folder.exists():
            return ()
        values = []
        for path in sorted(folder.glob("*.json")):
            value = self.TYPES[category].model_validate_json(path.read_text(encoding="utf-8"))
            if value.project_id == project_id:
                values.append(value)
        return tuple(values)
