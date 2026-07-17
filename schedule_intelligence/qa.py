"""Conservative cited schedule operational answers."""

from pydantic import BaseModel, ConfigDict
from .service import ScheduleIntelligenceService


class ScheduleAnswer(BaseModel):
    model_config = ConfigDict(frozen=True)
    answer: str
    citations: tuple[dict[str, object], ...] = ()
    limitations: tuple[str, ...] = ()


class ScheduleQuestionService:
    def __init__(self, service: ScheduleIntelligenceService):
        self.service = service

    def answer(self, project_id, question):
        q = question.casefold()
        if any(
            x in q
            for x in (
                "caused",
                "responsible",
                "compensable",
                "entitlement",
                "excusable",
                "concurrent",
            )
        ):
            return ScheduleAnswer(
                answer="Brunel cannot determine schedule causation, contractual responsibility, concurrency, excusability, compensability, or entitlement from this evidence."
            )
        schedules = self.service.repository.list("schedules", project_id)
        if not schedules:
            return ScheduleAnswer(answer="No project-scoped schedule evidence supports an answer.")
        revision = self.service.repository.get(
            "revisions", schedules[-1].current_revision_id, project_id
        )
        items = self.service.activities(project_id, revision.id)
        citations = tuple(
            {
                "schedule_revision_id": a.schedule_revision_id,
                "activity_id": a.source_activity_id,
                "source_filename": a.citation.source_filename,
                "source_table": a.citation.source_table,
                "source_row": a.citation.source_row,
                "evidence_type": "imported_schedule_value",
            }
            for a in items[:5]
        )
        if "data date" in q:
            return ScheduleAnswer(
                answer=f"The imported schedule data date is {revision.data_date or 'not provided'}.",
                citations=citations,
            )
        if "forecast" in q and "finish" in q:
            return ScheduleAnswer(
                answer=f"The imported forecast project finish is {revision.forecast_project_finish or 'not provided'}. This is an imported/planning value, not a contractual delay conclusion.",
                citations=citations,
            )
        if "change" in q:
            comparisons = self.service.repository.list("comparisons", project_id)
            if comparisons:
                return ScheduleAnswer(
                    answer=f"The latest deterministic comparison contains {len(comparisons[-1].changes)} activity changes and a project-finish movement of {comparisons[-1].project_finish_change_days} calendar days. Causation is not established.",
                    citations=citations,
                    limitations=comparisons[-1].limitations,
                )
        return ScheduleAnswer(
            answer=f"The current imported revision contains {len(items)} activities. Schedule exposure is decision support and is not a forensic analysis.",
            citations=citations,
        )
