"""Staleness assessment and history-preserving deterministic regeneration orchestration."""

from enum import StrEnum
from pydantic import BaseModel, ConfigDict

from revision_intelligence.models import ComparisonRequest, DocumentComparison
from revision_intelligence.service import RevisionComparisonService

from .models import ActorReference, RegisterGenerationResult
from .service import ProjectChangeService


class StalenessStatus(StrEnum):
    CURRENT = "current"
    STALE = "stale"
    REGENERATION_REQUIRED = "regeneration_required"
    REGENERATION_FAILED = "regeneration_failed"


class StalenessAssessment(BaseModel):
    model_config = ConfigDict(frozen=True)
    comparison_id: str
    status: StalenessStatus
    reasons: tuple[str, ...] = ()


class ChangeRegenerationService:
    def __init__(
        self, comparisons: RevisionComparisonService, changes: ProjectChangeService
    ) -> None:
        self.comparisons = comparisons
        self.changes = changes

    def assess(self, comparison: DocumentComparison) -> StalenessAssessment:
        stale = self.comparisons.is_stale(comparison)
        return StalenessAssessment(
            comparison_id=comparison.id,
            status=StalenessStatus.STALE if stale else StalenessStatus.CURRENT,
            reasons=("source_hash_changed",) if stale else (),
        )

    def regenerate(
        self, comparison: DocumentComparison, request: ComparisonRequest, actor: ActorReference
    ) -> tuple[DocumentComparison, RegisterGenerationResult]:
        self.changes.mark_stale(comparison.project_id, comparison.id, actor)
        regenerated = self.comparisons.compare(request)
        return regenerated, self.changes.generate_register(regenerated, actor)
