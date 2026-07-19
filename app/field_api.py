from datetime import date
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict
from config import get_settings
from field_intelligence.models import ReportStatus
from field_intelligence.qa import FieldQuestionService
from field_intelligence.repository import JsonFieldRepository
from field_intelligence.service import FieldIntelligenceService

router = APIRouter(prefix="/projects/{project_id}", tags=["daily-reports-field-intelligence"])


def _service():
    return FieldIntelligenceService(
        JsonFieldRepository(get_settings().data_directory / "field-intelligence")
    )


def _call(fn):
    try:
        v = fn()
        return (
            v.model_dump(mode="json")
            if hasattr(v, "model_dump")
            else [x.model_dump(mode="json") for x in v]
            if isinstance(v, tuple)
            else v
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


class DayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    day: date
    shift: str = "day"
    timezone: str = "UTC"
    planned_schedule_revision_id: str | None = None


class ReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    day: date
    shift: str = "day"
    prepared_by: str | None = None
    text: str = ""
    file_path: Path | None = None
    predecessor_revision_id: str | None = None


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: str
    reviewer: str
    description: str | None = None


class TransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor: str


class QuestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str


@router.post("/project-days", status_code=201)
def day(project_id: str, body: DayRequest):
    return _call(
        lambda: _service().create_day(
            project_id, body.day, body.shift, body.timezone, body.planned_schedule_revision_id
        )
    )


@router.get("/project-days")
def days(project_id: str):
    return _call(lambda: _service().repository.list("days", project_id))


@router.post("/daily-reports", status_code=201)
def create(project_id: str, body: ReportRequest):
    return _call(
        lambda: _service().ingest(
            project_id,
            body.day,
            body.file_path,
            shift=body.shift,
            prepared_by=body.prepared_by,
            predecessor_revision_id=body.predecessor_revision_id,
        )
        if body.file_path
        else _service().create_report(
            project_id,
            body.day,
            shift=body.shift,
            prepared_by=body.prepared_by,
            text=body.text,
            predecessor_revision_id=body.predecessor_revision_id,
        )
    )


@router.get("/daily-reports")
def reports(project_id: str):
    return _call(lambda: _service().repository.list("reports", project_id))


@router.get("/daily-reports/{report_id}")
def report(project_id: str, report_id: str):
    return _call(lambda: _service()._report(project_id, report_id))


@router.get("/daily-report-revisions/{revision_id}")
def revision(project_id: str, revision_id: str):
    return _call(lambda: _service()._revision(project_id, revision_id))


@router.post("/daily-report-revisions/{revision_id}/analyze")
def analyze(project_id: str, revision_id: str):
    return _call(lambda: _service().analyze(project_id, revision_id))


@router.get("/daily-reports/{report_id}/observations")
def observations(project_id: str, report_id: str):
    return _call(
        lambda: tuple(
            x
            for x in _service().repository.list("observations", project_id)
            if x.report_id == report_id
        )
    )


@router.post("/daily-observations/{observation_id}/review")
def review_observation(project_id: str, observation_id: str, body: ReviewRequest):
    return _call(
        lambda: _service().review_observation(
            project_id, observation_id, body.decision, body.reviewer, description=body.description
        )
    )


@router.post("/daily-reports/{report_id}/submit-review")
def submit(project_id: str, report_id: str, body: TransitionRequest):
    return _call(
        lambda: _service().transition(project_id, report_id, ReportStatus.UNDER_REVIEW, body.actor)
    )


@router.post("/daily-reports/{report_id}/review")
def approve(project_id: str, report_id: str, body: TransitionRequest):
    return _call(
        lambda: _service().transition(project_id, report_id, ReportStatus.APPROVED, body.actor)
    )


@router.post("/daily-reports/{report_id}/issue")
def issue(project_id: str, report_id: str, body: TransitionRequest):
    return _call(
        lambda: _service().transition(
            project_id, report_id, ReportStatus.ISSUED_INTERNAL, body.actor
        )
    )


@router.post("/daily-reports/{report_id}/draft")
def draft(project_id: str, report_id: str):
    return {"markdown": _service().draft(project_id, report_id)}


@router.get("/field-dashboard")
def dashboard(project_id: str):
    return _call(lambda: _service().dashboard(project_id))


@router.get("/field-search")
def search(project_id: str, query: str):
    return _call(lambda: _service().search(project_id, query))


@router.post("/field-questions")
def question(project_id: str, body: QuestionRequest):
    return _call(lambda: FieldQuestionService(_service()).answer(project_id, body.question))
