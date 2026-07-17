"""Evidence-only deterministic drafting, validation, and duplicate detection."""

import re
from difflib import SequenceMatcher
from typing import Protocol
from change_workflow.models import ProjectChange
from document_processing.models import CitationReference, IngestedDocument
from .models import (
    RFI,
    RFIDuplicateAssessment,
    RFIEvidenceReference,
    RFIQualityAssessment,
    RFIQualityIssue,
    RFIQualitySeverity,
)


class RFIDraftProvider(Protocol):
    name: str

    def improve(self, rfi: RFI) -> RFI: ...


class DocumentEvidenceReader(Protocol):
    def get(self, document_id: str) -> IngestedDocument | None: ...


class DeterministicRFIDrafter:
    def __init__(self, documents: DocumentEvidenceReader | None = None) -> None:
        self.documents = documents

    def draft_fields(
        self,
        change: ProjectChange,
        instructions: str | None = None,
        selected_evidence: tuple[RFIEvidenceReference, ...] = (),
    ) -> tuple[str, str, str, tuple[RFIEvidenceReference, ...]]:
        evidence = selected_evidence or tuple(
            self._evidence(citation, document_id)
            for citation, document_id in (
                (change.evidence.old_citation, change.evidence.old_document_id),
                (change.evidence.new_citation, change.evidence.new_document_id),
            )
            if citation and document_id
        )
        if not evidence:
            return change.title, "", "", ()
        subject = change.title
        if subject.casefold() in {"modified content", "added content", "removed content"}:
            source_subject = evidence[-1].excerpt.splitlines()[0].split(".", 1)[0].strip()
            subject = f"Clarification: {source_subject[:100]}"
        background = f"Revision comparison {change.evidence.comparison_id} identified a project change requiring clarification. {change.description}"
        question = (
            instructions
            or "Please confirm the governing requirement and provide direction for coordination and implementation."
        )
        return subject, question, background, evidence

    def _evidence(self, citation: CitationReference, document_id: str) -> RFIEvidenceReference:
        excerpt = "Exact excerpt remains available through the cited source chunk."
        document = self.documents.get(document_id) if self.documents else None
        if document:
            chunk = next((item for item in document.chunks if item.id == citation.chunk_id), None)
            if chunk:
                excerpt = chunk.content
        return RFIEvidenceReference(citation=citation, excerpt=excerpt)


class RFIQualityValidator:
    def assess(self, rfi: RFI) -> RFIQualityAssessment:
        issues: list[RFIQualityIssue] = []
        for missing, value in (("subject", rfi.subject), ("question", rfi.question)):
            if not value.strip():
                issues.append(
                    RFIQualityIssue(
                        code=f"missing_{missing}",
                        severity=RFIQualitySeverity.BLOCKING,
                        message=f"RFI {missing} is required.",
                    )
                )
        if not rfi.evidence:
            issues.append(
                RFIQualityIssue(
                    code="missing_evidence",
                    severity=RFIQualitySeverity.BLOCKING,
                    message="At least one source citation is required for evidence-backed issue.",
                )
            )
        elif any(not item.citation.document_name.strip() for item in rfi.evidence):
            issues.append(
                RFIQualityIssue(
                    code="missing_document_reference",
                    severity=RFIQualitySeverity.BLOCKING,
                    message="Every evidence item must identify its source document.",
                )
            )
        if rfi.question.count("?") > 2:
            issues.append(
                RFIQualityIssue(
                    code="multiple_questions",
                    severity=RFIQualitySeverity.WARNING,
                    message="The draft may contain multiple unrelated questions; confirm scope.",
                )
            )
        if re.search(r"\b(please advise|as needed|appropriate|somehow)\b", rfi.question, re.I):
            issues.append(
                RFIQualityIssue(
                    code="vague_wording",
                    severity=RFIQualitySeverity.WARNING,
                    message="The requested direction may be vague.",
                )
            )
        if not rfi.responsible_party:
            issues.append(
                RFIQualityIssue(
                    code="missing_responsible_party",
                    severity=RFIQualitySeverity.WARNING,
                    message="Responsible design party is not identified.",
                )
            )
        if not rfi.required_date:
            issues.append(
                RFIQualityIssue(
                    code="missing_required_date",
                    severity=RFIQualitySeverity.WARNING,
                    message="Required response date is not set.",
                )
            )
        if len(rfi.question) > 1500:
            issues.append(
                RFIQualityIssue(
                    code="excessive_length",
                    severity=RFIQualitySeverity.WARNING,
                    message="Question may be too long.",
                )
            )
        if re.search(r"\b(failure|negligent|obviously wrong)\b", rfi.question, re.I):
            issues.append(
                RFIQualityIssue(
                    code="accusatory_language",
                    severity=RFIQualitySeverity.WARNING,
                    message="Use neutral construction language.",
                )
            )
        source = " ".join(item.excerpt for item in rfi.evidence)
        for claim in re.findall(
            r"\b\d+(?:[,.]\d+)*(?:\s*(?:psi|weeks?|days?|feet|inches?))?\b",
            f"{rfi.background} {rfi.question}",
            re.I,
        ):
            if claim not in source and claim not in " ".join(
                rfi.drawing_references + rfi.specification_references
            ):
                issues.append(
                    RFIQualityIssue(
                        code="unsupported_numeric_claim",
                        severity=RFIQualitySeverity.WARNING,
                        message=f"Numeric claim '{claim}' is not present in selected evidence.",
                    )
                )
        return RFIQualityAssessment(
            valid=not any(i.severity == RFIQualitySeverity.BLOCKING for i in issues),
            issues=tuple(issues),
        )


class RFIDuplicateDetector:
    def __init__(self, threshold: float = 0.72) -> None:
        self.threshold = threshold

    def assess(self, candidate: RFI, existing: tuple[RFI, ...]) -> RFIDuplicateAssessment:
        matches = []
        reasons = []
        for item in existing:
            same_change = bool(
                set(candidate.related_project_change_ids) & set(item.related_project_change_ids)
            )
            similarity = SequenceMatcher(
                None, candidate.question.casefold(), item.question.casefold()
            ).ratio()
            shared_evidence = bool(
                {x.citation.chunk_id for x in candidate.evidence}
                & {x.citation.chunk_id for x in item.evidence}
            )
            shared_reference = bool(
                set(candidate.drawing_references) & set(item.drawing_references)
                or set(candidate.specification_references) & set(item.specification_references)
            )
            if same_change or shared_evidence or shared_reference or similarity >= self.threshold:
                matches.append(item.id)
                reasons.append(
                    "same_project_change"
                    if same_change
                    else "shared_evidence"
                    if shared_evidence
                    else "shared_document_reference"
                    if shared_reference
                    else f"question_similarity:{similarity:.2f}"
                )
        return RFIDuplicateAssessment(
            possible_duplicate_ids=tuple(matches),
            reasons=tuple(reasons),
            strength="strong" if matches else "none",
            recommended_review_action=(
                "Review the possible duplicates before issue; do not merge automatically."
                if matches
                else "No duplicate indicators found."
            ),
        )
