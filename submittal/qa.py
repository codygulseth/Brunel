"""Project-scoped operational submittal question answering."""

import re
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict

from .models import (
    OfficialDisposition,
    StalenessStatus,
    SubmittalEvidenceReference,
    SubmittalPackage,
    SubmittalRegisterItem,
    SubmittalStatus,
)
from .repository import JsonSubmittalRepository


class SubmittalAnswer(BaseModel):
    model_config = ConfigDict(frozen=True)
    answer: str
    records: tuple[SubmittalRegisterItem, ...] = ()
    packages: tuple[SubmittalPackage, ...] = ()
    citations: tuple[SubmittalEvidenceReference, ...] = ()
    distinctions: tuple[str, ...] = ()
    sufficient: bool = False


class SubmittalQuestionService:
    def __init__(self, repository: JsonSubmittalRepository) -> None:
        self.repository = repository

    def answer(self, project_id: str, question: str) -> SubmittalAnswer:
        lowered = question.casefold()
        items = self.repository.list_register(project_id)
        packages = self.repository.list_packages(project_id)
        if "overdue" in lowered:
            today = datetime.now(UTC).date()
            matches = tuple(
                item
                for item in items
                if item.status
                not in {
                    SubmittalStatus.CLOSED,
                    SubmittalStatus.VOID,
                    SubmittalStatus.SUPERSEDED,
                }
                and (
                    bool(
                        item.planned_submit_date
                        and item.planned_submit_date < today
                        and item.actual_submit_date is None
                    )
                    or bool(
                        item.required_response_date
                        and item.required_response_date < today
                        and item.actual_response_date is None
                    )
                )
            )
            return self._answer(
                "Overdue project-team submittal records: "
                + (", ".join(item.register_number for item in matches) if matches else "none"),
                matches,
                packages,
            )
        terms = {
            token
            for token in re.findall(r"[a-z0-9]+", lowered)
            if len(token) > 2 and token not in {"which", "what", "does", "this", "that"}
        }
        ranked: list[tuple[int, SubmittalRegisterItem]] = []
        for item in items:
            related_packages = tuple(
                package for package in packages if item.id in package.register_item_ids
            )
            package_text = " ".join(
                f"{package.package_number} {package.official_review_status or ''} "
                + " ".join(
                    f"{revision.title} {revision.description} "
                    f"{revision.product.name if revision.product else ''} "
                    f"{revision.product.model_number if revision.product and revision.product.model_number else ''}"
                    for revision in package.revisions
                )
                + " ".join(
                    " ".join(response.review_comments + response.required_corrections)
                    for response in package.official_responses
                )
                for package in related_packages
            )
            text = (
                f"{item.register_number} {item.specification_section} {item.description} "
                f"{item.status.value} {item.discipline or ''} {item.responsible_subcontractor or ''} "
                f"{' '.join(item.related_rfi_ids)} {package_text}"
            ).casefold()
            score = len(terms & set(re.findall(r"[a-z0-9]+", text)))
            if item.register_number.casefold() in lowered:
                score += 100
            if score:
                ranked.append((score, item))
        ranked.sort(key=lambda value: (-value[0], value[1].id))
        if not ranked:
            return SubmittalAnswer(answer="The project submittal records do not establish this.")
        item = ranked[0][1]
        related = tuple(package for package in packages if item.id in package.register_item_ids)
        latest = related[-1] if related else None
        response = (
            next((value for value in reversed(latest.official_responses) if value.official), None)
            if latest
            else None
        )
        answer = (
            f"Project-team register record {item.register_number} is {item.status.value}. "
            f"It is governed by Specification Section {item.specification_section}."
        )
        distinctions = ["specification requirement", "project-team register record"]
        if response:
            answer += (
                f" The explicitly identified official design-team disposition is "
                f"{response.disposition.value}: {response.original_disposition_text}."
            )
            if response.required_corrections:
                answer += " Required corrections: " + "; ".join(response.required_corrections) + "."
            distinctions.append("official design-team disposition")
        if "procurement" in lowered or "released" in lowered:
            answer += (
                " Procurement release has been human-confirmed."
                if item.procurement.procurement_release_date
                else " Procurement release has not been human-confirmed."
            )
        if "stale" in lowered and latest:
            assessment = latest.staleness_assessments[-1] if latest.staleness_assessments else None
            answer += (
                f" Package staleness is {assessment.status.value}: {'; '.join(assessment.reasons)}."
                if assessment
                else " No package staleness assessment is recorded."
            )
            distinctions.append("Brunel inference requiring human review")
        if "approved package" in lowered and latest:
            valid = latest.official_review_status in {
                OfficialDisposition.APPROVED,
                OfficialDisposition.APPROVED_AS_NOTED,
                OfficialDisposition.NO_EXCEPTION_TAKEN,
            } and not (
                latest.staleness_assessments
                and latest.staleness_assessments[-1].status
                in {StalenessStatus.POTENTIALLY_STALE, StalenessStatus.STALE}
            )
            answer += f" Current approved-package validity is {'confirmed by the record' if valid else 'not established'}; technical compliance is not inferred."
        return self._answer(answer, (item,), related, tuple(distinctions))

    def _answer(
        self,
        answer: str,
        items: tuple[SubmittalRegisterItem, ...],
        packages: tuple[SubmittalPackage, ...],
        distinctions: tuple[str, ...] = ("project-team register record",),
    ) -> SubmittalAnswer:
        citations = tuple(
            evidence
            for item in items
            for requirement in item.requirements
            for evidence in requirement.evidence
        ) + tuple(
            evidence
            for package in packages
            for response in package.official_responses
            if response.official
            for evidence in response.evidence
        )
        return SubmittalAnswer(
            answer=answer,
            records=items,
            packages=packages,
            citations=citations,
            distinctions=distinctions,
            sufficient=True,
        )
