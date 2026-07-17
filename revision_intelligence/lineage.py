"""Explicit-first revision lineage and conservative comparability assessment."""

from difflib import SequenceMatcher
from pathlib import Path

from document_processing.models import IngestedDocument

from .errors import CrossProjectComparisonError
from .models import ComparabilityAssessment, DocumentRevision, RevisionLineage


def _stem(name: str) -> str:
    value = Path(name).stem.casefold()
    for marker in ("revision", "rev", "r1", "r2", "r3", "-1", "-2", "_1", "_2"):
        value = value.replace(marker, "")
    return " ".join(value.replace("-", " ").replace("_", " ").split())


class RevisionLineageService:
    def build(self, documents: tuple[IngestedDocument, ...]) -> RevisionLineage:
        if not documents:
            raise ValueError("At least one document is required")
        projects = {item.document.project_id for item in documents}
        if len(projects) != 1:
            raise CrossProjectComparisonError("Revision lineage cannot cross project boundaries")
        family_ids = {
            item.document.document_family_id
            for item in documents
            if item.document.document_family_id
        }
        explicit = len(family_ids) == 1 and len(family_ids) > 0
        ordered = sorted(
            documents,
            key=lambda item: (
                item.document.revision_sequence is None,
                item.document.revision_sequence or 0,
                item.document.revision_date is None,
                item.document.revision_date or item.document.ingestion_timestamp.date(),
                item.document.document_id,
            ),
        )
        warnings = () if explicit else ("Document family relationship is inferred from metadata.",)
        return RevisionLineage(
            project_id=next(iter(projects)),
            document_family_id=next(iter(family_ids)) if explicit else None,
            revisions=tuple(
                DocumentRevision(document=item.document, relationship_confirmed=explicit)
                for item in ordered
            ),
            inferred=not explicit,
            warnings=warnings,
        )

    def assess(
        self, old: IngestedDocument, new: IngestedDocument, *, force: bool = False
    ) -> ComparabilityAssessment:
        if old.document.project_id != new.document.project_id:
            raise CrossProjectComparisonError("Documents belong to different projects")
        reasons: list[str] = []
        warnings: list[str] = []
        score = 0.0
        explicit_family = (
            old.document.document_family_id is not None
            and old.document.document_family_id == new.document.document_family_id
        )
        explicit_link = old.document.document_id == new.document.supersedes_document_id
        if explicit_family or explicit_link:
            score += 0.5
            reasons.append("Explicit revision lineage matches.")
        title_a = old.document.title or _stem(old.document.original_filename)
        title_b = new.document.title or _stem(new.document.original_filename)
        title_score = SequenceMatcher(None, title_a.casefold(), title_b.casefold()).ratio()
        score += 0.25 * title_score
        if old.document.document_type == new.document.document_type:
            score += 0.15
            reasons.append("Document types match.")
        if (
            old.document.document_number
            and old.document.document_number == new.document.document_number
        ):
            score += 0.1
            reasons.append("Document numbers match.")
        if not old.chunks or not new.chunks:
            return ComparabilityAssessment(
                comparable=False,
                score=0,
                reasons=("One or both documents have no extractable content.",),
                forced=force,
            )
        if not explicit_family:
            warnings.append("Revision family is not explicitly confirmed.")
        comparable = score >= 0.35
        if force and not comparable:
            comparable = True
            warnings.append("Comparison was user-forced and may be unreliable.")
        return ComparabilityAssessment(
            comparable=comparable,
            score=round(min(score, 1), 6),
            reasons=tuple(reasons),
            warnings=tuple(warnings),
            forced=force,
        )
