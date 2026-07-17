"""Deterministic, descriptive evidence-sufficiency assessment."""

import re
from collections import defaultdict

from .models import EvidenceAssessment, EvidenceLevel, RetrievalResult

MEASUREMENT_PATTERN = re.compile(
    r"\b(\d+(?:,\d{3})*(?:\.\d+)?)\s*(psi|ksi|hour|hours|hr|hrs|feet|foot|ft|inch|inches|in)\b",
    re.IGNORECASE,
)
APPROVAL_PATTERN = re.compile(r"\b(not approved|approved|rejected|revise and resubmit)\b", re.I)


class EvidenceAssessor:
    def assess(self, retrieval: RetrievalResult) -> EvidenceAssessment:
        evidence = retrieval.evidence
        if not evidence:
            return EvidenceAssessment(
                level=EvidenceLevel.INSUFFICIENT,
                summary="No relevant project-document evidence was retrieved.",
                reasons=("No chunks met the minimum relevance threshold.",),
                supporting_chunk_count=0,
            )

        conflict_reasons = self._conflicts(retrieval)
        exact_identifier = any(item.matched_identifiers for item in evidence)
        metadata_complete = all(
            item.chunk.citation.document_name
            and item.chunk.citation.source_location
            and item.chunk.citation.page_number >= 1
            for item in evidence
        )
        if conflict_reasons:
            return EvidenceAssessment(
                level=EvidenceLevel.CONFLICTING,
                summary="Retrieved project documents contain conflicting evidence.",
                reasons=conflict_reasons,
                supporting_chunk_count=len(evidence),
                exact_identifier_match=exact_identifier,
                source_metadata_complete=metadata_complete,
            )

        top_score = evidence[0].relevance_score
        if top_score >= 0.65 and (exact_identifier or len(evidence) >= 2):
            level = EvidenceLevel.STRONG
            summary = "The retrieved evidence directly and strongly supports an answer."
        elif top_score >= 0.35:
            level = EvidenceLevel.MODERATE
            summary = "The retrieved evidence supports an answer, with some limitations."
        else:
            level = EvidenceLevel.WEAK
            summary = "Only weakly matching evidence was found; the answer may be partial."
        reasons = [f"Top retrieval relevance is {top_score:.2f}."]
        if exact_identifier:
            reasons.append("An exact construction identifier was matched.")
        if len(evidence) > 1:
            reasons.append(f"{len(evidence)} supporting chunks were retrieved.")
        return EvidenceAssessment(
            level=level,
            summary=summary,
            reasons=tuple(reasons),
            supporting_chunk_count=len(evidence),
            exact_identifier_match=exact_identifier,
            source_metadata_complete=metadata_complete,
        )

    @staticmethod
    def _conflicts(retrieval: RetrievalResult) -> tuple[str, ...]:
        measurements: dict[str, set[str]] = defaultdict(set)
        approval_states: set[str] = set()
        top_relevance = retrieval.evidence[0].relevance_score if retrieval.evidence else 0.0
        conflict_cutoff = max(0.25, top_relevance * 0.6)
        for item in retrieval.evidence:
            if item.relevance_score < conflict_cutoff:
                continue
            for value, unit in MEASUREMENT_PATTERN.findall(item.chunk.content):
                normalized_unit = unit.lower().rstrip("s")
                measurements[normalized_unit].add(value.replace(",", ""))
            approval_states.update(
                state.lower() for state in APPROVAL_PATTERN.findall(item.chunk.content)
            )
        reasons = [
            f"Conflicting {unit} values were retrieved: {', '.join(sorted(values))}."
            for unit, values in measurements.items()
            if len(values) > 1
        ]
        positive = "approved" in approval_states
        negative = bool(approval_states & {"not approved", "rejected", "revise and resubmit"})
        if positive and negative:
            reasons.append("Conflicting approval states were retrieved.")
        return tuple(reasons)
