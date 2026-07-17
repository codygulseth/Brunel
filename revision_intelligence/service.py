"""Revision-comparison orchestration with deterministic evidence as authority."""

import logging
from hashlib import sha256

from document_processing.interfaces import DocumentRepository

from .alignment import BlockAlignmentService
from .classification import ConstructionChangeClassifier
from .differ import TokenDiffer
from .errors import DocumentNotFoundError, DocumentsNotComparableError, InsufficientContentError
from .interfaces import ComparisonRepository, RevisionAnalysisProvider
from .lineage import RevisionLineageService
from .models import (
    ChangeEvidence,
    ChangeImplication,
    ChangeSeverity,
    ChangeType,
    ComparisonRequest,
    ComparisonStatus,
    ComparisonUnit,
    ComparisonSummary,
    DocumentChange,
    DocumentComparison,
    MatchMethod,
    TokenDiff,
)
from .normalization import ContentNormalizer
from .significance import ChangeSignificanceAssessor

logger = logging.getLogger(__name__)


class RevisionComparisonService:
    def __init__(
        self,
        documents: DocumentRepository,
        comparisons: ComparisonRepository,
        *,
        lineage: RevisionLineageService | None = None,
        normalizer: ContentNormalizer | None = None,
        aligner: BlockAlignmentService | None = None,
        differ: TokenDiffer | None = None,
        classifier: ConstructionChangeClassifier | None = None,
        significance: ChangeSignificanceAssessor | None = None,
        analysis_provider: RevisionAnalysisProvider | None = None,
    ) -> None:
        self.documents = documents
        self.comparisons = comparisons
        self.lineage = lineage or RevisionLineageService()
        self.normalizer = normalizer or ContentNormalizer()
        self.aligner = aligner or BlockAlignmentService()
        self.differ = differ or TokenDiffer()
        self.classifier = classifier or ConstructionChangeClassifier()
        self.significance = significance or ChangeSignificanceAssessor()
        self.analysis_provider = analysis_provider

    def compare(self, request: ComparisonRequest) -> DocumentComparison:
        logger.info("revision_comparison_started", extra={"project_id": request.project_id})
        old = self.documents.get(request.old_document_id)
        new = self.documents.get(request.new_document_id)
        if old is None or new is None:
            raise DocumentNotFoundError("One or both document IDs were not found")
        if (
            old.document.project_id != request.project_id
            or new.document.project_id != request.project_id
        ):
            raise DocumentNotFoundError("Document not found in requested project")
        assessment = self.lineage.assess(old, new, force=request.force)
        if not old.chunks or not new.chunks:
            raise InsufficientContentError("Both revisions require extractable text")
        if not assessment.comparable:
            raise DocumentsNotComparableError(
                "Documents appear unrelated; use --force to compare with warnings"
            )
        old_units, new_units = self.normalizer.normalize(old), self.normalizer.normalize(new)
        alignment = self.aligner.align(old_units, new_units)
        changes: list[DocumentChange] = []
        unchanged = 0
        for match in alignment.matches:
            change_type, diff = self.differ.diff(
                match.old_unit.span.source_text, match.new_unit.span.source_text
            )
            if change_type == ChangeType.UNCHANGED:
                unchanged += 1
                if match.old_unit.order != match.new_unit.order:
                    change_type = ChangeType.MOVED
                else:
                    continue
            if change_type == ChangeType.FORMATTING_ONLY and not request.include_formatting:
                unchanged += 1
                continue
            changes.append(
                self._change(
                    change_type, match.method, match.old_unit, match.new_unit, diff, match.ambiguous
                )
            )
        for match in alignment.ambiguous:
            changes.append(
                self._change(
                    ChangeType.AMBIGUOUS,
                    match.method,
                    match.old_unit,
                    match.new_unit,
                    TokenDiff(),
                    True,
                )
            )
        for unit in alignment.added:
            changes.append(
                self._change(
                    ChangeType.ADDED,
                    MatchMethod.UNMATCHED,
                    None,
                    unit,
                    TokenDiff(added=(unit.span.source_text,)),
                    False,
                )
            )
        for unit in alignment.removed:
            changes.append(
                self._change(
                    ChangeType.REMOVED,
                    MatchMethod.UNMATCHED,
                    unit,
                    None,
                    TokenDiff(removed=(unit.span.source_text,)),
                    False,
                )
            )
        changes.sort(key=lambda item: (self._severity_rank(item.severity), item.id))
        aligned = len(alignment.matches) + len(alignment.ambiguous)
        counts = {kind: sum(item.change_type == kind for item in changes) for kind in ChangeType}
        total = len(changes)
        summary = ComparisonSummary(
            total_changes=total,
            added=counts[ChangeType.ADDED],
            removed=counts[ChangeType.REMOVED],
            modified=counts[ChangeType.MODIFIED],
            moved=counts[ChangeType.MOVED],
            ambiguous=counts[ChangeType.AMBIGUOUS],
            unchanged_blocks=unchanged,
            aligned_blocks=aligned,
            unchanged_percentage=round(
                100 * unchanged / max(aligned + len(alignment.added) + len(alignment.removed), 1), 2
            ),
            executive_summary=f"Brunel detected {total} reviewable change(s): {counts[ChangeType.ADDED]} added, {counts[ChangeType.REMOVED]} removed, and {counts[ChangeType.MODIFIED]} modified. Potential implications require human review.",
        )
        identity = f"{request.project_id}\0{old.document.content_hash}\0{new.document.content_hash}\0revision-comparison-v1"
        comparison_id = f"cmp_{sha256(identity.encode()).hexdigest()[:24]}"
        warnings = assessment.warnings + (
            ("Ambiguous block matches require review.",) if alignment.ambiguous else ()
        )
        provider_metadata: dict[str, object] = {
            "provider": "disabled",
            "deterministic": True,
        }
        if request.use_model:
            if self.analysis_provider is None:
                warnings += (
                    "Optional model analysis was requested but no provider is configured; "
                    "deterministic summary retained.",
                )
            else:
                try:
                    generated_summary = self.analysis_provider.summarize(tuple(changes)).strip()
                    if not generated_summary:
                        raise ValueError("Provider returned an empty summary")
                    summary = summary.model_copy(update={"executive_summary": generated_summary})
                    provider_metadata = {
                        "provider": self.analysis_provider.name,
                        "deterministic": False,
                    }
                except Exception as exc:
                    logger.warning(
                        "revision_analysis_provider_failed",
                        extra={
                            "project_id": request.project_id,
                            "error_type": type(exc).__name__,
                        },
                    )
                    warnings += (
                        f"Optional model analysis failed safely ({type(exc).__name__}); "
                        "deterministic summary retained.",
                    )
                    provider_metadata = {
                        "provider": self.analysis_provider.name,
                        "failed": True,
                        "deterministic": True,
                    }
        comparison = DocumentComparison(
            id=comparison_id,
            project_id=request.project_id,
            old_document=old.document,
            new_document=new.document,
            status=ComparisonStatus.COMPLETED_WITH_WARNINGS
            if warnings
            else ComparisonStatus.COMPLETED,
            comparability=assessment,
            changes=tuple(changes),
            summary=summary,
            warnings=warnings,
            old_content_hash=old.document.content_hash,
            new_content_hash=new.document.content_hash,
            provider_metadata=provider_metadata,
        )
        self.comparisons.save(comparison)
        logger.info(
            "revision_comparison_completed",
            extra={
                "project_id": request.project_id,
                "comparison_id": comparison_id,
                "change_count": total,
            },
        )
        return comparison

    def is_stale(self, comparison: DocumentComparison) -> bool:
        """Return true when either persisted source aggregate has changed or disappeared."""
        old = self.documents.get(comparison.old_document.document_id)
        new = self.documents.get(comparison.new_document.document_id)
        return (
            old is None
            or new is None
            or old.document.content_hash != comparison.old_content_hash
            or new.document.content_hash != comparison.new_content_hash
        )

    def _change(
        self,
        kind: ChangeType,
        method: MatchMethod,
        old: ComparisonUnit | None,
        new: ComparisonUnit | None,
        diff: TokenDiff,
        ambiguous: bool,
    ) -> DocumentChange:
        old_text = old.span.source_text if old else ""
        new_text = new.span.source_text if new else ""
        categories, signals, explanation = self.classifier.classify(old_text, new_text, diff)
        significance = self.significance.assess(
            change_type=kind,
            categories=categories,
            diff=diff,
            ambiguous=ambiguous,
        )
        digest = sha256(f"{kind}\0{old_text}\0{new_text}".encode()).hexdigest()[:16]
        evidence = ChangeEvidence(
            old_citation=old.span.citation if old else None,
            new_citation=new.span.citation if new else None,
            old_excerpt=old_text or None,
            new_excerpt=new_text or None,
            alignment_method=method,
            diff=diff,
        )
        return DocumentChange(
            id=f"chg_{digest}",
            change_type=ChangeType.AMBIGUOUS if ambiguous else kind,
            title=f"{kind.value.replace('_', ' ').title()} content",
            categories=categories,
            severity=significance.severity,
            evidence_strength=significance.evidence_strength,
            evidence=evidence,
            signals=signals,
            explanation=f"{explanation} {significance.explanation}",
            potentially_affected_workflows=tuple(
                sorted(
                    {
                        c.value
                        for c in categories
                        if c.value in {"schedule", "procurement", "testing", "commissioning"}
                    }
                )
            ),
            implications=(
                ChangeImplication(
                    statement=f"This change may affect {categories[0].value}; confirm with the responsible project professional."
                ),
            ),
            review_required=True,
        )

    @staticmethod
    def _severity_rank(value: ChangeSeverity) -> int:
        return {
            ChangeSeverity.CRITICAL: 0,
            ChangeSeverity.HIGH: 1,
            ChangeSeverity.MEDIUM: 2,
            ChangeSeverity.LOW: 3,
            ChangeSeverity.INFORMATIONAL: 4,
            ChangeSeverity.UNKNOWN: 5,
        }[value]
