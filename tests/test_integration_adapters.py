from datetime import UTC, datetime, timedelta
import pytest
from integration_adapters.interfaces import AdapterError
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


def setup_service(tmp_path, adapter):
    registry = AdapterRegistry()
    registry.register(adapter)
    return IntegrationService(
        JsonIntegrationRepository(tmp_path), registry, TestSecretProvider()
    ), registry


def test_manifests_registry_read_only_default_and_nonmutating_test(tmp_path):
    service, registry = setup_service(tmp_path, GenericJsonAdapter())
    manifest = registry.manifests()[0]
    assert not manifest.write_capable and Capability.IMPORT_RECORDS in manifest.supported_operations
    connection = service.create_connection("org", "p1", manifest.adapter_name, "JSON", "admin")
    tested = service.test_connection("org", "p1", connection.id, "admin")
    assert tested.status == ConnectionStatus.ACTIVE
    with pytest.raises(AdapterError):
        registry.get(manifest.adapter_name).execute_approved_export({}, "key", None)
    assert service.repository.get("connections", connection.id, "other", "p1") is None


def test_immutable_idempotent_import_cursor_and_external_deletion(tmp_path):
    adapter = GenericJsonAdapter(
        (
            {
                "external_id": "A",
                "external_version": "1",
                "target_domain": "document",
                "title": "Switchgear",
            },
        )
    )
    service, _ = setup_service(tmp_path, adapter)
    connection = service.create_connection(
        "org", "p1", adapter.manifest.adapter_name, "JSON", "admin"
    )
    service.test_connection("org", "p1", connection.id, "admin")
    session, records = service.import_records(
        "org", "p1", connection.id, "admin", scope={"page_size": "10"}
    )
    assert session.cursor_committed == "1" and len(records) == 1
    replay, replayed = service.import_records(
        "org", "p1", connection.id, "admin", scope={"page_size": "10"}
    )
    assert replay.duplicates == 1 and not replayed
    raw = service.repository.list("raw", "org", "p1")[0]
    conflict = service.record_external_deletion("org", "p1", raw.id, "reviewer")
    assert (
        conflict.review_status == "proposed"
        and service.repository.get("raw", raw.id, "org", "p1") is not None
    )


def test_external_write_requires_validation_human_approval_idempotency_and_reconciliation(tmp_path):
    adapter = InMemoryWriteAdapter()
    service, _ = setup_service(tmp_path, adapter)
    connection = service.create_connection(
        "org",
        "p1",
        adapter.manifest.adapter_name,
        "Memory",
        "admin",
        write_enabled=True,
        authorized_principal_ids=("admin", "pm", "authorized-user"),
        external_write_approver_ids=("authorized-user",),
    )
    service.test_connection("org", "p1", connection.id, "admin")
    proposal = service.create_export_proposal(
        "org",
        "p1",
        connection.id,
        Capability.EXECUTE_APPROVED_EXPORT,
        "rfi",
        "rfi-1",
        "issue",
        {"record_id": "RFI-1", "status": "issued"},
        ({"citation": "rfi-1"},),
        "Human requested external issue",
        "pm",
    )
    with pytest.raises(ValueError):
        service.execute_export("org", "p1", proposal.id, "authorized-user")
    proposal = service.validate_export("org", "p1", proposal.id, "pm")
    proposal = service.approve_export(
        "org",
        "p1",
        proposal.id,
        "authorized-user",
        "Explicit external-write approval",
        datetime.now(UTC) + timedelta(hours=1),
    )
    execution = service.execute_export("org", "p1", proposal.id, "authorized-user")
    replay = service.execute_export("org", "p1", proposal.id, "authorized-user")
    assert adapter.calls == 1 and replay.replayed
    with pytest.raises(PermissionError):
        service.execute_export("org", "p1", proposal.id, "pm")
    result = service.reconcile("org", "p1", proposal.id, execution.id, "authorized-user")
    assert result.status == "matched"


def test_read_only_connection_blocks_export_and_secrets_are_not_persisted(tmp_path):
    service, _ = setup_service(tmp_path, LocalFileAdapter())
    connection = service.create_connection(
        "org", "p1", "local_file_reference", "Files", "admin", configuration={"root": str(tmp_path)}
    )
    proposal = service.create_export_proposal(
        "org",
        "p1",
        connection.id,
        Capability.EXECUTE_APPROVED_EXPORT,
        "document",
        "d1",
        "upload",
        {"name": "x"},
        ({"citation": "d1"},),
        "review",
        "admin",
    )
    validated = service.validate_export("org", "p1", proposal.id, "admin")
    assert "connection_read_only" in validated.validation_errors
    assert (
        "password" not in connection.model_dump_json().casefold()
        and "token" not in connection.model_dump_json().casefold()
    )
