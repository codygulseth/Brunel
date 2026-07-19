from pydantic import BaseModel, ConfigDict
from .service import EnterpriseIntelligenceService


class EnterpriseAnswer(BaseModel):
    model_config = ConfigDict(frozen=True)
    answer: str
    citations: tuple[dict[str, object], ...] = ()
    limitations: tuple[str, ...] = ()


class EnterpriseQuestionService:
    def __init__(self, service: EnterpriseIntelligenceService):
        self.service = service

    def answer(
        self, org: str, question: str, portfolio_id: str, principal_id: str
    ) -> EnterpriseAnswer:
        prohibited = (
            "best contractor",
            "worst contractor",
            "award contract",
            "terminate",
            "negligent",
            "liable",
            "responsible",
            "breach",
            "entitled",
            "compliant",
            "performance review",
            "protected characteristic",
        )
        if any(x in question.casefold() for x in prohibited):
            return EnterpriseAnswer(
                answer="Brunel cannot rank people or companies, recommend awards or termination, determine negligence, liability, responsibility, breach, entitlement or compliance, produce employment decisions, or infer protected characteristics."
            )
        self.service.authorize(org, portfolio_id, principal_id)
        results = [
            x
            for x in self.service.repository.list("benchmarks", org)
            if x.portfolio_id == portfolio_id
        ]
        if not results:
            return EnterpriseAnswer(answer="No authorized enterprise benchmark supports an answer.")
        item = results[-1]
        citations = tuple(
            {"project_id": x.project_id, "record_id": x.record_id, "citation": x.citation}
            for x in item.provenance.authorized_citations
        )
        return EnterpriseAnswer(
            answer=f"Historical benchmark {item.definition_id}: {item.value} {item.unit}; sample size {item.sample_size}; {item.source_project_count} projects. This is an evidence-backed planning reference, not a guaranteed outcome or ranking.",
            citations=citations,
            limitations=item.limitations,
        )
