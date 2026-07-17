"""Deterministic and optional structured answer providers."""

import json
import logging
from typing import Any

import httpx
from pydantic import ValidationError

from prompts.grounded_qa import SYSTEM_PROMPT, build_user_prompt

from .citations import CitationBuilder
from .errors import AnswerProviderError, InvalidStructuredOutputError
from .interfaces import LanguageModelClient
from .models import (
    AnswerDraft,
    AnswerStatus,
    EvidenceAssessment,
    EvidenceLevel,
    ProjectQuestion,
    RetrievalResult,
)

logger = logging.getLogger(__name__)


class ExtractiveAnswerProvider:
    """Local baseline that quotes the highest-ranking supplied evidence verbatim."""

    def __init__(self, maximum_evidence_chunks: int = 3, excerpt_length: int = 320) -> None:
        self.maximum_evidence_chunks = maximum_evidence_chunks
        self.citation_builder = CitationBuilder(excerpt_length)

    def generate(
        self,
        question: ProjectQuestion,
        retrieval: RetrievalResult,
        assessment: EvidenceAssessment,
    ) -> AnswerDraft:
        if not retrieval.evidence:
            return self._insufficient(question)
        candidates = retrieval.evidence[: self.maximum_evidence_chunks]
        unresolved: tuple[str, ...]
        if assessment.level == EvidenceLevel.CONFLICTING:
            cutoff = max(0.25, candidates[0].relevance_score * 0.6)
            selected = tuple(item for item in candidates if item.relevance_score >= cutoff)
            quotes = [
                f'"{self.citation_builder.excerpt(item.chunk.content, question.question)}"'
                for item in selected
            ]
            status = AnswerStatus.CONFLICTING_EVIDENCE
            answer = "The provided project documents conflict: " + " | ".join(quotes)
            unresolved = ("The conflicting sources require human review.",)
        else:
            selected = (candidates[0],)
            best = selected[0]
            quote = f'"{self.citation_builder.excerpt(best.chunk.content, question.question)}"'
            coverage = len(best.matched_terms) / max(len(retrieval.normalized_terms), 1)
            if assessment.level == EvidenceLevel.WEAK or coverage < 0.75:
                status = AnswerStatus.PARTIALLY_ANSWERED
                answer = "The provided project documents partially establish: " + quote
                unresolved = (
                    "The retrieved evidence does not address every part of the question.",
                )
            else:
                status = AnswerStatus.ANSWERED
                answer = "The provided project documents state: " + quote
                unresolved = ()
        return AnswerDraft(
            answer=answer,
            status=status,
            cited_chunk_ids=tuple(item.chunk.id for item in selected),
            evidence_summary=assessment.summary,
            unresolved_questions=unresolved,
        )

    @staticmethod
    def _insufficient(question: ProjectQuestion) -> AnswerDraft:
        return AnswerDraft(
            answer="The provided project documents do not establish this.",
            status=AnswerStatus.INSUFFICIENT_EVIDENCE,
            evidence_summary="No reliable supporting evidence was found.",
            unresolved_questions=(question.question,),
        )


class StructuredModelAnswerProvider:
    """Validates model JSON and retries only within a small configured limit."""

    def __init__(self, client: LanguageModelClient, retry_limit: int = 1) -> None:
        if retry_limit < 0 or retry_limit > 3:
            raise ValueError("retry_limit must be between 0 and 3")
        self.client = client
        self.retry_limit = retry_limit

    def generate(
        self,
        question: ProjectQuestion,
        retrieval: RetrievalResult,
        assessment: EvidenceAssessment,
    ) -> AnswerDraft:
        user_prompt = build_user_prompt(question, retrieval, assessment)
        last_error: Exception | None = None
        for attempt in range(self.retry_limit + 1):
            try:
                raw = self.client.complete(system_prompt=SYSTEM_PROMPT, user_prompt=user_prompt)
                return AnswerDraft.model_validate_json(raw)
            except (ValidationError, ValueError, json.JSONDecodeError) as exc:
                last_error = exc
                logger.warning(
                    "structured_answer_validation_failed",
                    extra={"attempt": attempt + 1, "retry_limit": self.retry_limit},
                )
        raise InvalidStructuredOutputError(
            "Answer provider returned invalid structured output"
        ) from last_error


class OpenAICompatibleClient:
    """Optional HTTP adapter for configured OpenAI-compatible chat-completion servers."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str,
        temperature: float = 0.1,
        timeout_seconds: float = 30,
    ) -> None:
        if not base_url or not model or not api_key:
            raise ValueError("base_url, model, and api_key are required")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.temperature = temperature
        self.timeout_seconds = timeout_seconds

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "temperature": self.temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise AnswerProviderError("Configured model provider request failed") from exc
        if not isinstance(content, str):
            raise AnswerProviderError("Configured model provider returned non-text content")
        return content
