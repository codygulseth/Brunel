"""Deterministic cited operational answers for meetings, actions, and decisions."""

from pydantic import BaseModel, ConfigDict

from .models import ActionStatus, MeetingEvidenceReference, ProjectAction, ProjectDecision
from .repository import JsonMeetingRepository


class MeetingAnswer(BaseModel):
    model_config = ConfigDict(frozen=True)
    answer: str
    sufficient: bool
    evidence_type: str
    citations: tuple[MeetingEvidenceReference, ...] = ()
    record_ids: tuple[str, ...] = ()


class MeetingQuestionService:
    def __init__(self, repository: JsonMeetingRepository) -> None:
        self.repository = repository

    def answer(self, project_id: str, question: str) -> MeetingAnswer:
        lowered = question.casefold()
        actions = tuple(
            item
            for item in self.repository.list("actions", project_id)
            if isinstance(item, ProjectAction)
        )
        decisions = tuple(
            item
            for item in self.repository.list("decisions", project_id)
            if isinstance(item, ProjectDecision)
        )
        if "schedule" in lowered and ("confirmed" in lowered or "delay" in lowered):
            candidates = [
                item
                for item in self.repository.list("candidates", project_id)
                if "schedule impact" in item.description.casefold()
            ]
            if candidates:
                return MeetingAnswer(
                    answer="The raw meeting record described a potential schedule impact; Brunel does not treat it as confirmed.",
                    sufficient=True,
                    evidence_type="system_extracted_proposal_unconfirmed",
                    citations=tuple(c for item in candidates for c in item.citations),
                    record_ids=tuple(item.id for item in candidates),
                )
        if "action" in lowered:
            selected = actions
            if "overdue" in lowered:
                selected = tuple(item for item in actions if item.status == ActionStatus.OVERDUE)
            if "open" in lowered:
                selected = tuple(
                    item
                    for item in actions
                    if item.status
                    not in {ActionStatus.COMPLETED, ActionStatus.CANCELLED, ActionStatus.SUPERSEDED}
                )
            if "switchgear" in lowered:
                selected = tuple(
                    item for item in actions if "switchgear" in item.description.casefold()
                )
            if selected:
                return MeetingAnswer(
                    answer="; ".join(
                        f"{item.id}: {item.description} (owner: {item.owner_name or 'unassigned'}, status: {item.status})"
                        for item in selected
                    ),
                    sufficient=True,
                    evidence_type="human_confirmed_project_action",
                    citations=tuple(c for item in selected for c in item.citations),
                    record_ids=tuple(item.id for item in selected),
                )
        if "decision" in lowered and decisions:
            selected = (
                tuple(
                    item
                    for item in decisions
                    if "owner" not in lowered or "owner" in item.decision_text.casefold()
                )
                or decisions
            )
            return MeetingAnswer(
                answer="; ".join(
                    f"{item.id}: {item.decision_text} ({item.status})" for item in selected
                ),
                sufficient=True,
                evidence_type="project_decision_register",
                citations=tuple(c for item in selected for c in item.citations),
                record_ids=tuple(item.id for item in selected),
            )
        results = []
        for category in ("candidates", "actions", "decisions"):
            results.extend(
                item
                for item in self.repository.list(category, project_id)
                if any(
                    term in item.model_dump_json().casefold()
                    for term in lowered.split()
                    if len(term) > 4
                )
            )
        if results:
            citations = tuple(c for item in results for c in getattr(item, "citations", ()))
            return MeetingAnswer(
                answer="The meeting records contain relevant proposed or confirmed items; review the cited records for authority status.",
                sufficient=True,
                evidence_type="mixed_meeting_evidence",
                citations=citations,
                record_ids=tuple(item.id for item in results),
            )
        return MeetingAnswer(
            answer="The project meeting evidence does not support an answer.",
            sufficient=False,
            evidence_type="insufficient_evidence",
        )
