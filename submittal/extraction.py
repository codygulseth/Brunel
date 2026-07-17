"""Deterministic, citation-preserving specification requirement extraction."""

import re
from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from typing import Protocol

from document_processing.models import CitationReference, DocumentType
from storage import JsonDocumentRepository

from .models import (
    RequirementCategory,
    RequirementExtractionResult,
    SubmittalEvidenceReference,
    SubmittalRequirementCandidate,
    SubmittalType,
)
from .repository import JsonSubmittalRepository


class RequirementExtractionProvider(Protocol):
    name: str

    def enhance(
        self, candidates: tuple[SubmittalRequirementCandidate, ...]
    ) -> tuple[SubmittalRequirementCandidate, ...]: ...


PATTERNS: tuple[tuple[SubmittalType, str], ...] = (
    (SubmittalType.PRODUCT_DATA, r"\bproduct data\b"),
    (SubmittalType.SHOP_DRAWING, r"\bshop drawings?\b"),
    (SubmittalType.SAMPLE, r"\bsamples?\b"),
    (SubmittalType.MOCKUP, r"\bmockups?\b"),
    (SubmittalType.CERTIFICATE, r"\bcertificates?|qualification data\b"),
    (SubmittalType.TEST_REPORT, r"\b(?:factory|field)?\s*test reports?|quality-control reports?\b"),
    (SubmittalType.CALCULATION, r"\b(?:design|short-circuit)?\s*calculations?\b"),
    (SubmittalType.COORDINATION_DRAWING, r"\bcoordination drawings?\b"),
    (SubmittalType.QUALITY_CONTROL_PLAN, r"\bquality[- ]control plans?\b"),
    (SubmittalType.INSTALLATION_INSTRUCTION, r"\bmanufacturer(?:'s)? instructions?\b"),
    (SubmittalType.WARRANTY, r"\bwarrant(?:y|ies)\b"),
    (SubmittalType.OPERATION_AND_MAINTENANCE, r"\boperation and maintenance|\bo\s*&\s*m\b"),
    (SubmittalType.CLOSEOUT, r"\bcloseout submittals?\b"),
    (SubmittalType.DELEGATED_DESIGN, r"\bdelegated design\b"),
    (SubmittalType.SUBSTITUTION_REQUEST, r"\bsubstitution requests?\b"),
)


class SubmittalRequirementExtractionService:
    def __init__(
        self,
        documents: JsonDocumentRepository,
        repository: JsonSubmittalRepository,
        *,
        provider: RequirementExtractionProvider | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.documents = documents
        self.repository = repository
        self.provider = provider
        self.clock = clock or (lambda: datetime.now(UTC))

    def extract(
        self,
        project_id: str,
        *,
        document_ids: tuple[str, ...] = (),
        specification_sections: tuple[str, ...] = (),
        use_model: bool = False,
    ) -> RequirementExtractionResult:
        candidates: list[SubmittalRequirementCandidate] = []
        warnings: list[str] = []
        for aggregate in self.documents.list_by_project(project_id):
            document = aggregate.document
            if document.document_type != DocumentType.SPECIFICATION:
                continue
            if document_ids and document.document_id not in document_ids:
                continue
            for chunk in aggregate.chunks:
                section = (
                    chunk.citation.specification_section
                    or document.specification_section
                    or self._section(chunk.content)
                    or "UNCLASSIFIED"
                )
                if specification_sections and section not in specification_sections:
                    continue
                for paragraph in self._paragraphs(chunk.content):
                    if not re.search(r"\bsubmit(?:tal|ted|s)?\b", paragraph, re.I):
                        continue
                    matched = False
                    for submittal_type, pattern in PATTERNS:
                        if not re.search(pattern, paragraph, re.I):
                            continue
                        matched = True
                        candidates.append(
                            self._candidate(
                                project_id,
                                document.document_id,
                                document.title,
                                document.discipline,
                                section,
                                paragraph,
                                submittal_type,
                                chunk.citation,
                            )
                        )
                    if not matched:
                        candidates.append(
                            self._candidate(
                                project_id,
                                document.document_id,
                                document.title,
                                document.discipline,
                                section,
                                paragraph,
                                SubmittalType.OTHER,
                                chunk.citation,
                            )
                        )
        unique = {candidate.id: candidate for candidate in candidates}
        deterministic = tuple(unique.values())
        provider_name = "deterministic"
        if use_model:
            if self.provider is None:
                warnings.append(
                    "Model extraction requested but no provider configured; deterministic candidates retained."
                )
            else:
                try:
                    enhanced = self.provider.enhance(deterministic)
                    self._validate_provider_output(deterministic, enhanced)
                    deterministic = enhanced
                    provider_name = self.provider.name
                except Exception as exc:
                    warnings.append(
                        f"Model extraction failed safely ({type(exc).__name__}); deterministic candidates retained."
                    )
        reused = 0
        ids: list[str] = []
        for candidate in deterministic:
            existing = self.repository.get_candidate(project_id, candidate.id)
            if existing:
                reused += 1
                ids.append(existing.id)
            else:
                self.repository.save_candidate(candidate)
                ids.append(candidate.id)
        return RequirementExtractionResult(
            project_id=project_id,
            candidate_ids=tuple(ids),
            extracted=len(ids) - reused,
            reused=reused,
            provider=provider_name,
            warnings=tuple(warnings),
        )

    def _candidate(
        self,
        project_id: str,
        document_id: str,
        title: str | None,
        discipline: str | None,
        section: str,
        paragraph: str,
        submittal_type: SubmittalType,
        citation: CitationReference,
    ) -> SubmittalRequirementCandidate:
        normalized = " ".join(paragraph.split())
        identity = sha256(
            f"{project_id}\0{document_id}\0{citation.chunk_id}\0{section}\0{submittal_type.value}\0{normalized}".encode()
        ).hexdigest()[:24]
        lowered = normalized.casefold()
        category = RequirementCategory.ACTION
        if any(term in lowered for term in ("for information", "for record", "informational")):
            category = RequirementCategory.INFORMATIONAL
        elif any(term in lowered for term in ("closeout", "operation and maintenance", "warranty")):
            category = RequirementCategory.CLOSEOUT
        elif "deferred" in lowered:
            category = RequirementCategory.DEFERRED
        elif submittal_type == SubmittalType.DELEGATED_DESIGN:
            category = RequirementCategory.DELEGATED_DESIGN
        paragraph_reference = self._paragraph_reference(normalized)
        timing = next(
            (
                term
                for term in ("before fabrication", "before installation", "at closeout")
                if term in lowered
            ),
            None,
        )
        now = self.clock()
        evidence = SubmittalEvidenceReference(citation=citation, excerpt=normalized)
        return SubmittalRequirementCandidate(
            id=f"subreq_{identity}",
            project_id=project_id,
            document_id=document_id,
            specification_section=section,
            specification_title=title,
            paragraph_reference=paragraph_reference,
            submittal_type=submittal_type,
            category=category,
            description=normalized,
            required_documentation=(submittal_type.value,),
            discipline=discipline,
            frequency_or_timing=timing,
            evidence=evidence,
            created_at=now,
            updated_at=now,
        )

    @staticmethod
    def _paragraphs(content: str) -> tuple[str, ...]:
        lines = tuple(line.strip(" -\t") for line in content.splitlines() if line.strip())
        if len(lines) > 1:
            return lines
        return tuple(
            part.strip() for part in re.split(r"(?<=[.;])\s+(?=[A-Z0-9])", content) if part.strip()
        )

    @staticmethod
    def _section(content: str) -> str | None:
        match = re.search(r"\b(?:SECTION\s+)?(\d{2}\s\d{2}\s\d{2})\b", content, re.I)
        return match.group(1) if match else None

    @staticmethod
    def _paragraph_reference(content: str) -> str | None:
        match = re.match(r"\s*([A-Z]?\d+(?:\.\d+)+[A-Z]?)\b", content)
        return match.group(1) if match else None

    @staticmethod
    def _validate_provider_output(
        source: tuple[SubmittalRequirementCandidate, ...],
        enhanced: tuple[SubmittalRequirementCandidate, ...],
    ) -> None:
        source_citations = {item.evidence.citation.chunk_id for item in source}
        if not enhanced or any(
            item.evidence.citation.chunk_id not in source_citations for item in enhanced
        ):
            raise ValueError("Model extraction introduced unsupported evidence")
