"""Atomic project-scoped JSON persistence for meeting operational records."""

import os
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from .models import (
    AuditEvent,
    DecisionConflict,
    ExtractedMeetingItem,
    Meeting,
    MeetingAnalysis,
    MeetingCommitment,
    MeetingDependency,
    MeetingRecordComparison,
    MeetingRecordRevision,
    MeetingSeries,
    MinutesRevision,
    NotificationRequest,
    ProjectAction,
    ProjectDecision,
)

T = TypeVar("T", bound=BaseModel)


class JsonMeetingRepository:
    TYPES = {
        "meetings": Meeting,
        "series": MeetingSeries,
        "records": MeetingRecordRevision,
        "analyses": MeetingAnalysis,
        "candidates": ExtractedMeetingItem,
        "actions": ProjectAction,
        "decisions": ProjectDecision,
        "commitments": MeetingCommitment,
        "dependencies": MeetingDependency,
        "conflicts": DecisionConflict,
        "minutes": MinutesRevision,
        "comparisons": MeetingRecordComparison,
        "audit": AuditEvent,
        "outbox": NotificationRequest,
    }

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()

    @staticmethod
    def _safe(identifier: str) -> str:
        if not identifier or any(
            char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
            for char in identifier
        ):
            raise ValueError("Unsafe record identifier")
        return identifier

    def save(
        self, category: str, identifier: str, value: BaseModel, *, immutable: bool = False
    ) -> Path:
        if category not in self.TYPES:
            raise ValueError("Unknown repository category")
        target = self.root / category / f"{self._safe(identifier)}.json"
        if immutable and target.exists():
            current = self.TYPES[category].model_validate_json(target.read_text(encoding="utf-8"))
            if current != value:
                raise ValueError(f"{category} record is immutable")
            return target
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        temporary.write_text(value.model_dump_json(indent=2), encoding="utf-8")
        os.replace(temporary, target)
        return target

    def get(self, category: str, identifier: str, project_id: str) -> BaseModel | None:
        model = self.TYPES[category]
        target = self.root / category / f"{self._safe(identifier)}.json"
        if not target.exists():
            return None
        value = model.model_validate_json(target.read_text(encoding="utf-8"))
        return value if getattr(value, "project_id", project_id) == project_id else None

    def list(self, category: str, project_id: str) -> tuple[BaseModel, ...]:
        model = self.TYPES[category]
        folder = self.root / category
        if not folder.exists():
            return ()
        values = []
        for path in sorted(folder.glob("*.json")):
            try:
                value = model.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if getattr(value, "project_id", project_id) == project_id:
                values.append(value)
        return tuple(values)

    def find_candidate(self, project_id: str, candidate_id: str) -> ExtractedMeetingItem | None:
        value = self.get("candidates", candidate_id, project_id)
        return value if isinstance(value, ExtractedMeetingItem) else None

    def find_action(self, project_id: str, action_id: str) -> ProjectAction | None:
        value = self.get("actions", action_id, project_id)
        return value if isinstance(value, ProjectAction) else None

    def find_decision(self, project_id: str, decision_id: str) -> ProjectDecision | None:
        value = self.get("decisions", decision_id, project_id)
        return value if isinstance(value, ProjectDecision) else None
