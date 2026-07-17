"""Project-scoped RFI operational question answering."""

import re
from pydantic import BaseModel, ConfigDict
from .models import RFI, RFIEvidenceReference, RFIImpactType, RFIResponseType, RFIStatus
from .repository import JsonRFIRepository


class RFIAnswer(BaseModel):
    model_config = ConfigDict(frozen=True)
    answer: str
    records: tuple[RFI, ...] = ()
    evidence_type: str = "rfi_record"
    sufficient: bool = False
    citations: tuple[RFIEvidenceReference, ...] = ()
    distinctions: tuple[str, ...] = ()


class RFIQuestionService:
    def __init__(self, repository: JsonRFIRepository) -> None:
        self.repository = repository

    def answer(self, project_id: str, question: str) -> RFIAnswer:
        lowered = question.casefold()
        project_items = self.repository.list(project_id)
        if "overdue" in lowered:
            from datetime import UTC, datetime

            today = datetime.now(UTC).date()
            matches = tuple(
                item
                for item in project_items
                if item.required_date
                and item.required_date < today
                and item.status not in {RFIStatus.CLOSED, RFIStatus.RESOLVED, RFIStatus.VOID}
            )
            return RFIAnswer(
                answer=(
                    "Overdue project-team RFI records: "
                    + (", ".join(item.number for item in matches) if matches else "none")
                ),
                records=matches,
                sufficient=True,
                distinctions=("project-team record",),
            )
        terms = {x for x in re.findall(r"[a-z0-9]+", question.casefold()) if len(x) > 2}
        ranked = []
        for item in project_items:
            response = next(
                (
                    x
                    for x in reversed(item.responses)
                    if x.response_type == RFIResponseType.OFFICIAL
                ),
                None,
            )
            text = f"{item.number} {item.subject} {item.question} {item.background} {item.status.value} {response.text if response else ''}".casefold()
            score = len(terms & set(re.findall(r"[a-z0-9]+", text)))
            if score:
                ranked.append((score, item, response))
        ranked.sort(key=lambda x: (-x[0], x[1].id))
        if not ranked:
            return RFIAnswer(answer="The project RFI log does not establish this.")
        _, item, response = ranked[0]
        answer = f"RFI record {item.number} is {item.status.value}. It was created from project change(s): {', '.join(item.related_project_change_ids) or 'none recorded'}."
        distinctions = ["project-team RFI record", "source-document evidence"]
        if response:
            answer += f" The explicitly recorded official response states: {response.text}"
            distinctions.append("official RFI response")
        if "confirmed cost" in lowered or "cost impact" in lowered:
            confirmed = any(
                impact.impact_type == RFIImpactType.COST and impact.certainty.value == "confirmed"
                for impact in item.impacts
            )
            answer += (
                " A confirmed cost impact is explicitly recorded."
                if confirmed
                else " No confirmed cost impact is recorded; inferred exposure is not confirmation."
            )
        else:
            answer += " Potential cost and schedule impacts remain unconfirmed unless explicitly reviewed."
        citations = item.evidence + (response.citations if response else ())
        return RFIAnswer(
            answer=answer,
            records=(item,),
            sufficient=True,
            citations=citations,
            distinctions=tuple(distinctions),
        )
