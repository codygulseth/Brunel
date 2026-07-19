from pathlib import Path
from typing import Any
from .interfaces import IntegrationAdapter, SecretProvider
from .models import AdapterManifest, Capability


class TestSecretProvider(SecretProvider):
    __test__ = False

    def __init__(self, available: tuple[str, ...] = ()):
        self.available = set(available)

    def resolve(self, reference_id: str) -> object | None:
        return object() if reference_id in self.available else None


class GenericJsonAdapter(IntegrationAdapter):
    def __init__(self, records: tuple[dict[str, Any], ...] = ()):
        self.records = records

    @property
    def manifest(self):
        return AdapterManifest(
            adapter_name="generic_json_reference",
            adapter_version="1.0.0",
            category="generic_api",
            supported_record_types=("generic",),
            supported_operations=(
                Capability.CONNECTION_TEST,
                Capability.IMPORT_RECORDS,
                Capability.LIST_CHANGES,
            ),
            incremental_sync=True,
            known_limitations=(
                "Deterministic test/reference adapter; not a production connector.",
            ),
        )

    def test_connection(self, configuration, secret):
        return {"ok": True, "mutated_external_data": False}

    def import_records(self, scope, cursor):
        start = int(cursor or 0)
        page = self.records[start : start + int(scope.get("page_size", "100"))]
        return tuple(page), str(start + len(page))


class LocalFileAdapter(IntegrationAdapter):
    @property
    def manifest(self):
        return AdapterManifest(
            adapter_name="local_file_reference",
            adapter_version="1.0.0",
            category="file_system",
            supported_record_types=(
                "document",
                "drawing",
                "schedule",
                "daily_report",
                "attachment",
            ),
            supported_operations=(Capability.CONNECTION_TEST, Capability.IMPORT_RECORDS),
            attachments=True,
            revisions=True,
            required_configuration=("root",),
            known_limitations=(
                "Reads fixture metadata only; canonical domain ingestion performs file admission.",
            ),
        )

    def test_connection(self, configuration, secret):
        return {"ok": Path(configuration.get("root", "")).is_dir(), "mutated_external_data": False}

    def import_records(self, scope, cursor):
        self.require(Capability.IMPORT_RECORDS)
        root = Path(scope["root"])
        records = tuple(
            {"external_id": p.name, "external_version": str(p.stat().st_mtime_ns), "path": str(p)}
            for p in sorted(root.iterdir())
            if p.is_file()
        )
        return records, str(len(records))


class InMemoryWriteAdapter(IntegrationAdapter):
    def __init__(self):
        self.records = {}
        self.calls = 0

    @property
    def manifest(self):
        return AdapterManifest(
            adapter_name="in_memory_write_test",
            adapter_version="1.0.0",
            category="custom",
            supported_record_types=("test",),
            supported_operations=(
                Capability.CONNECTION_TEST,
                Capability.PROPOSE_EXPORT,
                Capability.EXECUTE_APPROVED_EXPORT,
                Capability.RETRIEVE_EXTERNAL_RECORD,
                Capability.RECONCILE_EXPORT,
            ),
            write_capable=True,
            known_limitations=("Test-only; never contacts an external system.",),
        )

    def test_connection(self, configuration, secret):
        return {"ok": True, "mutated_external_data": False}

    def execute_approved_export(self, payload, idempotency_key, expected_version):
        if idempotency_key in self.records:
            return {**self.records[idempotency_key], "replayed": True}
        self.calls += 1
        record = {
            "record_id": payload.get("record_id", f"memory-{self.calls}"),
            "version": str(self.calls),
            "fields": payload,
            "replayed": False,
        }
        self.records[idempotency_key] = record
        return record

    def retrieve_external_record(self, record_id):
        for value in self.records.values():
            if value["record_id"] == record_id:
                return value
        raise KeyError(record_id)
