"""Exact source excerpt selection and citation validation."""

import re
from hashlib import sha256

from .errors import CitationValidationError
from .models import AnswerCitation, RetrievedEvidence
from .query import ConstructionQueryNormalizer


class CitationBuilder:
    def __init__(self, maximum_excerpt_length: int = 320) -> None:
        if maximum_excerpt_length < 50:
            raise ValueError("maximum_excerpt_length must be at least 50")
        self.maximum_excerpt_length = maximum_excerpt_length
        self.normalizer = ConstructionQueryNormalizer()

    def build(
        self,
        evidence: RetrievedEvidence,
        *,
        question: str,
        ordinal: int,
    ) -> AnswerCitation:
        excerpt = self.excerpt(evidence.chunk.content, question)
        if excerpt not in evidence.chunk.content:
            raise CitationValidationError("Citation excerpt is not an exact source substring")
        digest = sha256(f"{evidence.chunk.id}\0{excerpt}".encode()).hexdigest()[:12]
        return AnswerCitation.from_source(
            evidence.chunk.citation,
            citation_id=f"cite_{ordinal}_{digest}",
            excerpt=excerpt,
            document_title=evidence.document_title,
        )

    def excerpt(self, content: str, question: str) -> str:
        sentences = [item for item in re.split(r"(?<=[.!?])\s+|\n+", content) if item.strip()]
        terms = set(self.normalizer.normalize(question).terms)
        selected = max(
            sentences or [content],
            key=lambda sentence: len(terms & set(self.normalizer.normalize(sentence).terms)),
        ).strip()
        if len(selected) <= self.maximum_excerpt_length:
            return selected
        lowered = selected.lower()
        positions = [lowered.find(term) for term in terms if lowered.find(term) >= 0]
        center = min(positions) if positions else 0
        start = max(0, center - self.maximum_excerpt_length // 3)
        end = min(len(selected), start + self.maximum_excerpt_length)
        start = max(0, end - self.maximum_excerpt_length)
        return selected[start:end].strip()
