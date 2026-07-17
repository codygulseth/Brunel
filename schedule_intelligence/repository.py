"""Atomic local persistence for schedule records."""

import os
from pathlib import Path
from pydantic import BaseModel
from .models import (
    ActivityLineage,
    AuditEvent,
    FloatHistoryRecord,
    MilestoneVarianceRecord,
    NotificationRequest,
    ProjectSchedule,
    ScheduleActivityRevision,
    ScheduleCalendar,
    ScheduleCalculationResult,
    ScheduleExposure,
    ScheduleQualityAssessment,
    ScheduleRelationship,
    ScheduleRevision,
    ScheduleRevisionComparison,
    ScheduleWBSNode,
    SynchronizationProposal,
)


class JsonScheduleRepository:
    TYPES = {
        "schedules": ProjectSchedule,
        "revisions": ScheduleRevision,
        "activities": ScheduleActivityRevision,
        "relationships": ScheduleRelationship,
        "quality": ScheduleQualityAssessment,
        "calculations": ScheduleCalculationResult,
        "lineage": ActivityLineage,
        "comparisons": ScheduleRevisionComparison,
        "floats": FloatHistoryRecord,
        "milestone_variances": MilestoneVarianceRecord,
        "calendars": ScheduleCalendar,
        "wbs": ScheduleWBSNode,
        "proposals": SynchronizationProposal,
        "exposures": ScheduleExposure,
        "audit": AuditEvent,
        "outbox": NotificationRequest,
    }

    def __init__(self, root: Path):
        self.root = root.expanduser().resolve()

    @staticmethod
    def _safe(v):
        if not v or any(
            c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in v
        ):
            raise ValueError("Unsafe schedule identifier")
        return v

    def save(self, category, identifier, value: BaseModel, immutable=False):
        model = self.TYPES[category]
        target = self.root / category / f"{self._safe(identifier)}.json"
        if immutable and target.exists():
            current = model.model_validate_json(target.read_text(encoding="utf-8"))
            if current != value:
                raise ValueError("Immutable schedule record cannot be changed")
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        temporary.write_text(value.model_dump_json(indent=2), encoding="utf-8")
        os.replace(temporary, target)

    def get(self, category, identifier, project_id):
        target = self.root / category / f"{self._safe(identifier)}.json"
        if not target.exists():
            return None
        try:
            value = self.TYPES[category].model_validate_json(target.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return value if getattr(value, "project_id", project_id) == project_id else None

    def list(self, category, project_id):
        folder = self.root / category
        if not folder.exists():
            return ()
        values = []
        for path in sorted(folder.glob("*.json")):
            try:
                value = self.TYPES[category].model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if getattr(value, "project_id", project_id) == project_id:
                values.append(value)
        return tuple(values)
