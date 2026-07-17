"""Explicitly opt-in OCR boundary with safe disabled and synthetic providers."""

from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4
from .models import OCRResult, OCRTextBlock


class OCRProvider(Protocol):
    name: str
    version: str

    def recognize(self, project_id: str, sheet_revision_id: str) -> tuple[OCRTextBlock, ...]: ...


class DisabledOCRProvider:
    name = "disabled"
    version = "1"

    def recognize(self, project_id: str, sheet_revision_id: str) -> tuple[OCRTextBlock, ...]:
        raise RuntimeError("OCR is disabled; explicit provider configuration is required")


class SyntheticOCRProvider:
    name = "synthetic-test"
    version = "1"

    def __init__(self, blocks: tuple[OCRTextBlock, ...]):
        self.blocks = blocks

    def recognize(self, project_id: str, sheet_revision_id: str) -> tuple[OCRTextBlock, ...]:
        return self.blocks


def run_ocr(provider: OCRProvider, project_id: str, sheet_revision_id: str) -> OCRResult:
    try:
        blocks = provider.recognize(project_id, sheet_revision_id)
        weak = any(b.confidence < 0.8 for b in blocks)
        return OCRResult(
            id=f"ocr_{uuid4().hex}",
            project_id=project_id,
            sheet_revision_id=sheet_revision_id,
            provider=provider.name,
            provider_version=provider.version,
            configuration_version="1",
            blocks=blocks,
            created_at=datetime.now(UTC),
            successful=True,
            warnings=("Low-confidence OCR requires human confirmation",) if weak else (),
        )
    except Exception as exc:
        return OCRResult(
            id=f"ocr_{uuid4().hex}",
            project_id=project_id,
            sheet_revision_id=sheet_revision_id,
            provider=provider.name,
            provider_version=provider.version,
            configuration_version="1",
            blocks=(),
            created_at=datetime.now(UTC),
            successful=False,
            warnings=(str(exc),),
        )
