"""Grounded question-answering orchestration and citation enforcement."""

import logging
import re

from .assessment import EvidenceAssessor
from .citations import CitationBuilder
from .errors import CitationValidationError
from .interfaces import GroundedAnswerProvider, Retriever
from .models import (
    AnswerStatus,
    EvidenceAssessment,
    EvidenceLevel,
    GroundedAnswer,
    ProjectQuestion,
    RetrievedEvidence,
    RetrievalQuery,
    RetrievalResult,
)

logger = logging.getLogger(__name__)


class CitedQuestionAnsweringService:
    def __init__(
        self,
        retriever: Retriever,
        provider: GroundedAnswerProvider,
        *,
        assessor: EvidenceAssessor | None = None,
        citation_builder: CitationBuilder | None = None,
        default_top_k: int = 5,
        minimum_relevance: float = 0.08,
        maximum_evidence_chunks: int = 8,
    ) -> None:
        self.retriever = retriever
        self.provider = provider
        self.assessor = assessor or EvidenceAssessor()
        self.citation_builder = citation_builder or CitationBuilder()
        self.default_top_k = default_top_k
        self.minimum_relevance = minimum_relevance
        self.maximum_evidence_chunks = maximum_evidence_chunks

    def answer(self, question: ProjectQuestion) -> GroundedAnswer:
        retrieval = self.retriever.retrieve(
            RetrievalQuery(
                project_id=question.project_id,
                text=question.question,
                limit=min(self.default_top_k, self.maximum_evidence_chunks),
                minimum_relevance=self.minimum_relevance,
            )
        )
        assessment = self.assessor.assess(retrieval)
        if assessment.level == EvidenceLevel.INSUFFICIENT:
            return self._insufficient(question, retrieval, assessment)
        try:
            draft = self.provider.generate(question, retrieval, assessment)
            evidence_by_id = {item.chunk.id: item for item in retrieval.evidence}
            if (
                draft.status
                not in {
                    AnswerStatus.INSUFFICIENT_EVIDENCE,
                    AnswerStatus.FAILED,
                }
                and not draft.cited_chunk_ids
            ):
                raise CitationValidationError(
                    "Answer provider returned a factual answer without citations"
                )
            unknown_ids = set(draft.cited_chunk_ids) - set(evidence_by_id)
            if unknown_ids:
                raise CitationValidationError(
                    "Answer provider cited evidence that was not retrieved"
                )
            self._validate_quoted_text(draft.answer, tuple(evidence_by_id.values()))
            citations = tuple(
                self.citation_builder.build(
                    evidence_by_id[chunk_id], question=question.question, ordinal=index
                )
                for index, chunk_id in enumerate(draft.cited_chunk_ids, start=1)
            )
            status = (
                AnswerStatus.CONFLICTING_EVIDENCE
                if assessment.level == EvidenceLevel.CONFLICTING
                else draft.status
            )
            return GroundedAnswer(
                question=question,
                answer=draft.answer,
                status=status,
                citations=citations,
                evidence_summary=draft.evidence_summary,
                evidence_assessment=assessment.model_copy(
                    update={"depends_on_inference": draft.depends_on_inference}
                ),
                unresolved_questions=draft.unresolved_questions,
                retrieval_metadata=self._retrieval_metadata(retrieval),
            )
        except Exception as exc:
            logger.exception(
                "grounded_answer_generation_failed",
                extra={"project_id": question.project_id, "error_type": type(exc).__name__},
            )
            failed_assessment = assessment.model_copy(
                update={
                    "summary": "Answer generation failed safely; no unvalidated answer was returned.",
                    "reasons": assessment.reasons + (type(exc).__name__,),
                }
            )
            return GroundedAnswer(
                question=question,
                answer="Brunel could not produce a validated evidence-backed answer.",
                status=AnswerStatus.FAILED,
                evidence_summary=failed_assessment.summary,
                evidence_assessment=failed_assessment,
                unresolved_questions=(question.question,),
                retrieval_metadata=self._retrieval_metadata(retrieval),
            )

    @staticmethod
    def _validate_quoted_text(answer: str, evidence: tuple[RetrievedEvidence, ...]) -> None:
        source_text = "\n".join(item.chunk.content for item in evidence)
        for quote in re.findall(r'"([^"]+)"', answer):
            if quote not in source_text:
                raise CitationValidationError(
                    "Answer contains a quotation absent from supplied evidence"
                )

    @staticmethod
    def _retrieval_metadata(retrieval: RetrievalResult) -> dict[str, int | float]:
        return {
            "sources_retrieved": len(retrieval.evidence),
            "candidates_considered": retrieval.candidates_considered,
            "duplicates_removed": retrieval.duplicates_removed,
            "top_relevance": (retrieval.evidence[0].relevance_score if retrieval.evidence else 0.0),
        }

    def _insufficient(
        self,
        question: ProjectQuestion,
        retrieval: RetrievalResult,
        assessment: EvidenceAssessment,
    ) -> GroundedAnswer:
        return GroundedAnswer(
            question=question,
            answer="The provided project documents do not establish this.",
            status=AnswerStatus.INSUFFICIENT_EVIDENCE,
            evidence_summary=assessment.summary,
            evidence_assessment=assessment,
            unresolved_questions=(question.question,),
            retrieval_metadata=self._retrieval_metadata(retrieval),
        )
