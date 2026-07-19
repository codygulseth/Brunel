from pydantic import BaseModel, ConfigDict
from .service import FieldIntelligenceService


class FieldAnswer(BaseModel):
    model_config = ConfigDict(frozen=True)
    answer: str
    citations: tuple[dict[str, object], ...] = ()
    limitations: tuple[str, ...] = ()


class FieldQuestionService:
    def __init__(self, service: FieldIntelligenceService):
        self.service = service

    def answer(self, project_id, question):
        q = question.casefold()
        if any(x in q for x in ("caused", "entitled", "entitlement", "contractual delay")):
            return FieldAnswer(
                answer="Brunel cannot determine contractual delay, causation, responsibility, or entitlement from daily-report evidence."
            )
        terms = [
            x
            for x in q.split()
            if len(x) > 4 and x not in {"which", "reported", "yesterday", "there"}
        ]
        items = self.service.search(
            project_id, terms[0] if terms else ""
        ) or self.service.repository.list("observations", project_id)
        if not items:
            return FieldAnswer(
                answer="No project-scoped reviewed field evidence supports an answer."
            )
        citations = tuple(
            {
                "daily_report_revision_id": x.revision_id,
                "source_locator": x.citation.source_locator,
                "source_filename": x.citation.source_filename,
                "exact_excerpt": x.citation.exact_excerpt,
                "evidence_type": "human_confirmed_daily_record"
                if x.human_confirmed
                else "reported_field_observation",
            }
            for x in items[:5]
        )
        return FieldAnswer(
            answer="The daily report states: "
            + "; ".join(x.description for x in items[:5])
            + ". Unconfirmed observations remain proposals and do not update schedules or establish impact.",
            citations=citations,
        )
