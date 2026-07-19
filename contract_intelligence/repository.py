import os
from pathlib import Path
from typing import Any
from pydantic import BaseModel
from .models import (
    AuditEvent,
    ChronologyEntry,
    Clause,
    ConflictFinding,
    ContractDocument,
    ContractEvent,
    ContractRelationship,
    ContractRequirement,
    Correspondence,
    DeadlineCalculation,
    DefinedTerm,
    HierarchyEdge,
    NoticeCandidate,
    NoticeDraft,
    NotificationRequest,
    Obligation,
)


class JsonContractRepository:
    TYPES: dict[str, type[BaseModel]] = {
        "documents": ContractDocument,
        "relationships": ContractRelationship,
        "hierarchy": HierarchyEdge,
        "clauses": Clause,
        "terms": DefinedTerm,
        "requirements": ContractRequirement,
        "deadlines": DeadlineCalculation,
        "candidates": NoticeCandidate,
        "drafts": NoticeDraft,
        "obligations": Obligation,
        "events": ContractEvent,
        "correspondence": Correspondence,
        "conflicts": ConflictFinding,
        "chronology": ChronologyEntry,
        "audit": AuditEvent,
        "outbox": NotificationRequest,
    }

    def __init__(self, root: Path):
        self.root = root.expanduser().resolve()

    def save(
        self, category: str, identifier: str, value: BaseModel, immutable: bool = False
    ) -> None:
        if not identifier.replace("-", "").replace("_", "").isalnum():
            raise ValueError("Unsafe contract record identifier")
        path = self.root / category / f"{identifier}.json"
        if immutable and path.exists():
            if self.TYPES[category].model_validate_json(path.read_text(encoding="utf-8")) != value:
                raise ValueError("Immutable contract record cannot be changed")
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
        result = []
        for path in sorted(folder.glob("*.json")):
            value = self.TYPES[category].model_validate_json(path.read_text(encoding="utf-8"))
            if value.project_id == project_id:
                result.append(value)
        return tuple(result)
