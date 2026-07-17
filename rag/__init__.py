"""Brunel's project-scoped retrieval and cited-answering foundation."""

from .interfaces import GroundedAnswerProvider, LanguageModelClient, Retriever
from .assessment import EvidenceAssessor
from .citations import CitationBuilder
from .models import (
    AnswerCitation,
    AnswerDraft,
    AnswerStatus,
    EvidenceAssessment,
    EvidenceLevel,
    GroundedAnswer,
    ProjectQuestion,
    RetrievedEvidence,
    RetrievalFilters,
    RetrievalQuery,
    RetrievalResult,
)
from .providers import (
    ExtractiveAnswerProvider,
    OpenAICompatibleClient,
    StructuredModelAnswerProvider,
)
from .qa import CitedQuestionAnsweringService
from .retrieval import LocalProjectRetriever

__all__ = [
    "AnswerCitation",
    "AnswerDraft",
    "AnswerStatus",
    "CitedQuestionAnsweringService",
    "CitationBuilder",
    "EvidenceAssessor",
    "EvidenceAssessment",
    "EvidenceLevel",
    "GroundedAnswer",
    "GroundedAnswerProvider",
    "ExtractiveAnswerProvider",
    "LanguageModelClient",
    "ProjectQuestion",
    "LocalProjectRetriever",
    "OpenAICompatibleClient",
    "RetrievedEvidence",
    "RetrievalFilters",
    "RetrievalQuery",
    "RetrievalResult",
    "Retriever",
    "StructuredModelAnswerProvider",
]
