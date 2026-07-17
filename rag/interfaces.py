"""Provider-neutral retrieval and answer-generation interfaces."""

from typing import Protocol

from .models import (
    AnswerDraft,
    EvidenceAssessment,
    ProjectQuestion,
    RetrievalQuery,
    RetrievalResult,
)


class Retriever(Protocol):
    def retrieve(self, query: RetrievalQuery) -> RetrievalResult: ...


class GroundedAnswerProvider(Protocol):
    def generate(
        self,
        question: ProjectQuestion,
        retrieval: RetrievalResult,
        assessment: EvidenceAssessment,
    ) -> AnswerDraft: ...


class LanguageModelClient(Protocol):
    def complete(self, *, system_prompt: str, user_prompt: str) -> str: ...
