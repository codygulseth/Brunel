"""Atomic local persistence for canonical submittal records."""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, TypeVar
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from .errors import SubmittalConcurrencyError, SubmittalPersistenceError
from .models import (
    RequirementReview,
    SubmittalAuditEvent,
    SubmittalPackage,
    SubmittalRegisterItem,
    SubmittalRequirementCandidate,
)

RecordT = TypeVar("RecordT", bound=BaseModel)


class JsonSubmittalRepository:
    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()

    def next_number(
        self, project_id: str, *, prefix: str = "SUB", digits: int = 3, sequence: str = "register"
    ) -> str:
        path = self.root / "sequences" / f"{self._safe(project_id)}-{self._safe(sequence)}.json"
        current = json.loads(path.read_text(encoding="utf-8"))["value"] if path.is_file() else 0
        value = int(current) + 1
        self._write(path, {"value": value})
        return f"{prefix}-{value:0{digits}d}"

    def save_candidate(
        self, candidate: SubmittalRequirementCandidate, expected_version: int | None = None
    ) -> Path:
        return self._save("candidates", candidate.id, candidate, expected_version)

    def get_candidate(
        self, project_id: str, candidate_id: str
    ) -> SubmittalRequirementCandidate | None:
        return self._get("candidates", candidate_id, SubmittalRequirementCandidate, project_id)

    def list_candidates(self, project_id: str) -> tuple[SubmittalRequirementCandidate, ...]:
        return self._list("candidates", SubmittalRequirementCandidate, project_id)

    def save_register(
        self, item: SubmittalRegisterItem, expected_version: int | None = None
    ) -> Path:
        return self._save("register", item.id, item, expected_version)

    def get_register(self, project_id: str, item_id: str) -> SubmittalRegisterItem | None:
        return self._get("register", item_id, SubmittalRegisterItem, project_id)

    def list_register(self, project_id: str) -> tuple[SubmittalRegisterItem, ...]:
        return self._list("register", SubmittalRegisterItem, project_id)

    def save_package(self, package: SubmittalPackage, expected_version: int | None = None) -> Path:
        return self._save("packages", package.id, package, expected_version)

    def get_package(self, project_id: str, package_id: str) -> SubmittalPackage | None:
        return self._get("packages", package_id, SubmittalPackage, project_id)

    def list_packages(self, project_id: str) -> tuple[SubmittalPackage, ...]:
        return self._list("packages", SubmittalPackage, project_id)

    def append_review(self, project_id: str, review: RequirementReview) -> None:
        self._write(
            self.root / "requirement-reviews" / f"{self._safe(review.id)}.json",
            {"project_id": project_id, **review.model_dump(mode="json")},
            exclusive=True,
        )

    def append_audit(self, event: SubmittalAuditEvent) -> None:
        self._write(
            self.root / "audit" / f"{self._safe(event.id)}.json",
            event.model_dump(mode="json"),
            exclusive=True,
        )

    def audit(
        self, project_id: str, entity_id: str | None = None
    ) -> tuple[SubmittalAuditEvent, ...]:
        events = self._list("audit", SubmittalAuditEvent, project_id)
        return tuple(event for event in events if entity_id is None or event.entity_id == entity_id)

    def _save(
        self, kind: str, record_id: str, item: BaseModel, expected_version: int | None
    ) -> Path:
        path = self.root / kind / f"{self._safe(record_id)}.json"
        if path.is_file() and expected_version is not None:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("version") != expected_version:
                raise SubmittalConcurrencyError("Submittal record was updated concurrently")
        self._write(path, item.model_dump(mode="json"))
        return path

    def _get(
        self, kind: str, record_id: str, model: type[RecordT], project_id: str
    ) -> RecordT | None:
        path = self.root / kind / f"{self._safe(record_id)}.json"
        if not path.is_file():
            return None
        try:
            item = model.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, ValidationError) as exc:
            raise SubmittalPersistenceError(f"Unreadable {kind} record: {record_id}") from exc
        return item if getattr(item, "project_id", None) == project_id else None

    def _list(self, kind: str, model: type[RecordT], project_id: str) -> tuple[RecordT, ...]:
        directory = self.root / kind
        if not directory.is_dir():
            return ()
        items: list[RecordT] = []
        for path in sorted(directory.glob("*.json")):
            try:
                item = model.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, ValidationError):
                logging.getLogger(__name__).warning(
                    "Skipping unreadable submittal record: %s", path.name
                )
                continue
            if getattr(item, "project_id", None) == project_id:
                items.append(item)
        return tuple(items)

    @staticmethod
    def _safe(value: str) -> str:
        if not value or not value.replace("_", "").replace("-", "").isalnum():
            raise ValueError("Invalid identifier")
        return value

    @staticmethod
    def _write(path: Path, payload: dict[str, Any], *, exclusive: bool = False) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if exclusive and path.exists():
            raise SubmittalConcurrencyError("Append-only record already exists")
        temporary = path.with_suffix(f".json.{uuid4().hex}.tmp")
        temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        try:
            for attempt in range(20):
                try:
                    os.replace(temporary, path)
                    return
                except PermissionError:
                    if attempt == 19:
                        raise
                    time.sleep(0.05)
        finally:
            temporary.unlink(missing_ok=True)
