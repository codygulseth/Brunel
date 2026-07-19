import os
from pathlib import Path
from typing import Any
from pydantic import BaseModel
from .models import (
    AuditEvent,
    CommitmentView,
    DependencyEdge,
    Mitigation,
    NotificationRequest,
    RiskCandidate,
)


class JsonRiskRepository:
    TYPES: dict[str, type[BaseModel]] = {
        "risks": RiskCandidate,
        "commitments": CommitmentView,
        "mitigations": Mitigation,
        "edges": DependencyEdge,
        "audit": AuditEvent,
        "outbox": NotificationRequest,
    }

    def __init__(self, root: Path):
        self.root = root.expanduser().resolve()

    def save(self, category: str, identifier: str, value: BaseModel) -> None:
        if not identifier.replace("-", "").replace("_", "").isalnum():
            raise ValueError("Unsafe risk record identifier")
        path = self.root / category / f"{identifier}.json"
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
        return tuple(
            value
            for p in sorted(folder.glob("*.json"))
            if (
                value := self.TYPES[category].model_validate_json(p.read_text(encoding="utf-8"))
            ).project_id
            == project_id
        )
