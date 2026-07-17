"""Unauthenticated development API for Schedule Intelligence."""

from datetime import date
from pathlib import Path
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from config import get_settings
from schedule_intelligence.models import ScheduleType
from schedule_intelligence.repository import JsonScheduleRepository
from schedule_intelligence.service import ScheduleIntelligenceService
from schedule_intelligence.qa import ScheduleQuestionService

router = APIRouter(prefix="/projects/{project_id}", tags=["schedule-intelligence"])


def _service():
    return ScheduleIntelligenceService(
        JsonScheduleRepository(get_settings().data_directory / "schedule-intelligence")
    )


def _call(fn):
    try:
        value = fn()
        return (
            value.model_dump(mode="json")
            if hasattr(value, "model_dump")
            else [x.model_dump(mode="json") for x in value]
            if isinstance(value, tuple)
            else value
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


class ImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file_path: Path
    name: str
    schedule_type: ScheduleType = ScheduleType.UPDATE
    revision_label: str | None = None
    revision_number: int | None = None
    predecessor_revision_id: str | None = None
    baseline_revision_id: str | None = None
    calendar_fallback: bool = False


class CompareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    old_revision_id: str
    new_revision_id: str


class LinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workflow_type: str
    reference: str
    relationship: str = "related_to"


class LineageReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: str
    reviewer: str


class ProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    activity_revision_id: str
    workflow_type: str
    workflow_reference: str
    existing_date: date | None = None
    relationship: str


class ProposalReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: str
    reviewer: str


class QuestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str


@router.post("/schedules", status_code=201)
def import_schedule(project_id: str, body: ImportRequest, x_actor_id: str | None = Header(None)):
    return _call(
        lambda: _service().import_schedule(
            project_id,
            body.file_path,
            body.name,
            body.schedule_type,
            revision_label=body.revision_label,
            revision_number=body.revision_number,
            predecessor_revision_id=body.predecessor_revision_id,
            baseline_revision_id=body.baseline_revision_id,
            calendar_fallback=body.calendar_fallback,
            imported_by=x_actor_id or "local-user",
        )
    )


@router.get("/schedules")
def schedules(project_id: str):
    return _call(lambda: _service().repository.list("schedules", project_id))


@router.get("/schedules/{schedule_id}")
def schedule(project_id: str, schedule_id: str):
    return _call(
        lambda: _service().repository.get("schedules", schedule_id, project_id)
        or (_ for _ in ()).throw(ValueError("Schedule not found"))
    )


@router.get("/schedule-revisions/{revision_id}")
def revision(project_id: str, revision_id: str):
    return _call(
        lambda: _service().repository.get("revisions", revision_id, project_id)
        or (_ for _ in ()).throw(ValueError("Revision not found"))
    )


@router.post("/schedule-revisions/{revision_id}/analyze")
def analyze(project_id: str, revision_id: str):
    return _call(lambda: _service().assess_quality(project_id, revision_id))


@router.get("/schedule-revisions/{revision_id}/activities")
def activities(
    project_id: str,
    revision_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    return _call(lambda: _service().activities(project_id, revision_id)[offset : offset + limit])


@router.get("/schedule-activities/{activity_id}")
def activity(project_id: str, activity_id: str):
    return _call(
        lambda: _service().repository.get("activities", activity_id, project_id)
        or (_ for _ in ()).throw(ValueError("Activity not found"))
    )


@router.get("/schedule-activities/{activity_id}/relationships")
def relationships(project_id: str, activity_id: str):
    s = _service()
    a = s.repository.get("activities", activity_id, project_id)
    return _call(
        lambda: tuple(
            x
            for x in s.relationships(project_id, a.schedule_revision_id)
            if a and a.source_activity_id in {x.predecessor_id, x.successor_id}
        )
    )


@router.get("/schedule-activities/{activity_id}/float-history")
def float_history(project_id: str, activity_id: str):
    activity = _service().repository.get("activities", activity_id, project_id)
    return _call(
        lambda: tuple(
            x
            for x in _service().repository.list("floats", project_id)
            if activity and x.activity_identity_id == activity.activity_identity_id
        )
    )


@router.get("/schedule-activities/{activity_id}/workflow-links")
def workflow_links(project_id: str, activity_id: str):
    activity = _service().repository.get("activities", activity_id, project_id)
    return _call(lambda: activity.workflow_links if activity else ())


@router.post("/schedule-activities/{activity_id}/links")
def link(
    project_id: str, activity_id: str, body: LinkRequest, x_actor_id: str | None = Header(None)
):
    return _call(
        lambda: _service().link_activity(
            project_id,
            activity_id,
            body.workflow_type,
            body.reference,
            body.relationship,
            x_actor_id or "local-user",
        )
    )


@router.get("/schedule-revisions/{revision_id}/quality")
def quality(project_id: str, revision_id: str):
    return _call(lambda: _service().assess_quality(project_id, revision_id))


@router.get("/schedule-revisions/{revision_id}/critical-activities")
def critical(project_id: str, revision_id: str):
    return _call(
        lambda: tuple(
            a
            for a in _service().activities(project_id, revision_id)
            if _service().criticality(a).classification.value == "critical"
        )
    )


@router.get("/schedule-revisions/{revision_id}/near-critical-activities")
def near(project_id: str, revision_id: str):
    return _call(
        lambda: tuple(
            a
            for a in _service().activities(project_id, revision_id)
            if _service().criticality(a).classification.value == "near_critical"
        )
    )


@router.get("/schedule-revisions/{revision_id}/milestones")
def milestones(project_id: str, revision_id: str):
    return _call(
        lambda: tuple(
            a
            for a in _service().activities(project_id, revision_id)
            if "milestone" in a.activity_type.value
        )
    )


@router.get("/schedule-revisions/{revision_id}/lookahead")
def lookahead(project_id: str, revision_id: str, start: date, end: date, date_field: str):
    return _call(lambda: _service().lookahead(project_id, revision_id, start, end, date_field))


@router.get("/schedule-revisions/{revision_id}/lineage-candidates")
def lineage(project_id: str, revision_id: str):
    return _call(
        lambda: tuple(
            x
            for x in _service().repository.list("lineage", project_id)
            if x.new_activity_revision_id
            in {a.id for a in _service().activities(project_id, revision_id)}
        )
    )


@router.post("/schedule-lineage/{lineage_id}/review")
def review_lineage(project_id: str, lineage_id: str, body: LineageReviewRequest):
    return _call(
        lambda: _service().review_lineage(project_id, lineage_id, body.decision, body.reviewer)
    )


@router.post("/schedule-comparisons")
def compare(project_id: str, body: CompareRequest):
    return _call(lambda: _service().compare(project_id, body.old_revision_id, body.new_revision_id))


@router.get("/schedule-comparisons/{comparison_id}")
def comparison(project_id: str, comparison_id: str):
    return _call(
        lambda: _service().repository.get("comparisons", comparison_id, project_id)
        or (_ for _ in ()).throw(ValueError("Comparison not found"))
    )


@router.get("/schedule-synchronization-proposals")
def proposals(project_id: str):
    return _call(lambda: _service().repository.list("proposals", project_id))


@router.post("/schedule-synchronization-proposals")
def propose(project_id: str, body: ProposalRequest):
    return _call(
        lambda: _service().propose_sync(
            project_id,
            body.activity_revision_id,
            body.workflow_type,
            body.workflow_reference,
            body.existing_date,
            body.relationship,
        )
    )


@router.post("/schedule-synchronization-proposals/{proposal_id}/review")
def review_proposal(project_id: str, proposal_id: str, body: ProposalReviewRequest):
    return _call(
        lambda: _service().review_proposal(project_id, proposal_id, body.decision, body.reviewer)
    )


@router.get("/schedule-dashboard")
def dashboard(project_id: str, revision_id: str | None = None):
    return _call(lambda: _service().dashboard(project_id, revision_id))


@router.get("/schedule-exposures")
def exposures(project_id: str, revision_id: str):
    return _call(lambda: _service().assess_exposures(project_id, revision_id))


@router.get("/schedule-register")
def register(project_id: str, revision_id: str):
    return _call(lambda: _service().activities(project_id, revision_id))


@router.get("/schedule-search")
def search(project_id: str, query: str, revision_id: str | None = None):
    return _call(lambda: _service().search(project_id, query, revision_id))


@router.post("/schedule-questions")
def question(project_id: str, body: QuestionRequest):
    return _call(lambda: ScheduleQuestionService(_service()).answer(project_id, body.question))
