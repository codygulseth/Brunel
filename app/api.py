# mypy: disable-error-code=no-untyped-def
"""Unauthenticated development API for canonical Brunel workflow services."""

from datetime import date
from uuid import uuid4
from typing import Any

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from change_workflow.dashboard import ProjectChangeDashboardService
from change_workflow.errors import ChangeNotFoundError, ChangeWorkflowError
from change_workflow.models import (
    ActorReference,
    ChangeDisposition,
    ChangePriority,
    ChangeStatus,
    ImpactCertainty,
    NoteType,
    RelationshipType,
    ReviewerReference,
    WorkflowType,
)
from change_workflow.repository import JsonChangeWorkflowRepository
from change_workflow.service import ProjectChangeService
from change_workflow.staleness import ChangeRegenerationService
from config import get_settings
from revision_intelligence.repository import JsonComparisonRepository
from revision_intelligence.models import ComparisonRequest
from revision_intelligence.service import RevisionComparisonService
from rfi.errors import RFIError, RFINotFoundError
from submittal.errors import SubmittalError, SubmittalNotFoundError
from storage import JsonDocumentRepository
from app.rfi_api import router as rfi_router
from app.submittal_api import router as submittal_router
from app.submittal_attachment_api import router as submittal_attachment_router
from app.drawing_api import router as drawing_router
from app.meeting_api import router as meeting_router
from app.procurement_api import router as procurement_router

app = FastAPI(
    title="Brunel Development API",
    version="0.5.0",
    description="Development-only API. Authentication and authorization are not implemented.",
)
app.include_router(rfi_router)
app.include_router(submittal_router)
app.include_router(submittal_attachment_router)
app.include_router(drawing_router)
app.include_router(meeting_router)
app.include_router(procurement_router)


def _repository() -> JsonChangeWorkflowRepository:
    return JsonChangeWorkflowRepository(get_settings().data_directory / "change-workflow")


def _actor(actor_id: str | None, actor_name: str | None) -> ActorReference:
    return ActorReference(id=actor_id or "local-user", display_name=actor_name or "Local User")


def _public(value: Any) -> Any:
    """Remove internal filesystem locations from API serialization."""
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: _public(item) for key, item in value.items() if key != "source_location"}
    if isinstance(value, (list, tuple)):
        return [_public(item) for item in value]
    return value


class AssignmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assignee_id: str
    assignee_name: str
    email: str | None = None
    team: str | None = None
    discipline: str | None = None
    due_date: date | None = None
    note: str | None = None


class TransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: ChangeStatus
    reason: str | None = None
    resolution: str | None = None
    stale_acknowledged: bool = False


class DispositionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    disposition: ChangeDisposition
    explanation: str = Field(min_length=1)
    cost_impact: ImpactCertainty = ImpactCertainty.UNKNOWN
    schedule_impact: ImpactCertainty = ImpactCertainty.UNKNOWN
    scope_impact: ImpactCertainty = ImpactCertainty.UNKNOWN


class NoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=10_000)
    note_type: NoteType = NoteType.GENERAL


class LinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workflow_type: WorkflowType
    reference: str = Field(min_length=1)
    relationship: RelationshipType = RelationshipType.RELATED_TO
    url: str | None = None


class RelatedItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workflow_type: WorkflowType


class ResolutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str = Field(min_length=1)


class ReasonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str | None = None


@app.middleware("http")
async def correlation_id(request: Request, call_next):
    value = request.headers.get("X-Correlation-ID", uuid4().hex)
    response: Response = await call_next(request)
    response.headers["X-Correlation-ID"] = value
    return response


@app.exception_handler(ChangeWorkflowError)
async def workflow_error(_: Request, exc: ChangeWorkflowError):
    status = 404 if isinstance(exc, ChangeNotFoundError) else 409
    return __import__("fastapi").responses.JSONResponse(
        status_code=status, content={"detail": str(exc)}
    )


@app.exception_handler(RFIError)
async def rfi_error(_: Request, exc: RFIError):
    status = 404 if isinstance(exc, RFINotFoundError) else 409
    return __import__("fastapi").responses.JSONResponse(
        status_code=status, content={"detail": str(exc)}
    )


@app.exception_handler(SubmittalError)
async def submittal_error(_: Request, exc: SubmittalError):
    status = 404 if isinstance(exc, SubmittalNotFoundError) else 409
    return __import__("fastapi").responses.JSONResponse(
        status_code=status, content={"detail": str(exc)}
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/version")
def version():
    return {"name": "Brunel", "version": app.version, "authentication": "not_configured"}


@app.get("/projects/{project_id}/change-dashboard")
def dashboard(project_id: str):
    return _public(ProjectChangeDashboardService(_repository()).build(project_id))


@app.get("/projects/{project_id}/review-queue")
def review_queue(project_id: str):
    return _public(ProjectChangeDashboardService(_repository()).build(project_id).priority_queue)


@app.get("/projects/{project_id}/changes")
def list_changes(
    project_id: str,
    status: ChangeStatus | None = None,
    priority: ChangePriority | None = None,
    assignee: str | None = None,
    stale: bool | None = None,
    search: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    items = _repository().list_changes(project_id)
    if status:
        items = tuple(i for i in items if i.status == status)
    if priority:
        items = tuple(i for i in items if i.priority == priority)
    if assignee:
        items = tuple(
            i for i in items if any(a.active and a.assignee.id == assignee for a in i.assignments)
        )
    if stale is not None:
        items = tuple(i for i in items if i.source_stale == stale)
    if search:
        items = tuple(
            i
            for i in items
            if search.casefold()
            in f"{i.title} {i.description} {i.resolution_summary or ''}".casefold()
        )
    return {
        "items": _public(items[offset : offset + limit]),
        "total": len(items),
        "limit": limit,
        "offset": offset,
    }


@app.get("/projects/{project_id}/changes/{change_id}")
def get_change(project_id: str, change_id: str):
    return _public(ProjectChangeService(_repository()).get(project_id, change_id))


@app.post("/projects/{project_id}/comparisons/{comparison_id}/register")
def generate_register(
    project_id: str,
    comparison_id: str,
    x_actor_id: str | None = Header(None),
    x_actor_name: str | None = Header(None),
):
    comparison = JsonComparisonRepository(
        get_settings().data_directory / "revision-intelligence"
    ).get(comparison_id)
    if comparison is None or comparison.project_id != project_id:
        raise HTTPException(404, "Comparison not found in requested project")
    return ProjectChangeService(_repository()).generate_register(
        comparison, _actor(x_actor_id, x_actor_name)
    )


@app.post("/projects/{project_id}/changes/{change_id}/assign")
def assign(
    project_id: str,
    change_id: str,
    body: AssignmentRequest,
    x_actor_id: str | None = Header(None),
    x_actor_name: str | None = Header(None),
):
    reviewer = ReviewerReference(
        id=body.assignee_id,
        display_name=body.assignee_name,
        email=body.email,
        team=body.team,
        discipline=body.discipline,
    )
    result = ProjectChangeService(_repository()).assign(
        project_id,
        change_id,
        reviewer,
        _actor(x_actor_id, x_actor_name),
        due_date=body.due_date,
        note=body.note,
    )
    return _public(result)


@app.post("/projects/{project_id}/changes/{change_id}/unassign")
def unassign(
    project_id: str,
    change_id: str,
    body: ReasonRequest,
    x_actor_id: str | None = Header(None),
    x_actor_name: str | None = Header(None),
):
    result = ProjectChangeService(_repository()).unassign(
        project_id,
        change_id,
        _actor(x_actor_id, x_actor_name),
        reason=body.reason,
    )
    return _public(result)


@app.post("/projects/{project_id}/changes/{change_id}/transition")
def transition(
    project_id: str,
    change_id: str,
    body: TransitionRequest,
    x_actor_id: str | None = Header(None),
    x_actor_name: str | None = Header(None),
):
    result = ProjectChangeService(_repository()).transition(
        project_id,
        change_id,
        body.status,
        _actor(x_actor_id, x_actor_name),
        reason=body.reason,
        resolution=body.resolution,
        stale_acknowledged=body.stale_acknowledged,
    )
    return _public(result)


@app.post("/projects/{project_id}/changes/{change_id}/disposition")
def disposition(
    project_id: str,
    change_id: str,
    body: DispositionRequest,
    x_actor_id: str | None = Header(None),
    x_actor_name: str | None = Header(None),
):
    result = ProjectChangeService(_repository()).disposition(
        project_id,
        change_id,
        body.disposition,
        _actor(x_actor_id, x_actor_name),
        body.explanation,
        cost=body.cost_impact,
        schedule=body.schedule_impact,
        scope=body.scope_impact,
    )
    return _public(result)


@app.post("/projects/{project_id}/changes/{change_id}/notes")
def add_note(
    project_id: str,
    change_id: str,
    body: NoteRequest,
    x_actor_id: str | None = Header(None),
    x_actor_name: str | None = Header(None),
):
    result = ProjectChangeService(_repository()).add_note(
        project_id, change_id, body.text, _actor(x_actor_id, x_actor_name), body.note_type
    )
    return _public(result)


@app.get("/projects/{project_id}/changes/{change_id}/notes")
def notes(project_id: str, change_id: str):
    return _public(ProjectChangeService(_repository()).get(project_id, change_id).notes)


@app.get("/projects/{project_id}/changes/{change_id}/audit")
def change_audit(project_id: str, change_id: str):
    ProjectChangeService(_repository()).get(project_id, change_id)
    return _public(_repository().list_audit(project_id, change_id))


@app.get("/projects/{project_id}/audit-events")
def audit_events(
    project_id: str, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)
):
    items = _repository().list_audit(project_id)
    return {"items": _public(items[offset : offset + limit]), "total": len(items)}


@app.post("/projects/{project_id}/changes/{change_id}/links")
def add_link(
    project_id: str,
    change_id: str,
    body: LinkRequest,
    x_actor_id: str | None = Header(None),
    x_actor_name: str | None = Header(None),
):
    result = ProjectChangeService(_repository()).add_link(
        project_id,
        change_id,
        body.workflow_type,
        body.reference,
        body.relationship,
        _actor(x_actor_id, x_actor_name),
        url=body.url,
    )
    return _public(result)


@app.post("/projects/{project_id}/changes/{change_id}/related-items")
def related_item(
    project_id: str,
    change_id: str,
    body: RelatedItemRequest,
    x_actor_id: str | None = Header(None),
    x_actor_name: str | None = Header(None),
):
    result = ProjectChangeService(_repository()).create_related_item(
        project_id, change_id, body.workflow_type, _actor(x_actor_id, x_actor_name)
    )
    return _public(result)


@app.delete("/projects/{project_id}/changes/{change_id}/links/{link_id}")
def remove_link(
    project_id: str,
    change_id: str,
    link_id: str,
    x_actor_id: str | None = Header(None),
    x_actor_name: str | None = Header(None),
):
    result = ProjectChangeService(_repository()).remove_link(
        project_id, change_id, link_id, _actor(x_actor_id, x_actor_name)
    )
    return _public(result)


@app.post("/projects/{project_id}/changes/{change_id}/resolve")
def resolve_change(
    project_id: str,
    change_id: str,
    body: ResolutionRequest,
    x_actor_id: str | None = Header(None),
    x_actor_name: str | None = Header(None),
):
    result = ProjectChangeService(_repository()).transition(
        project_id,
        change_id,
        ChangeStatus.RESOLVED,
        _actor(x_actor_id, x_actor_name),
        resolution=body.summary,
    )
    return _public(result)


@app.post("/projects/{project_id}/changes/{change_id}/reopen")
def reopen_change(
    project_id: str,
    change_id: str,
    body: ReasonRequest,
    x_actor_id: str | None = Header(None),
    x_actor_name: str | None = Header(None),
):
    result = ProjectChangeService(_repository()).transition(
        project_id,
        change_id,
        ChangeStatus.UNDER_REVIEW,
        _actor(x_actor_id, x_actor_name),
        reason=body.reason,
    )
    return _public(result)


def _regeneration_service() -> ChangeRegenerationService:
    settings = get_settings()
    documents = JsonDocumentRepository(settings.data_directory / "ingested")
    comparisons = JsonComparisonRepository(settings.data_directory / "revision-intelligence")
    comparison_service = RevisionComparisonService(documents, comparisons)
    return ChangeRegenerationService(comparison_service, ProjectChangeService(_repository()))


@app.post("/projects/{project_id}/comparisons/{comparison_id}/staleness-check")
def staleness_check(project_id: str, comparison_id: str):
    comparison = JsonComparisonRepository(
        get_settings().data_directory / "revision-intelligence"
    ).get(comparison_id)
    if comparison is None or comparison.project_id != project_id:
        raise HTTPException(404, "Comparison not found in requested project")
    return _regeneration_service().assess(comparison)


@app.post("/projects/{project_id}/comparisons/{comparison_id}/regenerate")
def regenerate_comparison(
    project_id: str,
    comparison_id: str,
    x_actor_id: str | None = Header(None),
    x_actor_name: str | None = Header(None),
):
    comparison = JsonComparisonRepository(
        get_settings().data_directory / "revision-intelligence"
    ).get(comparison_id)
    if comparison is None or comparison.project_id != project_id:
        raise HTTPException(404, "Comparison not found in requested project")
    regenerated, result = _regeneration_service().regenerate(
        comparison,
        ComparisonRequest(
            project_id=project_id,
            old_document_id=comparison.old_document.document_id,
            new_document_id=comparison.new_document.document_id,
        ),
        _actor(x_actor_id, x_actor_name),
    )
    return {"comparison_id": regenerated.id, "register": _public(result)}


@app.get("/projects/{project_id}/notification-outbox")
def outbox(project_id: str):
    return _public(_repository().list_notifications(project_id))


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "app.api:app",
        host=settings.workflow.api_host,
        port=settings.workflow.api_port,
        reload=False,
    )
