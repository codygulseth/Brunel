import os
from pathlib import Path
from pydantic import BaseModel
from .models import (
    AuditEvent,
    DailyReport,
    DailyReportComparison,
    DailyReportRevision,
    FieldObservation,
    NotificationRequest,
    PhotoRecord,
    ProgressProposal,
    PlannedWork,
    ProjectDay,
    ScheduleLinkProposal,
    WeeklyFieldSummary,
)


class JsonFieldRepository:
    TYPES = {
        "days": ProjectDay,
        "reports": DailyReport,
        "revisions": DailyReportRevision,
        "observations": FieldObservation,
        "photos": PhotoRecord,
        "schedule_links": ScheduleLinkProposal,
        "progress": ProgressProposal,
        "planned_work": PlannedWork,
        "comparisons": DailyReportComparison,
        "weekly": WeeklyFieldSummary,
        "audit": AuditEvent,
        "outbox": NotificationRequest,
    }

    def __init__(self, root: Path):
        self.root = root.expanduser().resolve()

    def save(self, category, identifier, value: BaseModel, immutable=False):
        if not identifier or any(
            c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
            for c in identifier
        ):
            raise ValueError("Unsafe field record identifier")
        target = self.root / category / f"{identifier}.json"
        model = self.TYPES[category]
        if immutable and target.exists():
            if model.model_validate_json(target.read_text(encoding="utf-8")) != value:
                raise ValueError("Immutable field record cannot be changed")
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix(".tmp")
        temp.write_text(value.model_dump_json(indent=2), encoding="utf-8")
        os.replace(temp, target)

    def get(self, category, identifier, project_id):
        target = self.root / category / f"{identifier}.json"
        if not target.exists():
            return None
        try:
            value = self.TYPES[category].model_validate_json(target.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return value if value.project_id == project_id else None

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
            if value.project_id == project_id:
                values.append(value)
        return tuple(values)
