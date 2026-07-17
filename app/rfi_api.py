# mypy: disable-error-code=no-untyped-def
"""Thin FastAPI routes for canonical RFI services."""

from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from change_workflow.models import ActorReference, ImpactCertainty, ReviewerReference
from change_workflow.repository import JsonChangeWorkflowRepository
from config import get_settings
from rfi.models import RFIPriority, RFIImpactType, RFIResponseType, RFIReviewDecision, RFIStatus
from rfi.models import RFIEvidenceReference
from rfi.numbering import ProjectRFINumberingService
from rfi.qa import RFIQuestionService
from rfi.repository import JsonRFIRepository
from rfi.reporting import RFILogService, RFIRenderer
from rfi.service import RFIService
from storage import JsonDocumentRepository

router = APIRouter()


def _public(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: _public(item) for key, item in value.items() if key != "source_location"}
    if isinstance(value, (list, tuple)):
        return [_public(item) for item in value]
    return value


def _repo() -> JsonRFIRepository:
    return JsonRFIRepository(get_settings().data_directory / "rfi")


def _service() -> RFIService:
    settings = get_settings()
    repository = _repo()
    return RFIService(
        repository,
        JsonChangeWorkflowRepository(settings.data_directory / "change-workflow"),
        numbering=ProjectRFINumberingService(
            repository, settings.rfi.numbering_prefix, settings.rfi.numbering_digits
        ),
        duplicate_threshold=settings.rfi.duplicate_similarity_threshold,
        assign_number_at_creation=settings.rfi.assign_number_at_creation,
        documents=JsonDocumentRepository(settings.data_directory / "ingested"),
    )


def _actor(i: str | None, n: str | None) -> ActorReference:
    return ActorReference(id=i or "local-user", display_name=n or "Local User")


class CreateRFI(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject: str = Field(min_length=1)
    question: str = Field(min_length=1)
    background: str = ""
    responsible_party: str | None = None
    required_date: date | None = None
    evidence: tuple[RFIEvidenceReference, ...] = ()


class DraftRFI(BaseModel):
    model_config = ConfigDict(extra="forbid")
    change_id: str
    instructions: str | None = None
    responsible_party: str | None = None
    required_date: date | None = None
    selected_evidence: tuple[RFIEvidenceReference, ...] = ()


class UpdateRFI(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject: str | None = None
    question: str | None = None
    background: str | None = None
    change_summary: str = Field(min_length=1)


class ReviewerBody(BaseModel):
    reviewer_id: str
    reviewer_name: str
    comments: str | None = None
    decision: RFIReviewDecision | None = None


class TransitionBody(BaseModel):
    status: RFIStatus
    reason: str | None = None
    resolution: str | None = None


class CloseBody(BaseModel):
    resolution: str = Field(min_length=1)


class ReopenBody(BaseModel):
    reason: str = Field(min_length=1)


class ResponseBody(BaseModel):
    text: str = Field(min_length=1)
    responding_party: str
    response_type: RFIResponseType = RFIResponseType.OFFICIAL


class ImpactBody(BaseModel):
    impact_type: RFIImpactType
    certainty: ImpactCertainty
    description: str = Field(min_length=1)


class RFIQuestionBody(BaseModel):
    question: str = Field(min_length=1)


@router.get("/projects/{project_id}/rfis")
def list_rfis(
    project_id: str,
    status: RFIStatus | None = None,
    discipline: str | None = None,
    priority: RFIPriority | None = None,
    reviewer_id: str | None = None,
    responsible_party: str | None = None,
    overdue: bool | None = None,
    open_only: bool | None = None,
    project_change_id: str | None = None,
    search: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    items = RFILogService(_repo()).list(
        project_id,
        status=status,
        discipline=discipline,
        priority=priority,
        reviewer_id=reviewer_id,
        responsible_party=responsible_party,
        overdue=overdue,
        open_only=open_only,
        project_change_id=project_change_id,
        search=search,
    )
    return _public({"items": items[offset : offset + limit], "total": len(items)})


@router.post("/projects/{project_id}/rfis", status_code=201)
def create_rfi(
    project_id: str,
    body: CreateRFI,
    x_actor_id: str | None = Header(None),
    x_actor_name: str | None = Header(None),
):
    return _public(
        _service().create(
            project_id=project_id,
            subject=body.subject,
            question=body.question,
            background=body.background,
            actor=_actor(x_actor_id, x_actor_name),
            responsible_party=body.responsible_party,
            required_date=body.required_date,
            evidence=body.evidence,
        )
    )


@router.post("/projects/{project_id}/rfis/draft-from-change", status_code=201)
def draft_from_change(
    project_id: str,
    body: DraftRFI,
    x_actor_id: str | None = Header(None),
    x_actor_name: str | None = Header(None),
):
    return _public(
        _service().draft_from_change(
            project_id,
            body.change_id,
            _actor(x_actor_id, x_actor_name),
            instructions=body.instructions,
            responsible_party=body.responsible_party,
            required_date=body.required_date,
            selected_evidence=body.selected_evidence,
        )
    )


@router.get("/projects/{project_id}/rfis/{rfi_id}")
def get_rfi(project_id: str, rfi_id: str):
    return _public(_service().get(project_id, rfi_id))


@router.patch("/projects/{project_id}/rfis/{rfi_id}")
def update_rfi(
    project_id: str,
    rfi_id: str,
    body: UpdateRFI,
    x_actor_id: str | None = Header(None),
    x_actor_name: str | None = Header(None),
):
    return _public(
        _service().revise(
            project_id,
            rfi_id,
            _actor(x_actor_id, x_actor_name),
            subject=body.subject,
            question=body.question,
            background=body.background,
            summary=body.change_summary,
        )
    )


@router.post("/projects/{project_id}/rfis/{rfi_id}/submit-review")
def submit_review(
    project_id: str,
    rfi_id: str,
    body: ReviewerBody,
    x_actor_id: str | None = Header(None),
    x_actor_name: str | None = Header(None),
):
    service = _service()
    actor = _actor(x_actor_id, x_actor_name)
    service.assign_reviewer(
        project_id,
        rfi_id,
        ReviewerReference(id=body.reviewer_id, display_name=body.reviewer_name),
        actor,
    )
    return _public(service.transition(project_id, rfi_id, RFIStatus.PENDING_INTERNAL_REVIEW, actor))


@router.post("/projects/{project_id}/rfis/{rfi_id}/review")
def review(
    project_id: str,
    rfi_id: str,
    body: ReviewerBody,
    x_actor_id: str | None = Header(None),
    x_actor_name: str | None = Header(None),
):
    if body.decision is None:
        raise HTTPException(422, "decision is required")
    return _public(
        _service().review(
            project_id,
            rfi_id,
            body.decision,
            ReviewerReference(id=body.reviewer_id, display_name=body.reviewer_name),
            _actor(x_actor_id, x_actor_name),
            body.comments,
        )
    )


@router.post("/projects/{project_id}/rfis/{rfi_id}/issue")
def issue(
    project_id: str,
    rfi_id: str,
    x_actor_id: str | None = Header(None),
    x_actor_name: str | None = Header(None),
):
    return _public(
        _service().transition(
            project_id, rfi_id, RFIStatus.ISSUED, _actor(x_actor_id, x_actor_name)
        )
    )


@router.post("/projects/{project_id}/rfis/{rfi_id}/responses")
def response(
    project_id: str,
    rfi_id: str,
    body: ResponseBody,
    x_actor_id: str | None = Header(None),
    x_actor_name: str | None = Header(None),
):
    return _public(
        _service().record_response(
            project_id,
            rfi_id,
            _actor(x_actor_id, x_actor_name),
            text=body.text,
            responding_party=body.responding_party,
            response_type=body.response_type,
        )
    )


@router.post("/projects/{project_id}/rfis/{rfi_id}/analyze-response")
def analyze(
    project_id: str,
    rfi_id: str,
    x_actor_id: str | None = Header(None),
    x_actor_name: str | None = Header(None),
):
    return _public(
        _service().analyze_response(project_id, rfi_id, _actor(x_actor_id, x_actor_name))
    )


@router.post("/projects/{project_id}/rfis/{rfi_id}/impacts")
def add_impact(
    project_id: str,
    rfi_id: str,
    body: ImpactBody,
    x_actor_id: str | None = Header(None),
    x_actor_name: str | None = Header(None),
):
    return _public(
        _service().add_impact(
            project_id,
            rfi_id,
            _actor(x_actor_id, x_actor_name),
            impact_type=body.impact_type,
            certainty=body.certainty,
            description=body.description,
        )
    )


@router.post("/projects/{project_id}/rfis/{rfi_id}/transition")
def transition(
    project_id: str,
    rfi_id: str,
    body: TransitionBody,
    x_actor_id: str | None = Header(None),
    x_actor_name: str | None = Header(None),
):
    return _public(
        _service().transition(
            project_id,
            rfi_id,
            body.status,
            _actor(x_actor_id, x_actor_name),
            reason=body.reason,
            resolution=body.resolution,
        )
    )


@router.post("/projects/{project_id}/rfis/{rfi_id}/close")
def close_rfi(
    project_id: str,
    rfi_id: str,
    body: CloseBody,
    x_actor_id: str | None = Header(None),
    x_actor_name: str | None = Header(None),
):
    return _public(
        _service().transition(
            project_id,
            rfi_id,
            RFIStatus.CLOSED,
            _actor(x_actor_id, x_actor_name),
            resolution=body.resolution,
        )
    )


@router.post("/projects/{project_id}/rfis/{rfi_id}/reopen")
def reopen_rfi(
    project_id: str,
    rfi_id: str,
    body: ReopenBody,
    x_actor_id: str | None = Header(None),
    x_actor_name: str | None = Header(None),
):
    return _public(
        _service().transition(
            project_id,
            rfi_id,
            RFIStatus.UNDER_REVIEW,
            _actor(x_actor_id, x_actor_name),
            reason=body.reason,
        )
    )


@router.get("/projects/{project_id}/rfis/{rfi_id}/audit")
def audit(project_id: str, rfi_id: str):
    _service().get(project_id, rfi_id)
    return _public(_repo().audit(project_id, rfi_id))


@router.get("/projects/{project_id}/rfi-log")
def log(project_id: str, status: RFIStatus | None = None):
    return _public(RFILogService(_repo()).list(project_id, status=status))


@router.get("/projects/{project_id}/rfi-dashboard")
def dashboard(project_id: str):
    return _public(RFILogService(_repo()).dashboard(project_id))


@router.post("/projects/{project_id}/rfi-questions")
def ask_rfi_question(project_id: str, body: RFIQuestionBody):
    return _public(RFIQuestionService(_repo()).answer(project_id, body.question))


@router.get("/projects/{project_id}/rfis/{rfi_id}/export")
def export(
    project_id: str,
    rfi_id: str,
    format: Literal["markdown", "json"] = "markdown",
    x_actor_id: str | None = Header(None),
    x_actor_name: str | None = Header(None),
):
    item = _service().record_export(project_id, rfi_id, _actor(x_actor_id, x_actor_name), format)
    return {
        "format": format,
        "content": item.model_dump_json(indent=2)
        if format == "json"
        else RFIRenderer().markdown(item),
    }
