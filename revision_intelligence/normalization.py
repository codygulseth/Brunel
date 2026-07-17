"""Conservative block normalization with exact source traceability."""

import re
import unicodedata
from hashlib import sha256

from document_processing.models import IngestedDocument

from .models import BlockType, ComparisonUnit, SourceSpan

_CLAUSE = re.compile(r"^\s*(\d+(?:\.\d+)*|[A-Z]\d*(?:\.\d+)*)[.)]?\s+")
_BULLET = re.compile(r"^\s*[-*•]\s+")


class ContentNormalizer:
    """Splits source chunks into stable blocks without rewriting quoted text."""

    def normalize(self, document: IngestedDocument) -> tuple[ComparisonUnit, ...]:
        units: list[ComparisonUnit] = []
        order = 0
        for chunk in document.chunks:
            for match in re.finditer(r"[^\n]+(?:\n|$)", chunk.content):
                source = match.group(0).rstrip("\r\n")
                if not source.strip():
                    continue
                normalized = self.normalize_text(source)
                identifier = self._identifier(source)
                digest = sha256(f"{chunk.id}\0{match.start()}\0{source}".encode()).hexdigest()[:16]
                units.append(
                    ComparisonUnit(
                        id=f"blk_{digest}",
                        block_type=self._block_type(source, identifier),
                        normalized_text=normalized,
                        identifier=identifier,
                        order=order,
                        span=SourceSpan(
                            document_id=document.document.document_id,
                            page_number=chunk.page_number,
                            chunk_id=chunk.id,
                            start_offset=chunk.start_offset + match.start(),
                            end_offset=chunk.start_offset + match.start() + len(source),
                            sheet_number=chunk.citation.sheet_number,
                            specification_section=chunk.citation.specification_section,
                            source_text=source,
                            citation=chunk.citation,
                        ),
                    )
                )
                order += 1
        return tuple(units)

    @staticmethod
    def normalize_text(text: str) -> str:
        return " ".join(unicodedata.normalize("NFKC", text).casefold().split())

    @staticmethod
    def _identifier(text: str) -> str | None:
        match = _CLAUSE.match(text)
        return match.group(1).casefold() if match else None

    @staticmethod
    def _block_type(text: str, identifier: str | None) -> BlockType:
        stripped = text.strip()
        if identifier:
            return BlockType.NUMBERED_CLAUSE
        if _BULLET.match(text):
            return BlockType.BULLET
        if stripped.startswith("#") or (len(stripped) < 80 and stripped.isupper()):
            return BlockType.HEADING
        if "|" in stripped or "\t" in stripped:
            return BlockType.TABLE_ROW
        return BlockType.PARAGRAPH
