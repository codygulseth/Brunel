from pydantic import BaseModel, ConfigDict
from .service import RiskIntelligenceService


class RiskAnswer(BaseModel):
    model_config = ConfigDict(frozen=True)
    answer: str
    citations: tuple[dict[str, object], ...] = ()
    limitations: tuple[str, ...] = ()


class RiskQuestionService:
    def __init__(self, service: RiskIntelligenceService):
        self.service = service

    def answer(self, project_id: str, question: str) -> RiskAnswer:
        q = question.casefold()
        if any(
            x in q
            for x in ("delay", "fault", "responsib", "entitlement", "compliance", "critical path")
        ):
            return RiskAnswer(
                answer="Brunel cannot determine delay, fault, responsibility, entitlement, critical-path impact, or compliance. It can present evidence-backed candidates for human review."
            )
        items = self.service.search(project_id, question) or self.service.repository.list(
            "risks", project_id
        )
        if not items:
            return RiskAnswer(answer="No project-scoped risk evidence supports an answer.")
        citations = tuple(
            {
                "risk_id": r.id,
                "record_ids": r.linked_record_ids,
                "evidence": tuple(e.citation for e in r.evidence),
            }
            for r in items[:5]
        )
        return RiskAnswer(
            answer="; ".join(
                f"{r.title} ({r.status}; proposed {r.score.severity})" for r in items[:5]
            )
            + ". These are review items, not autonomous project determinations.",
            citations=citations,
            limitations=(
                "Correlation and scoring are deterministic proposals; human review is required.",
            ),
        )
