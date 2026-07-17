"""Deterministic operational procurement answers with typed evidence."""

from pydantic import BaseModel, ConfigDict
from .service import ProcurementService


class ProcurementAnswer(BaseModel):
    model_config = ConfigDict(frozen=True)
    answer: str
    citations: tuple[dict[str, object], ...] = ()
    limitations: tuple[str, ...] = ()


class ProcurementQuestionService:
    def __init__(self, service: ProcurementService):
        self.service = service

    def answer(self, project_id: str, question: str) -> ProcurementAnswer:
        q = question.casefold()
        items = self.service.list_items(
            project_id,
            query=next(
                (
                    x
                    for x in q.split()
                    if len(x) > 4 and x not in {"which", "what", "released", "procurement"}
                ),
                None,
            ),
        ) or self.service.list_items(project_id)
        if not items:
            return ProcurementAnswer(
                answer="No project-scoped procurement record supports an answer.",
                limitations=("Brunel does not infer missing procurement information.",),
            )
        item = items[0]
        citations = tuple(
            {
                "evidence_type": c.evidence_type,
                "source_type": c.source_type,
                "source_id": c.source_id,
                "document_id": c.document_id,
                "page_number": c.page_number,
                "exact_excerpt": c.exact_excerpt,
            }
            for c in item.citations
        )
        if "released" in q or "release" in q:
            authorized = any(x.status == "authorized" for x in item.release_authorizations)
            return ProcurementAnswer(
                answer=f"{item.procurement_number} is {item.status.value}. Release authorization {'is recorded' if authorized else 'has not been recorded'}. An approved submittal alone is not authorization to buy.",
                citations=citations,
            )
        if "lead time" in q:
            lead = next((x for x in item.lead_times if x.id == item.active_lead_time_id), None)
            return ProcurementAnswer(
                answer=f"The current {'confirmed evidence' if lead and lead.confirmed else 'planning assumption'} is {lead.duration} {lead.unit} ({lead.definition}), provided by {lead.provided_by or 'an unspecified source'}."
                if lead
                else "No active lead-time evidence is recorded.",
                citations=citations,
            )
        if "cost" in q:
            return ProcurementAnswer(
                answer="No confirmed cost impact is recorded. Brunel does not infer commercial impact.",
                citations=citations,
            )
        exposure = (
            item.exposure_assessments[-1]
            if item.exposure_assessments
            else self.service.assess_exposure(project_id, item.id)
        )
        return ProcurementAnswer(
            answer=f"{item.procurement_number} is {item.status.value}; potential exposure is {exposure.level.value} because {'; '.join(exposure.reasons)} This is decision support, not a confirmed project delay.",
            citations=citations,
        )
