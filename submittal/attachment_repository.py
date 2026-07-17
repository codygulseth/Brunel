"""Atomic local persistence for attachment intelligence records."""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, TypeVar
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from .attachment_models import (
    AttachmentExtractionResult,
    PackageAttachmentStalenessAssessment,
    PackageEvidenceSet,
    PackageRevisionComparison,
    ProposedComplianceMapping,
    SubmittalAttachment,
)
from .errors import SubmittalConcurrencyError, SubmittalPersistenceError

RecordT = TypeVar("RecordT", bound=BaseModel)


class JsonAttachmentIntelligenceRepository:
    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()

    def save_attachment(
        self, attachment: SubmittalAttachment, expected_version: int | None = None
    ) -> Path:
        return self._save("attachments", attachment.id, attachment, expected_version)

    def get_attachment(self, project_id: str, attachment_id: str) -> SubmittalAttachment | None:
        return self._get("attachments", attachment_id, SubmittalAttachment, project_id)

    def list_attachments(
        self, project_id: str, package_id: str | None = None
    ) -> tuple[SubmittalAttachment, ...]:
        items = self._list("attachments", SubmittalAttachment, project_id)
        return tuple(item for item in items if package_id is None or item.package_id == package_id)

    def save_extraction(self, result: AttachmentExtractionResult) -> Path:
        return self._append("attachment-extractions", result.id, result)

    def get_extraction(self, project_id: str, result_id: str) -> AttachmentExtractionResult | None:
        return self._get(
            "attachment-extractions", result_id, AttachmentExtractionResult, project_id
        )

    def list_extractions(
        self, project_id: str, attachment_id: str | None = None
    ) -> tuple[AttachmentExtractionResult, ...]:
        items = self._list("attachment-extractions", AttachmentExtractionResult, project_id)
        return tuple(
            item for item in items if attachment_id is None or item.attachment_id == attachment_id
        )

    def save_mapping(self, mapping: ProposedComplianceMapping) -> Path:
        return self._save("compliance-mappings", mapping.id, mapping, None)

    def get_mapping(self, project_id: str, mapping_id: str) -> ProposedComplianceMapping | None:
        return self._get("compliance-mappings", mapping_id, ProposedComplianceMapping, project_id)

    def list_mappings(
        self,
        project_id: str,
        package_id: str | None = None,
        package_revision: int | None = None,
    ) -> tuple[ProposedComplianceMapping, ...]:
        items = self._list("compliance-mappings", ProposedComplianceMapping, project_id)
        return tuple(
            item
            for item in items
            if (package_id is None or item.package_id == package_id)
            and (package_revision is None or item.package_revision == package_revision)
        )

    def save_evidence_set(self, evidence_set: PackageEvidenceSet) -> Path:
        return self._append("evidence-sets", evidence_set.id, evidence_set, idempotent=True)

    def get_evidence_set(self, project_id: str, evidence_set_id: str) -> PackageEvidenceSet | None:
        return self._get("evidence-sets", evidence_set_id, PackageEvidenceSet, project_id)

    def list_evidence_sets(
        self,
        project_id: str,
        package_id: str | None = None,
        package_revision: int | None = None,
    ) -> tuple[PackageEvidenceSet, ...]:
        items = self._list("evidence-sets", PackageEvidenceSet, project_id)
        filtered = tuple(
            item
            for item in items
            if (package_id is None or item.package_id == package_id)
            and (package_revision is None or item.package_revision == package_revision)
        )
        return tuple(sorted(filtered, key=lambda item: (item.created_at, item.id)))

    def save_comparison(self, comparison: PackageRevisionComparison) -> Path:
        return self._append("package-comparisons", comparison.id, comparison, idempotent=True)

    def get_comparison(
        self, project_id: str, comparison_id: str
    ) -> PackageRevisionComparison | None:
        return self._get(
            "package-comparisons", comparison_id, PackageRevisionComparison, project_id
        )

    def list_comparisons(
        self, project_id: str, package_id: str | None = None
    ) -> tuple[PackageRevisionComparison, ...]:
        items = self._list("package-comparisons", PackageRevisionComparison, project_id)
        return tuple(item for item in items if package_id is None or item.package_id == package_id)

    def save_staleness(self, assessment: PackageAttachmentStalenessAssessment) -> Path:
        return self._append("attachment-staleness", assessment.id, assessment, idempotent=True)

    def list_staleness(
        self, project_id: str, package_id: str | None = None
    ) -> tuple[PackageAttachmentStalenessAssessment, ...]:
        items = self._list("attachment-staleness", PackageAttachmentStalenessAssessment, project_id)
        return tuple(item for item in items if package_id is None or item.package_id == package_id)

    def _save(
        self, kind: str, record_id: str, item: BaseModel, expected_version: int | None
    ) -> Path:
        path = self.root / kind / f"{self._safe(record_id)}.json"
        if path.is_file() and expected_version is not None:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("version") != expected_version:
                raise SubmittalConcurrencyError("Attachment record was updated concurrently")
        self._write(path, item.model_dump(mode="json"))
        return path

    def _append(
        self, kind: str, record_id: str, item: BaseModel, *, idempotent: bool = False
    ) -> Path:
        path = self.root / kind / f"{self._safe(record_id)}.json"
        if path.exists():
            if idempotent and path.read_text(encoding="utf-8") == json.dumps(
                item.model_dump(mode="json"), indent=2, ensure_ascii=False
            ):
                return path
            if idempotent:
                existing = type(item).model_validate_json(path.read_text(encoding="utf-8"))
                if existing == item:
                    return path
            raise SubmittalConcurrencyError("Immutable attachment record already exists")
        self._write(path, item.model_dump(mode="json"), exclusive=True)
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
                    "Skipping unreadable attachment-intelligence record: %s", path.name
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
            raise SubmittalConcurrencyError("Immutable attachment record already exists")
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
