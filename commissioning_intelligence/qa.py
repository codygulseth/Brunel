from pydantic import BaseModel, ConfigDict

from .service import CommissioningService


class CommissioningAnswer(BaseModel):
    model_config = ConfigDict(frozen=True)
    answer: str
    citations: tuple[dict[str, object], ...] = ()
    limitations: tuple[str, ...] = ()


class CommissioningQuestionService:
    def __init__(self, service: CommissioningService):
        self.service = service

    def answer(self, project_id: str, question: str) -> CommissioningAnswer:
        prohibited = (
            "certify",
            "approve",
            "accept",
            "authorize",
            "waive",
            "substantial completion",
            "final completion",
            "compliance",
            "occupancy",
            "retainage",
        )
        if any(x in question.casefold() for x in prohibited):
            return CommissioningAnswer(
                answer="Brunel cannot certify systems, approve testing, accept equipment, authorize startup, energization or occupancy, waive deficiencies, confirm completion, determine compliance, or release retainage."
            )
        records = self.service.search(project_id, question) or self.service.search(project_id, "")
        if not records:
            return CommissioningAnswer(
                answer="No project-scoped commissioning evidence supports an answer."
            )
        citations = []
        for record in records[:5]:
            evidence = getattr(record, "evidence", ())
            citations.extend(
                {
                    "record_id": record.id,
                    "source": x.citation,
                    "excerpt": x.excerpt,
                    "human_confirmed": x.human_confirmed,
                }
                for x in evidence
            )
        return CommissioningAnswer(
            answer="; ".join(f"{x.__class__.__name__} {x.id}" for x in records[:5])
            + ". Reported and proposed statuses require authorized human review.",
            citations=tuple(citations),
            limitations=(
                "No readiness, acceptance, compliance, or completion certification is made.",
            ),
        )
