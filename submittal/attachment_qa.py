"""Project-scoped retrieval and cited Q&A over submitted attachment content."""

import re

from .attachment_models import (
    AttachmentEvidenceReference,
    AttachmentQuestionAnswer,
    AttachmentSearchResult,
    AttachmentType,
)
from .attachment_repository import JsonAttachmentIntelligenceRepository
from .models import SubmittalEvidenceReference
from .repository import JsonSubmittalRepository


class AttachmentSearchService:
    def __init__(
        self,
        repository: JsonAttachmentIntelligenceRepository,
        submittals: JsonSubmittalRepository | None = None,
    ) -> None:
        self.repository = repository
        self.submittals = submittals

    def search(
        self,
        project_id: str,
        query: str,
        *,
        package_id: str | None = None,
        package_revision: int | None = None,
        attachment_type: AttachmentType | None = None,
        limit: int = 10,
    ) -> tuple[AttachmentSearchResult, ...]:
        terms = _terms(query)
        ranked: list[AttachmentSearchResult] = []
        for extraction in self.repository.list_extractions(project_id):
            if package_id and extraction.package_id != package_id:
                continue
            if package_revision and extraction.package_revision != package_revision:
                continue
            if attachment_type and extraction.classification.inferred_type != attachment_type:
                continue
            evidence = _evidence(extraction)
            attachment = self.repository.get_attachment(project_id, extraction.attachment_id)
            package = (
                self.submittals.get_package(project_id, extraction.package_id)
                if self.submittals
                else None
            )
            register_numbers = (
                tuple(
                    item.register_number
                    for item_id in package.register_item_ids
                    if (item := self.submittals.get_register(project_id, item_id))
                )
                if package and self.submittals
                else ()
            )
            searchable = " ".join(
                [
                    attachment.display_name if attachment else "",
                    package.package_number if package else "",
                    *register_numbers,
                    extraction.classification.inferred_type.value,
                    *(value for item in extraction.identities for value in _identity_values(item)),
                    *(f"{item.name} {item.value}" for item in extraction.technical_attributes),
                    *(f"{item.reference_type} {item.value}" for item in extraction.references),
                    *(item.excerpt for item in evidence),
                ]
            ).casefold()
            score = len(terms & set(re.findall(r"[a-z0-9.-]+", searchable)))
            if query.casefold() in searchable:
                score += 3
            if not score:
                continue
            matching = (
                tuple(
                    item
                    for item in evidence
                    if terms & set(re.findall(r"[a-z0-9.-]+", item.excerpt.casefold()))
                )
                or evidence[:3]
            )
            ranked.append(
                AttachmentSearchResult(
                    attachment_id=extraction.attachment_id,
                    attachment_revision_id=extraction.attachment_revision_id,
                    package_id=extraction.package_id,
                    score=score,
                    excerpts=matching[:5],
                )
            )
        return tuple(sorted(ranked, key=lambda item: (-item.score, item.attachment_id))[:limit])


class AttachmentQuestionService:
    """Answer only what cited submitted attachment or specification records establish."""

    def __init__(
        self,
        attachments: JsonAttachmentIntelligenceRepository,
        submittals: JsonSubmittalRepository,
    ) -> None:
        self.attachments = attachments
        self.submittals = submittals
        self.search_service = AttachmentSearchService(attachments, submittals)

    def answer(
        self, project_id: str, question: str, *, package_id: str | None = None
    ) -> AttachmentQuestionAnswer:
        lowered = question.casefold()
        evidence_sets = (
            self.attachments.list_evidence_sets(project_id, package_id) if package_id else ()
        )
        current_evidence = evidence_sets[-1] if evidence_sets else None
        if "procurement" in lowered and ("release" in lowered or "released" in lowered):
            return AttachmentQuestionAnswer(
                answer=(
                    "Attachment evidence cannot authorize procurement release. Procurement release "
                    "remains a human-controlled canonical submittal action."
                ),
                distinctions=(
                    "No product approval or procurement authority is inferred from submitted evidence.",
                ),
            )
        if current_evidence and "missing" in lowered:
            missing = current_evidence.missing_attachments
            return AttachmentQuestionAnswer(
                answer=(
                    "Brunel flagged these required attachment types as missing: "
                    + ", ".join(item.missing_type.value for item in missing)
                    if missing
                    else "The current evidence set does not flag a required attachment type as missing."
                ),
                specification_citations=tuple(
                    dict.fromkeys(item.requirement_evidence for item in missing)
                ),
                distinctions=("Brunel completeness indicator; human review remains required.",),
                sufficient=True,
            )
        if current_evidence and ("conflict" in lowered or "match" in lowered):
            conflicts = current_evidence.conflicts
            citations = tuple(
                dict.fromkeys(item for conflict in conflicts for item in conflict.evidence)
            )
            return AttachmentQuestionAnswer(
                answer=(
                    "Brunel flagged unresolved submitted-value conflicts for: "
                    + ", ".join(item.subject for item in conflicts)
                    if conflicts
                    else "The current evidence set does not contain an unresolved submitted-value conflict."
                ),
                attachment_citations=citations,
                distinctions=("Brunel conflict indicator; configuration context may differ.",),
                sufficient=True,
            )
        if current_evidence and (
            "deviation" in lowered or "differ" in lowered or "difference" in lowered
        ):
            deviations = current_evidence.possible_deviations
            return AttachmentQuestionAnswer(
                answer=(
                    "Brunel flagged possible specification differences: "
                    + "; ".join(
                        f"{item.attribute_name}: specified {item.specified_value}, submitted {item.submitted_value}"
                        for item in deviations
                    )
                    if deviations
                    else "The current evidence set does not flag an explicit technical-value difference."
                ),
                specification_citations=tuple(
                    dict.fromkeys(item.specification_evidence for item in deviations)
                ),
                attachment_citations=tuple(
                    dict.fromkeys(item.attachment_evidence for item in deviations)
                ),
                distinctions=(
                    "Possible deviation only; acceptability and equivalency are not determined.",
                ),
                sufficient=True,
            )
        if current_evidence and any(
            term in lowered for term in ("confirmed", "unconfirmed", "compliance matrix")
        ):
            mappings = current_evidence.compliance_mappings
            unconfirmed = tuple(
                item for item in mappings if item.human_confirmation_status.value == "unreviewed"
            )
            return AttachmentQuestionAnswer(
                answer=(
                    f"{len(unconfirmed)} of {len(mappings)} current proposed mappings remain unconfirmed. "
                    "System proposals are not authoritative human judgments."
                ),
                specification_citations=tuple(
                    dict.fromkeys(item.specification_evidence for item in mappings)
                ),
                attachment_citations=tuple(
                    dict.fromkeys(
                        item for mapping in mappings for item in mapping.supporting_evidence
                    )
                ),
                distinctions=("Brunel-proposed mapping versus human-confirmed review judgment.",),
                sufficient=True,
            )
        if package_id and ("what changed" in lowered or "between" in lowered):
            comparisons = self.attachments.list_comparisons(project_id, package_id)
            if comparisons:
                comparison = comparisons[-1]
                return AttachmentQuestionAnswer(
                    answer="Package attachment changes: "
                    + "; ".join(
                        f"{item.change_type.value} ({item.subject})" for item in comparison.changes
                    ),
                    attachment_citations=tuple(
                        dict.fromkeys(
                            item
                            for change in comparison.changes
                            for item in change.old_evidence + change.new_evidence
                        )
                    ),
                    distinctions=(
                        "Deterministic package-revision comparison; human review required.",
                    ),
                    sufficient=True,
                )
        if package_id and "stale" in lowered:
            assessments = self.attachments.list_staleness(project_id, package_id)
            return AttachmentQuestionAnswer(
                answer=(
                    f"Latest attachment staleness status is {assessments[-1].status.value}: "
                    + "; ".join(assessments[-1].reasons)
                    if assessments
                    else "No attachment-driven staleness assessment is recorded."
                ),
                distinctions=(
                    "Staleness is a Brunel workflow state, not an official disposition.",
                ),
                sufficient=bool(assessments),
            )
        results = self.search_service.search(project_id, question, package_id=package_id)
        if package_id:
            if evidence_sets:
                current_revision = max(item.package_revision for item in evidence_sets)
                current = tuple(
                    item for item in evidence_sets if item.package_revision == current_revision
                )[-1]
                allowed = set(current.attachment_revision_ids)
                results = tuple(
                    result for result in results if result.attachment_revision_id in allowed
                )
        if not results:
            return AttachmentQuestionAnswer(
                answer="The submitted attachment record does not establish this.",
                distinctions=(
                    "No design-compliance conclusion was inferred.",
                    "No official reviewer disposition was inferred.",
                ),
            )
        citations = tuple(dict.fromkeys(item for result in results[:3] for item in result.excerpts))
        excerpts = "; ".join(item.excerpt.strip() for item in citations[:4])
        answer = f"Submitted attachment evidence states: {excerpts}"
        specification_citations: tuple[SubmittalEvidenceReference, ...] = ()
        if package_id:
            sets = self.attachments.list_evidence_sets(project_id, package_id)
            if sets:
                mappings = sets[-1].compliance_mappings
                specification_citations = tuple(
                    dict.fromkeys(item.specification_evidence for item in mappings)
                )
        return AttachmentQuestionAnswer(
            answer=answer,
            specification_citations=specification_citations,
            attachment_citations=citations,
            distinctions=(
                "Submitted attachment fact; not a professional design-compliance determination.",
                "Brunel extraction; human review remains required.",
                "Official reviewer dispositions are separate records and are not inferred here.",
            ),
            sufficient=True,
        )


def _terms(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9.-]+", value.casefold())
        if len(token) > 1 and token not in {"what", "which", "does", "the", "this", "that"}
    }


def _identity_values(item: object) -> tuple[str, ...]:
    fields = (
        "manufacturer",
        "product_family",
        "product_name",
        "model_number",
        "catalog_number",
        "series",
        "category",
    )
    return tuple(str(value) for field in fields if (value := getattr(item, field, None)))


def _evidence(extraction: object) -> tuple[AttachmentEvidenceReference, ...]:
    identities = getattr(extraction, "identities", ())
    attributes = getattr(extraction, "technical_attributes", ())
    references = getattr(extraction, "references", ())
    return tuple(
        dict.fromkeys(
            tuple(value for item in identities for value in item.evidence)
            + tuple(item.evidence for item in attributes)
            + tuple(item.evidence for item in references)
        )
    )
