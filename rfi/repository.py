"""Atomic local RFI persistence, numbering, and append-only audit."""

import json
import logging
import os
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .errors import RFIConcurrencyError, RFIPersistenceError
from .models import RFI, RFIAuditEvent


class JsonRFIRepository:
    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()

    def next_number(self, project_id: str, prefix: str = "RFI", digits: int = 3) -> str:
        sequence = self.root / "sequences" / f"{self._safe(project_id)}.json"
        sequence.parent.mkdir(parents=True, exist_ok=True)
        current = (
            json.loads(sequence.read_text(encoding="utf-8"))["value"] if sequence.is_file() else 0
        )
        value = current + 1
        self._write(sequence, {"value": value})
        return f"{prefix}-{value:0{digits}d}"

    def save(self, rfi: RFI, expected_version: int | None = None) -> Path:
        path = self.root / "records" / f"{self._safe(rfi.id)}.json"
        if path.is_file() and expected_version is not None:
            current = RFI.model_validate_json(path.read_text(encoding="utf-8"))
            if current.version != expected_version:
                raise RFIConcurrencyError("RFI was updated concurrently")
        self._write(path, rfi.model_dump(mode="json"))
        return path

    def get(self, project_id: str, rfi_id: str) -> RFI | None:
        path = self.root / "records" / f"{self._safe(rfi_id)}.json"
        if not path.is_file():
            return None
        try:
            item = RFI.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError, ValueError) as exc:
            raise RFIPersistenceError(f"RFI record is unreadable: {rfi_id}") from exc
        return item if item.project_id == project_id else None

    def list(self, project_id: str) -> tuple[RFI, ...]:
        directory = self.root / "records"
        if not directory.is_dir():
            return ()
        items: list[RFI] = []
        for path in sorted(directory.glob("*.json")):
            try:
                item = RFI.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValidationError, ValueError):
                logging.getLogger(__name__).warning("Skipping unreadable RFI record: %s", path.name)
                continue
            if item.project_id == project_id:
                items.append(item)
        return tuple(items)

    def append_audit(self, event: RFIAuditEvent) -> None:
        path = self.root / "audit" / f"{self._safe(event.id)}.json"
        if path.exists():
            raise RFIConcurrencyError("RFI audit is append-only")
        self._write(path, event.model_dump(mode="json"))

    def audit(self, project_id: str, rfi_id: str) -> tuple[RFIAuditEvent, ...]:
        directory = self.root / "audit"
        if not directory.is_dir():
            return ()
        return tuple(
            item
            for item in (
                RFIAuditEvent.model_validate_json(p.read_text(encoding="utf-8"))
                for p in sorted(directory.glob("*.json"))
            )
            if item.project_id == project_id and item.rfi_id == rfi_id
        )

    @staticmethod
    def _safe(value: str) -> str:
        if not value or not value.replace("_", "").replace("-", "").isalnum():
            raise ValueError("Invalid identifier")
        return value

    @staticmethod
    def _write(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(temp, path)
