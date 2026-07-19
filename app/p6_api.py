"""Project-scoped API for the Primavera P6 adapter."""

from datetime import datetime
from pathlib import Path
from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict
from config import get_settings
from schedule_intelligence.repository import JsonScheduleRepository
from schedule_intelligence.service import ScheduleIntelligenceService
from app import integration_api
from p6_adapter import PrimaveraP6Adapter, PrimaveraP6Service


router = APIRouter(
    prefix="/organizations/{organization_id}/projects/{project_id}/p6",
    tags=["primavera-p6"],
)


def _service():
    adapter = integration_api._registry.get("primavera_p6")
    assert isinstance(adapter, PrimaveraP6Adapter)
    return PrimaveraP6Service(
        integration_api._service(),
        ScheduleIntelligenceService(
            JsonScheduleRepository(get_settings().data_directory / "schedule-intelligence")
        ),
        adapter,
    )


def _public(value):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, tuple):
        return [_public(x) for x in value]
    return value


def _call(fn):
    try:
        return _public(fn())
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(409, str(exc)) from exc


class FileBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor: str
    file_path: Path
    schedule_name: str | None = None


class MapBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    external_project_id: str
    actor: str


class CompareBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    old_revision_id: str
    new_revision_id: str


class ExportBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    activity_revision_id: str
    field: str
    value: Any
    evidence: tuple[dict[str, Any], ...]
    rationale: str
    actor: str
    expected_version: str


class ActionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor: str


class ApprovalBody(ActionBody):
    rationale: str
    expires_at: datetime | None = None


class RejectionBody(ActionBody):
    rationale: str


class QuestionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    connection_id: str
    question: str


class ReviewBody(ActionBody):
    decision: str


@router.get("/adapter-info")
def adapter_info(organization_id: str, project_id: str):
    return _public(_service().capabilities())


@router.post("/connections/{connection_id}/discover-projects")
def discover(organization_id: str, project_id: str, connection_id: str, body: FileBody):
    return _call(
        lambda: _service().discover_projects(
            organization_id, project_id, connection_id, body.actor, body.file_path
        )
    )


@router.post("/connections/{connection_id}/map-project")
def map_project(organization_id: str, project_id: str, connection_id: str, body: MapBody):
    return _call(
        lambda: _service().map_project(
            organization_id, project_id, connection_id, body.external_project_id, body.actor
        )
    )


@router.post("/connections/{connection_id}/imports", status_code=201)
def import_schedule(organization_id: str, project_id: str, connection_id: str, body: FileBody):
    return _call(
        lambda: _service().import_schedule(
            organization_id,
            project_id,
            connection_id,
            body.actor,
            body.file_path,
            name=body.schedule_name,
        )
    )


@router.get("/revisions")
def revisions(organization_id: str, project_id: str):
    return _public(_service().revisions(project_id))


@router.get("/revisions/{revision_id}")
def revision(organization_id: str, project_id: str, revision_id: str):
    return _call(
        lambda: _service().schedules.repository.get("revisions", revision_id, project_id)
        or (_ for _ in ()).throw(ValueError("P6 revision not found"))
    )


@router.post("/comparisons")
def compare(organization_id: str, project_id: str, body: CompareBody):
    return _call(lambda: _service().compare(project_id, body.old_revision_id, body.new_revision_id))


@router.get("/revisions/{revision_id}/quality")
def quality(organization_id: str, project_id: str, revision_id: str):
    return _call(lambda: _service().quality(project_id, revision_id))


@router.get("/search")
def search(organization_id: str, project_id: str, query: str, revision_id: str | None = None):
    return _call(lambda: _service().search(project_id, query, revision_id))


@router.get("/connections/{connection_id}/conflicts")
def conflicts(organization_id: str, project_id: str, connection_id: str):
    return _call(
        lambda: tuple(
            x
            for x in _service().integrations.repository.list(
                "conflicts", organization_id, project_id
            )
            if x.connection_id == connection_id
        )
    )


@router.post("/conflicts/{conflict_id}/review")
def review_conflict(organization_id: str, project_id: str, conflict_id: str, body: ReviewBody):
    return _call(
        lambda: _service().integrations.review_conflict(
            organization_id, project_id, conflict_id, body.decision, body.actor
        )
    )


@router.get("/connections/{connection_id}/activity-mapping-candidates")
def mapping_candidates(organization_id: str, project_id: str, connection_id: str):
    return _call(
        lambda: _service().activity_mapping_candidates(organization_id, project_id, connection_id)
    )


@router.post("/activity-mappings/{mapping_id}/review")
def review_mapping(organization_id: str, project_id: str, mapping_id: str, body: ReviewBody):
    return _call(
        lambda: _service().review_activity_mapping(
            organization_id, project_id, mapping_id, body.decision, body.actor
        )
    )


@router.post("/connections/{connection_id}/export-proposals", status_code=201)
def create_export(organization_id: str, project_id: str, connection_id: str, body: ExportBody):
    return _call(
        lambda: _service().create_export_proposal(
            organization_id,
            project_id,
            connection_id,
            body.activity_revision_id,
            body.field,
            body.value,
            body.evidence,
            body.rationale,
            body.actor,
            body.expected_version,
        )
    )


@router.get("/export-proposals")
def export_proposals(organization_id: str, project_id: str):
    return _call(
        lambda: _service().integrations.repository.list("proposals", organization_id, project_id)
    )


@router.post("/export-proposals/{proposal_id}/validate")
def validate(organization_id: str, project_id: str, proposal_id: str, body: ActionBody):
    return _call(
        lambda: _service().integrations.validate_export(
            organization_id, project_id, proposal_id, body.actor
        )
    )


@router.post("/export-proposals/{proposal_id}/approve")
def approve(organization_id: str, project_id: str, proposal_id: str, body: ApprovalBody):
    return _call(
        lambda: _service().integrations.approve_export(
            organization_id, project_id, proposal_id, body.actor, body.rationale, body.expires_at
        )
    )


@router.post("/export-proposals/{proposal_id}/reject")
def reject(organization_id: str, project_id: str, proposal_id: str, body: RejectionBody):
    return _call(
        lambda: _service().integrations.reject_export(
            organization_id, project_id, proposal_id, body.actor, body.rationale
        )
    )


@router.post("/export-proposals/{proposal_id}/execute")
def execute(organization_id: str, project_id: str, proposal_id: str, body: ActionBody):
    return _call(
        lambda: _service().integrations.execute_export(
            organization_id, project_id, proposal_id, body.actor
        )
    )


@router.post("/export-proposals/{proposal_id}/reconcile/{execution_id}")
def reconcile(
    organization_id: str, project_id: str, proposal_id: str, execution_id: str, body: ActionBody
):
    return _call(
        lambda: _service().integrations.reconcile(
            organization_id, project_id, proposal_id, execution_id, body.actor
        )
    )


@router.get("/connections/{connection_id}/dashboard")
def dashboard(organization_id: str, project_id: str, connection_id: str):
    return _call(lambda: _service().dashboard(organization_id, project_id, connection_id))


@router.post("/questions")
def question(organization_id: str, project_id: str, body: QuestionBody):
    return _call(
        lambda: _service().answer(organization_id, project_id, body.connection_id, body.question)
    )
