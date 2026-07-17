"""Deterministic project-scoped term-frequency retrieval."""

import logging
import math
import re
from collections import Counter

from document_processing.interfaces import DocumentRepository
from document_processing.models import DocumentChunk, IngestedDocument, SourceDocument

from .models import RetrievedEvidence, RetrievalFilters, RetrievalQuery, RetrievalResult
from .query import ConstructionQueryNormalizer, NormalizedQuery, canonical_identifier

logger = logging.getLogger(__name__)


class LocalProjectRetriever:
    """Strong local baseline using term coverage, frequency, phrases, and identifiers."""

    def __init__(
        self,
        repository: DocumentRepository,
        normalizer: ConstructionQueryNormalizer | None = None,
    ) -> None:
        self.repository = repository
        self.normalizer = normalizer or ConstructionQueryNormalizer()

    def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        normalized = self.normalizer.normalize(query.text)
        documents = self.repository.list_by_project(query.project_id)
        scored: list[RetrievedEvidence] = []
        candidates = 0
        duplicates = 0
        seen_content: set[str] = set()
        for ingested in documents:
            if not self._document_matches(ingested, query.filters):
                continue
            for chunk in ingested.chunks:
                if not self._chunk_matches(chunk, ingested.document, query.filters):
                    continue
                candidates += 1
                fingerprint = " ".join(chunk.content.lower().split())
                if fingerprint in seen_content:
                    duplicates += 1
                    continue
                seen_content.add(fingerprint)
                evidence = self._score(ingested, chunk, normalized)
                if evidence.relevance_score >= query.minimum_relevance:
                    scored.append(evidence)
        scored.sort(key=lambda item: (-item.relevance_score, item.chunk.id))
        result = RetrievalResult(
            query=query,
            normalized_terms=normalized.terms,
            evidence=tuple(scored[: query.limit]),
            candidates_considered=candidates,
            duplicates_removed=duplicates,
        )
        logger.info(
            "project_retrieval_completed",
            extra={
                "project_id": query.project_id,
                "candidate_count": candidates,
                "result_count": len(result.evidence),
                "duplicates_removed": duplicates,
            },
        )
        return result

    def _score(
        self, ingested: IngestedDocument, chunk: DocumentChunk, normalized: NormalizedQuery
    ) -> RetrievedEvidence:
        metadata_text = " ".join(
            value
            for value in (
                ingested.document.title,
                ingested.document.original_filename,
                chunk.citation.sheet_number,
                chunk.citation.specification_section,
            )
            if value
        )
        searchable = f"{chunk.content} {metadata_text}".lower()
        tokens = re.findall(r"[a-z0-9]+(?:[-.][a-z0-9]+)*", searchable)
        counts = Counter(tokens)
        matched_terms = tuple(term for term in normalized.terms if counts[term] > 0)
        coverage = len(matched_terms) / max(len(normalized.terms), 1)
        frequency = sum(min(counts[term], 3) for term in matched_terms)
        frequency_score = min(math.log1p(frequency) / math.log(10), 1.0)
        phrase_score = 1.0 if normalized.text and normalized.text in searchable else 0.0
        searchable_identifiers = set(self.normalizer.identifiers_in(searchable))
        matched_identifiers = tuple(
            identifier
            for identifier in normalized.identifiers
            if identifier in searchable_identifiers
        )
        identifier_score = (
            len(matched_identifiers) / len(normalized.identifiers)
            if normalized.identifiers
            else 0.0
        )
        score = min(
            1.0,
            0.6 * coverage + 0.15 * frequency_score + 0.1 * phrase_score + 0.15 * identifier_score,
        )
        return RetrievedEvidence(
            chunk=chunk,
            document_title=ingested.document.title,
            document_type=ingested.document.document_type,
            relevance_score=round(score, 6),
            matched_terms=matched_terms,
            matched_identifiers=matched_identifiers,
        )

    @staticmethod
    def _document_matches(document: IngestedDocument, filters: RetrievalFilters) -> bool:
        source = document.document
        if filters.document_type is not None and source.document_type != filters.document_type:
            return False
        if filters.document_id is not None and source.document_id != filters.document_id:
            return False
        if (
            filters.sheet_number is not None
            and source.sheet_number is not None
            and canonical_identifier(source.sheet_number)
            != canonical_identifier(filters.sheet_number)
        ):
            return False
        if (
            filters.specification_section is not None
            and source.specification_section is not None
            and canonical_identifier(source.specification_section)
            != canonical_identifier(filters.specification_section)
        ):
            return False
        return True

    @staticmethod
    def _chunk_matches(
        chunk: DocumentChunk, source: SourceDocument, filters: RetrievalFilters
    ) -> bool:
        if filters.page_number is not None and chunk.page_number != filters.page_number:
            return False
        if filters.sheet_number is not None:
            effective_sheet = chunk.citation.sheet_number or source.sheet_number
            if effective_sheet is None or canonical_identifier(
                effective_sheet
            ) != canonical_identifier(filters.sheet_number):
                return False
        if filters.specification_section is not None:
            effective_section = chunk.citation.specification_section or source.specification_section
            if effective_section is None or canonical_identifier(
                effective_section
            ) != canonical_identifier(filters.specification_section):
                return False
        return True
