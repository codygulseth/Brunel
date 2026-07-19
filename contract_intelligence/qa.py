from pydantic import BaseModel, ConfigDict
from .service import ContractIntelligenceService


class ContractAnswer(BaseModel):
    model_config = ConfigDict(frozen=True)
    answer: str
    citations: tuple[dict[str, object], ...] = ()
    limitations: tuple[str, ...] = ()


class ContractQuestionService:
    def __init__(self, service: ContractIntelligenceService):
        self.service = service

    def answer(self, project_id: str, question: str) -> ContractAnswer:
        prohibited = (
            "legal advice",
            "entitled",
            "entitlement",
            "breach",
            "liable",
            "liability",
            "responsible",
            "compensable",
            "excusable",
            "concurrent",
            "damages",
            "critical path",
            "waived",
            "enforceable",
            "legally sufficient",
            "litigation",
        )
        if any(x in question.casefold() for x in prohibited):
            return ContractAnswer(
                answer="Brunel cannot provide legal advice or determine entitlement, breach, liability, responsibility, compensability, excusability, concurrency, damages, critical-path delay, waiver, enforceability, or notice sufficiency."
            )
        records = self.service.search(project_id, question) or self.service.search(project_id, "")
        if not records:
            return ContractAnswer(
                answer="No project-scoped contractual evidence supports an answer."
            )
        citations = []
        for record in records[:5]:
            for evidence in getattr(record, "evidence", ()):
                citations.append(
                    {
                        "record_id": record.id,
                        "citation": evidence.citation,
                        "exact_text": evidence.exact_text,
                    }
                )
            citation = getattr(record, "citation", None)
            if citation:
                citations.append(
                    {
                        "record_id": record.id,
                        "citation": citation.citation,
                        "exact_text": citation.exact_text,
                    }
                )
        return ContractAnswer(
            answer="; ".join(f"{x.__class__.__name__} {x.id}" for x in records[:5])
            + ". Any contractual interpretation is a proposal requiring qualified human review.",
            citations=tuple(citations),
            limitations=(
                "Source language controls; summaries and deadline calculations are review proposals, not legal advice.",
            ),
        )
