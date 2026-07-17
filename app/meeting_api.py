"""Development FastAPI adapter for meeting operations."""

from datetime import date
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, ConfigDict

from config import get_settings
from meeting_tracking.models import (
    ActionStatus,
    MeetingType,
    MinutesStatus,
    RecordType,
    ReviewStatus,
)
from meeting_tracking.repository import JsonMeetingRepository
from meeting_tracking.service import MeetingTrackingService
from meeting_tracking.qa import MeetingQuestionService
from storage import JsonDocumentRepository

router = APIRouter(tags=["meeting-minutes-action-tracking"])


def _service() -> MeetingTrackingService:
    root = get_settings().data_directory
    return MeetingTrackingService(
        JsonDocumentRepository(root / "ingested"), JsonMeetingRepository(root / "meeting-tracking")
    )


class MeetingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    meeting_date: date
    meeting_type: MeetingType = MeetingType.OTHER
    meeting_number: str | None = None
    series_id: str | None = None
    previous_meeting_id: str | None = None


class SeriesCreate(BaseModel):
    name: str
    meeting_type: MeetingType
    recurrence: str | None = None


class ReviewRequest(BaseModel):
    status: ReviewStatus
    reviewer_id: str = "local-user"
    title: str | None = None
    description: str | None = None
    owner_name: str | None = None
    due_date: date | None = None


class AssignmentRequest(BaseModel):
    owner_id: str
    owner_name: str
    actor_id: str = "local-user"


class TransitionRequest(BaseModel):
    status: ActionStatus
    actor_id: str = "local-user"
    reason: str | None = None
    resolution: str | None = None
    completion_evidence: str | None = None


class DecisionCreate(BaseModel):
    decision_text: str
    meeting_id: str | None = None


class ActorRequest(BaseModel):
    actor_id: str = "local-user"


class SupersedeRequest(BaseModel):
    new_decision_id: str
    actor_id: str = "local-user"


class LinkRequest(BaseModel):
    workflow_type: str
    reference: str
    relationship: str = "related_to"
    actor_id: str = "local-user"


class CompareRequest(BaseModel):
    old_record_revision_id: str
    new_record_revision_id: str


class SplitRequest(BaseModel):
    descriptions: tuple[str, ...]
    reviewer_id: str = "local-user"


class MergeRequest(BaseModel):
    candidate_ids: tuple[str, ...]
    description: str
    reviewer_id: str = "local-user"


@router.post("/projects/{project_id}/meetings", status_code=201)
def create_meeting(project_id: str, body: MeetingCreate):
    return _service().create_meeting(
        project_id,
        body.title,
        body.meeting_date,
        meeting_type=body.meeting_type,
        meeting_number=body.meeting_number,
        series_id=body.series_id,
        previous_meeting_id=body.previous_meeting_id,
    )


@router.get("/projects/{project_id}/meetings")
def list_meetings(
    project_id: str, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)
):
    items = _service().repository.list("meetings", project_id)
    return {
        "items": items[offset : offset + limit],
        "total": len(items),
        "limit": limit,
        "offset": offset,
    }


@router.get("/projects/{project_id}/meetings/{meeting_id}")
def get_meeting(project_id: str, meeting_id: str):
    return _service()._meeting(project_id, meeting_id)


@router.patch("/projects/{project_id}/meetings/{meeting_id}")
def patch_meeting(project_id: str, meeting_id: str, body: dict):
    service = _service()
    item = service._meeting(project_id, meeting_id)
    allowed = {
        key: value
        for key, value in body.items()
        if key in {"title", "location", "chair", "recorder", "meeting_owner"}
    }
    updated = item.model_copy(update=allowed)
    service.repository.save("meetings", item.id, updated)
    return updated


@router.post("/projects/{project_id}/meeting-series", status_code=201)
def create_series(project_id: str, body: SeriesCreate):
    return _service().create_series(
        project_id, body.name, body.meeting_type, recurrence=body.recurrence
    )


@router.get("/projects/{project_id}/meeting-series")
def list_series(project_id: str):
    return _service().repository.list("series", project_id)


@router.post("/projects/{project_id}/meetings/{meeting_id}/records", status_code=201)
async def ingest_record(
    project_id: str,
    meeting_id: str,
    file: Annotated[UploadFile, File()],
    record_type: Annotated[RecordType, Form()],
    predecessor_revision_id: Annotated[str | None, Form()] = None,
):
    suffix = Path(file.filename or "").suffix.casefold()
    allowed = {".pdf": "application/pdf", ".txt": "text/plain", ".md": "text/markdown"}
    if suffix not in allowed:
        raise HTTPException(415, "Only PDF, TXT, and Markdown meeting records are accepted")
    payload = await file.read(25 * 1024 * 1024 + 1)
    if len(payload) > 25 * 1024 * 1024:
        raise HTTPException(413, "Meeting record exceeds 25 MiB")
    with NamedTemporaryFile(suffix=suffix, delete=False) as temporary:
        temporary.write(payload)
        path = Path(temporary.name)
    try:
        return _service().ingest_record(
            project_id,
            meeting_id,
            path,
            record_type,
            predecessor_revision_id=predecessor_revision_id,
        )
    finally:
        path.unlink(missing_ok=True)


@router.get("/projects/{project_id}/meetings/{meeting_id}/records")
def list_records(project_id: str, meeting_id: str):
    return [
        item
        for item in _service().repository.list("records", project_id)
        if item.meeting_id == meeting_id
    ]


@router.get("/projects/{project_id}/meeting-records/{record_revision_id}")
def get_record(project_id: str, record_revision_id: str):
    return _service()._record(project_id, record_revision_id)


@router.post("/projects/{project_id}/meeting-records/{record_revision_id}/analyze")
def analyze(project_id: str, record_revision_id: str):
    return _service().analyze(project_id, record_revision_id)


@router.post("/projects/{project_id}/meeting-records/compare")
def compare(project_id: str, body: CompareRequest):
    return _service().compare_records(
        project_id, body.old_record_revision_id, body.new_record_revision_id
    )


@router.get("/projects/{project_id}/meetings/{meeting_id}/candidates")
def candidates(project_id: str, meeting_id: str):
    return [
        item
        for item in _service().repository.list("candidates", project_id)
        if item.meeting_id == meeting_id
    ]


@router.post("/projects/{project_id}/meeting-candidates/{candidate_id}/review")
def review(project_id: str, candidate_id: str, body: ReviewRequest):
    return _service().review_candidate(
        project_id,
        candidate_id,
        body.status,
        body.reviewer_id,
        title=body.title,
        description=body.description,
        owner_name=body.owner_name,
        due_date=body.due_date,
    )


@router.post("/projects/{project_id}/meeting-candidates/{candidate_id}/split")
def split(project_id: str, candidate_id: str, body: SplitRequest):
    return _service().split_candidate(project_id, candidate_id, body.descriptions, body.reviewer_id)


@router.post("/projects/{project_id}/meeting-candidates/merge")
def merge(project_id: str, body: MergeRequest):
    return _service().merge_candidates(
        project_id, body.candidate_ids, body.description, body.reviewer_id
    )


@router.get("/projects/{project_id}/actions")
def actions(project_id: str, status: ActionStatus | None = None):
    return [
        item
        for item in _service().repository.list("actions", project_id)
        if not status or item.status == status
    ]


@router.post("/projects/{project_id}/actions", status_code=201)
def create_action(project_id: str, body: dict):
    raise HTTPException(
        422, "Manual actions require source evidence; confirm an extracted candidate"
    )


@router.patch("/projects/{project_id}/actions/{action_id}")
def patch_action(project_id: str, action_id: str, body: dict):
    service = _service()
    item = service._action(project_id, action_id)
    allowed = {
        key: value
        for key, value in body.items()
        if key in {"title", "description", "due_date", "priority", "discipline"}
    }
    updated = item.model_copy(update=allowed)
    service.repository.save("actions", item.id, updated)
    return updated


@router.get("/projects/{project_id}/actions/{action_id}")
def action(project_id: str, action_id: str):
    return _service()._action(project_id, action_id)


@router.post("/projects/{project_id}/actions/{action_id}/assign")
def assign(project_id: str, action_id: str, body: AssignmentRequest):
    return _service().assign_action(
        project_id, action_id, body.owner_id, body.owner_name, body.actor_id
    )


@router.post("/projects/{project_id}/actions/{action_id}/transition")
@router.post("/projects/{project_id}/actions/{action_id}/complete")
@router.post("/projects/{project_id}/actions/{action_id}/reopen")
def transition(project_id: str, action_id: str, body: TransitionRequest):
    return _service().transition_action(
        project_id,
        action_id,
        body.status,
        body.actor_id,
        reason=body.reason,
        resolution=body.resolution,
        completion_evidence=body.completion_evidence,
    )


@router.post("/projects/{project_id}/actions/{action_id}/links")
def add_link(project_id: str, action_id: str, body: LinkRequest):
    return _service().add_link(
        project_id, action_id, body.workflow_type, body.reference, body.relationship, body.actor_id
    )


@router.get("/projects/{project_id}/actions/{action_id}/audit")
def action_audit(project_id: str, action_id: str):
    return [
        item
        for item in _service().repository.list("audit", project_id)
        if item.subject_id == action_id
    ]


@router.get("/projects/{project_id}/decisions")
@router.get("/projects/{project_id}/decision-register")
def decisions(project_id: str):
    return _service().repository.list("decisions", project_id)


@router.post("/projects/{project_id}/decisions", status_code=201)
def create_decision(project_id: str, body: DecisionCreate):
    raise HTTPException(
        422, "Manual decisions require source evidence; confirm an extracted candidate"
    )


@router.get("/projects/{project_id}/decisions/{decision_id}")
def decision(project_id: str, decision_id: str):
    return _service()._decision(project_id, decision_id)


@router.post("/projects/{project_id}/decisions/{decision_id}/confirm")
def confirm_decision(project_id: str, decision_id: str, body: ActorRequest):
    return _service().confirm_decision(project_id, decision_id, body.actor_id)


@router.post("/projects/{project_id}/decisions/{decision_id}/supersede")
def supersede(project_id: str, decision_id: str, body: SupersedeRequest):
    return _service().supersede_decision(
        project_id, decision_id, body.new_decision_id, body.actor_id
    )


@router.get("/projects/{project_id}/decision-conflicts")
def conflicts(project_id: str):
    return _service().repository.list("conflicts", project_id)


@router.post("/projects/{project_id}/meetings/{meeting_id}/minutes/draft")
def draft(project_id: str, meeting_id: str, body: ActorRequest):
    return _service().draft_minutes(project_id, meeting_id, body.actor_id)


@router.post("/projects/{project_id}/meetings/{meeting_id}/minutes/submit-review")
def submit_minutes(project_id: str, meeting_id: str, body: dict):
    return _service().transition_minutes(
        project_id,
        body["minutes_id"],
        MinutesStatus.PENDING_REVIEW,
        body.get("actor_id", "local-user"),
    )


@router.post("/projects/{project_id}/meetings/{meeting_id}/minutes/review")
def review_minutes(project_id: str, meeting_id: str, body: dict):
    return _service().transition_minutes(
        project_id,
        body["minutes_id"],
        MinutesStatus(body["status"]),
        body.get("actor_id", "local-user"),
    )


@router.post("/projects/{project_id}/meetings/{meeting_id}/minutes/issue")
def issue_minutes(project_id: str, meeting_id: str, body: dict):
    return _service().transition_minutes(
        project_id, body["minutes_id"], MinutesStatus.ISSUED, body.get("actor_id", "local-user")
    )


@router.post("/projects/{project_id}/meetings/{meeting_id}/minutes/{minutes_id}/{status}")
def minutes_transition(
    project_id: str, meeting_id: str, minutes_id: str, status: MinutesStatus, body: ActorRequest
):
    return _service().transition_minutes(project_id, minutes_id, status, body.actor_id)


@router.get("/projects/{project_id}/meetings/{meeting_id}/minutes/export")
def minutes_export(project_id: str, meeting_id: str):
    return [
        item
        for item in _service().repository.list("minutes", project_id)
        if item.meeting_id == meeting_id
    ]


@router.get("/projects/{project_id}/meeting-dashboard")
@router.get("/projects/{project_id}/action-dashboard")
def dashboard(project_id: str):
    return _service().dashboard(project_id)


@router.get("/projects/{project_id}/meeting-search")
def search(project_id: str, query: str):
    return _service().search(project_id, query)


@router.get("/projects/{project_id}/meeting-ask")
def ask_meeting(project_id: str, question: str):
    return MeetingQuestionService(_service().repository).answer(project_id, question)
