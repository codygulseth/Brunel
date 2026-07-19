from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict
from config import get_settings
from integration_adapters.models import Capability, ConnectionStatus
from integration_adapters.reference import (
    GenericJsonAdapter,
    InMemoryWriteAdapter,
    LocalFileAdapter,
    TestSecretProvider,
)
from integration_adapters.registry import AdapterRegistry
from integration_adapters.repository import JsonIntegrationRepository
from integration_adapters.service import IntegrationService
from p6_adapter import PrimaveraP6Adapter

router = APIRouter(prefix="/organizations/{organization_id}", tags=["integration-adapters"])
_registry = AdapterRegistry()
for _adapter in (
    LocalFileAdapter(),
    GenericJsonAdapter(),
    InMemoryWriteAdapter(),
    PrimaveraP6Adapter(),
):
    _registry.register(_adapter)


def _service():
    return IntegrationService(
        JsonIntegrationRepository(get_settings().data_directory / "integrations"),
        _registry,
        TestSecretProvider(),
    )


def _call(fn):
    try:
        value = fn()
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        if isinstance(value, tuple):
            return [x.model_dump(mode="json") if hasattr(x, "model_dump") else x for x in value]
        return value
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(409, str(exc)) from exc


class ConnectionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str
    adapter_name: str
    display_name: str
    actor: str
    configuration: dict[str, str] = {}
    secret_reference_id: str | None = None
    write_enabled: bool = False
    authorized_principal_ids: tuple[str, ...] = ()
    external_write_approver_ids: tuple[str, ...] = ()


class ImportBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str
    actor: str
    scope: dict[str, str] = {}
    cursor: str | None = None


class ProposalBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str
    capability: Capability
    source_type: str
    source_id: str
    action: str
    fields: dict[str, object]
    evidence: tuple[dict[str, object], ...]
    rationale: str
    actor: str
    expected_version: str | None = None


class ApprovalBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str
    actor: str
    rationale: str
    expires_at: datetime | None = None


class ActionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str
    actor: str


@router.get("/integration-adapters")
def adapters(organization_id: str):
    return _call(lambda: _registry.manifests())


@router.post("/integration-connections", status_code=201)
def connection(organization_id: str, body: ConnectionBody):
    return _call(
        lambda: _service().create_connection(
            organization_id,
            body.project_id,
            body.adapter_name,
            body.display_name,
            body.actor,
            secret_reference_id=body.secret_reference_id,
            configuration=body.configuration,
            write_enabled=body.write_enabled,
            authorized_principal_ids=body.authorized_principal_ids or (body.actor,),
            external_write_approver_ids=body.external_write_approver_ids,
        )
    )


@router.get("/integration-connections")
def connections(organization_id: str, project_id: str | None = None):
    return _call(lambda: _service().repository.list("connections", organization_id, project_id))


@router.post("/integration-connections/{connection_id}/test")
def test(organization_id: str, connection_id: str, body: ActionBody):
    return _call(
        lambda: _service().test_connection(
            organization_id, body.project_id, connection_id, body.actor
        )
    )


@router.post("/integration-connections/{connection_id}/status/{status}")
def status(organization_id: str, connection_id: str, status: ConnectionStatus, body: ActionBody):
    return _call(
        lambda: _service().transition_connection(
            organization_id, body.project_id, connection_id, status, body.actor
        )
    )


@router.post("/integration-connections/{connection_id}/imports")
def import_records(organization_id: str, connection_id: str, body: ImportBody):
    return _call(
        lambda: _service().import_records(
            organization_id,
            body.project_id,
            connection_id,
            body.actor,
            scope=body.scope,
            cursor=body.cursor,
        )
    )


@router.get("/integration-imports")
def imports(organization_id: str, project_id: str | None = None):
    return _call(lambda: _service().repository.list("sessions", organization_id, project_id))


@router.post("/integration-connections/{connection_id}/export-proposals", status_code=201)
def proposal(organization_id: str, connection_id: str, body: ProposalBody):
    return _call(
        lambda: _service().create_export_proposal(
            organization_id,
            body.project_id,
            connection_id,
            body.capability,
            body.source_type,
            body.source_id,
            body.action,
            body.fields,
            body.evidence,
            body.rationale,
            body.actor,
            body.expected_version,
        )
    )


@router.post("/integration-export-proposals/{proposal_id}/validate")
def validate(organization_id: str, proposal_id: str, body: ActionBody):
    return _call(
        lambda: _service().validate_export(
            organization_id, body.project_id, proposal_id, body.actor
        )
    )


@router.post("/integration-export-proposals/{proposal_id}/approve")
def approve(organization_id: str, proposal_id: str, body: ApprovalBody):
    return _call(
        lambda: _service().approve_export(
            organization_id,
            body.project_id,
            proposal_id,
            body.actor,
            body.rationale,
            body.expires_at,
        )
    )


@router.post("/integration-export-proposals/{proposal_id}/execute")
def execute(organization_id: str, proposal_id: str, body: ActionBody):
    return _call(
        lambda: _service().execute_export(organization_id, body.project_id, proposal_id, body.actor)
    )


@router.get("/integration-health")
def health(organization_id: str, project_id: str | None = None):
    return _call(lambda: _service().health(organization_id, project_id))
