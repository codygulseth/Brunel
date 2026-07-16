"""Conservative construction metadata normalization."""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .models import DocumentType, FileType


@dataclass(frozen=True, slots=True)
class NormalizedMetadata:
    document_type: DocumentType = DocumentType.UNKNOWN
    title: str | None = None
    revision: str | None = None
    revision_date: date | None = None
    sheet_number: str | None = None
    specification_section: str | None = None


class ConservativeMetadataExtractor:
    """Retains explicit metadata and avoids guessing construction identifiers."""

    def extract(
        self,
        *,
        path: Path,
        file_type: FileType,
        first_page_text: str,
        document_type: DocumentType | None = None,
        title: str | None = None,
        revision: str | None = None,
        revision_date: date | None = None,
        sheet_number: str | None = None,
        specification_section: str | None = None,
    ) -> NormalizedMetadata:
        explicit_title = title
        if explicit_title is None and file_type == FileType.MARKDOWN:
            explicit_title = self._markdown_title(first_page_text)
        return NormalizedMetadata(
            document_type=document_type or DocumentType.UNKNOWN,
            title=explicit_title,
            revision=revision,
            revision_date=revision_date,
            sheet_number=sheet_number,
            specification_section=specification_section,
        )

    @staticmethod
    def _markdown_title(content: str) -> str | None:
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("# ") and stripped[2:].strip():
                return stripped[2:].strip()
        return None
