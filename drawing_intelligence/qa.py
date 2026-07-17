"""Deterministic cited answers about indexed drawing evidence."""

import re

from pydantic import BaseModel, ConfigDict

from .extraction import citation
from .models import VisualRegionCitation
from .repository import JsonDrawingRepository


class DrawingAnswer(BaseModel):
    model_config = ConfigDict(frozen=True)
    answer: str
    sufficient: bool
    evidence_type: str
    citations: tuple[VisualRegionCitation, ...] = ()
    limitations: tuple[str, ...] = ()


class DrawingQuestionService:
    """Answers only patterns supported by persisted drawing facts."""

    def __init__(self, repository: JsonDrawingRepository) -> None:
        self.repository = repository

    def answer(self, project_id: str, question: str) -> DrawingAnswer:
        analyses = self.repository.list_analyses(project_id)
        if not analyses:
            return self._unknown("No analyzed drawing sets exist in this project.")
        latest = max(
            analyses,
            key=lambda item: (
                item.revision.revision_sequence
                if item.revision.revision_sequence is not None
                else -1,
                item.revision.created_at,
            ),
        )
        lowered = question.casefold()
        if "graphical" in lowered or "visual" in lowered or "design changed" in lowered:
            return DrawingAnswer(
                answer=(
                    "Brunel cannot determine the meaning of graphical changes from this analysis. "
                    "It can report metadata/native-text differences and requires human visual review."
                ),
                sufficient=True,
                evidence_type="analysis_limitation",
                limitations=("Visual-only changes are not interpreted.",),
            )
        if "missing" in lowered:
            issues = [item for item in latest.validation.issues if "missing" in item.status.value]
            if not issues:
                return DrawingAnswer(
                    answer="No missing-sheet conditions were found in the latest analyzed set.",
                    sufficient=True,
                    evidence_type="drawing_validation",
                )
            return DrawingAnswer(
                answer="; ".join(item.message for item in issues),
                sufficient=True,
                evidence_type="drawing_index_and_explicit_reference",
                citations=tuple(c for item in issues for c in item.citations),
            )
        if "duplicate" in lowered:
            issues = [
                item for item in latest.validation.issues if item.status.value == "duplicate_sheet"
            ]
            return DrawingAnswer(
                answer=(
                    "; ".join(item.message for item in issues)
                    if issues
                    else "No duplicate sheet numbers were detected."
                ),
                sufficient=True,
                evidence_type="drawing_validation",
                citations=tuple(c for item in issues for c in item.citations),
            )
        number_match = re.search(r"\b[A-Z]{1,3}\d+(?:\.\d+)?\b", question.upper())
        if number_match:
            number = number_match.group(0)
            incoming = [item for item in latest.references if item.target_sheet_number == number]
            if "reference" in lowered and incoming:
                return DrawingAnswer(
                    answer=f"{len(incoming)} explicit reference(s) point to {number}.",
                    sufficient=True,
                    evidence_type="explicit_cross_sheet_reference",
                    citations=tuple(item.citation for item in incoming),
                )
            sheet = next((item for item in latest.sheets if item.sheet_number == number), None)
            if sheet:
                region = next(
                    item for item in latest.regions if item.page_number == sheet.source_page_number
                )
                return DrawingAnswer(
                    answer=f"Sheet {number} is titled {sheet.sheet_title or 'unknown'}.",
                    sufficient=True,
                    evidence_type="title_block_metadata",
                    citations=(
                        citation(
                            region, sheet.sheet_revision_id, sheet.sheet_number, sheet.sheet_title
                        ),
                    ),
                )
        terms = [term for term in re.findall(r"[a-z0-9.-]+", lowered) if len(term) > 3]
        for sheet in latest.sheets:
            region = next(
                item for item in latest.regions if item.page_number == sheet.source_page_number
            )
            haystack = f"{sheet.sheet_number} {sheet.sheet_title} {region.text_span}".casefold()
            if terms and all(term in haystack for term in terms[-2:]):
                return DrawingAnswer(
                    answer=f"The requested text appears on Sheet {sheet.sheet_number}, {sheet.sheet_title or 'title unknown'}.",
                    sufficient=True,
                    evidence_type="native_pdf_text",
                    citations=(
                        citation(
                            region, sheet.sheet_revision_id, sheet.sheet_number, sheet.sheet_title
                        ),
                    ),
                )
        return self._unknown("The analyzed drawing evidence does not support an answer.")

    @staticmethod
    def _unknown(reason: str) -> DrawingAnswer:
        return DrawingAnswer(
            answer=reason,
            sufficient=False,
            evidence_type="insufficient_evidence",
            limitations=("Brunel does not infer unsupported graphical meaning.",),
        )
