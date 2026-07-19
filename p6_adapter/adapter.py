"""Primavera P6 adapter transport and capability implementation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from integration_adapters.interfaces import AdapterError, IntegrationAdapter
from integration_adapters.models import AdapterManifest, Capability
from .parser import ParsedP6Source, parse_p6


ALLOWED_EXPORT_FIELDS = frozenset(
    {
        "actual_start",
        "actual_finish",
        "percent_complete",
        "remaining_duration",
        "expected_finish",
        "brunel_reference_note",
    }
)


class PrimaveraP6Adapter(IntegrationAdapter):
    """File-import adapter with an isolated deterministic write transport.

    No Oracle API behavior is claimed. Writes are possible only when the connection
    selects ``test_in_memory`` and the canonical export workflow has approved them.
    """

    def __init__(self):
        self._test_records: dict[str, dict[str, Any]] = {}
        self._idempotency: dict[str, dict[str, Any]] = {}

    @property
    def manifest(self) -> AdapterManifest:
        return AdapterManifest(
            adapter_name="primavera_p6",
            adapter_version="1.0.0",
            category="schedule",
            supported_record_types=(
                "p6_project",
                "schedule_revision",
                "wbs",
                "activity",
                "relationship",
                "calendar",
                "activity_code",
                "udf",
                "resource",
                "baseline",
            ),
            supported_operations=(
                Capability.CONNECTION_TEST,
                Capability.DISCOVER_PROJECTS,
                Capability.IMPORT_RECORDS,
                Capability.IMPORT_SCHEDULE,
                Capability.IMPORT_REVISIONS,
                Capability.IMPORT_XER,
                Capability.IMPORT_P6_XML,
                Capability.PROPOSE_EXPORT,
                Capability.EXECUTE_APPROVED_EXPORT,
                Capability.RETRIEVE_EXTERNAL_RECORD,
                Capability.RECONCILE_EXPORT,
            ),
            write_capable=True,
            incremental_sync=True,
            revisions=True,
            required_configuration=("transport",),
            required_permissions=("project_schedule_import",),
            known_limitations=(
                "XER and P6 XML are file imports; no Oracle API transport is implemented.",
                "External execution is available only through the deterministic test_in_memory transport.",
                "Relationship, constraint, calendar, cost, resource, create, and delete writes are unsupported.",
            ),
        )

    def test_connection(self, configuration, secret):
        transport = configuration.get("transport")
        supported = {"xer_file", "p6_xml_file", "test_in_memory", "future_api"}
        if transport not in supported:
            return {"ok": False, "mutated_external_data": False, "reason": "unsupported_transport"}
        if transport == "future_api":
            return {"ok": False, "mutated_external_data": False, "reason": "not_implemented"}
        return {"ok": True, "mutated_external_data": False, "transport": transport}

    def parse(self, path: Path, *, encoding: str | None = None) -> ParsedP6Source:
        return parse_p6(path, encoding=encoding)

    def discover_projects(self, path: Path, *, encoding: str | None = None):
        return self.parse(path, encoding=encoding).projects

    def import_records(self, scope, cursor):
        self.require(Capability.IMPORT_RECORDS)
        if "file_path" not in scope:
            raise AdapterError("configuration", "P6 file_path import scope is required")
        path = Path(scope["file_path"])
        try:
            source = self.parse(path, encoding=scope.get("encoding"))
        except (ValueError, OSError) as exc:
            raise AdapterError("parsing", str(exc)) from exc
        selected = scope.get("external_project_id")
        projects = tuple(
            p for p in source.projects if selected is None or p.external_project_id == selected
        )
        if selected and not projects:
            raise AdapterError("mapping", "Mapped P6 project is not present in the source")
        payloads = tuple(
            {
                "external_id": p.external_project_id,
                "external_version": source.content_hash,
                "record_type": "p6_schedule_source",
                "target_domain": "schedule",
                "source_format": source.source_format,
                "source_filename": path.name,
                "source_path": str(path.resolve()),
                "content_hash": source.content_hash,
                "parser_version": source.parser_version,
                "project_name": p.name,
                "project_short_name": p.short_name,
                "project_metadata": p.metadata,
                "activity_count": len(p.activities),
                "wbs_count": len(p.wbs),
                "calendar_count": len(p.calendars),
                "relationship_count": len(p.relationships),
                "unsupported_tables": p.unsupported or {},
                "warnings": source.warnings + p.warnings,
            }
            for p in projects
        )
        return payloads, source.content_hash

    def validate_export_payload(self, payload, configuration):
        errors = []
        if configuration.get("transport") != "test_in_memory":
            errors.append("p6_production_write_transport_not_implemented")
        field = payload.get("field")
        if field not in ALLOWED_EXPORT_FIELDS:
            errors.append("unsupported_p6_export_field")
        if not payload.get("record_id"):
            errors.append("confirmed_activity_mapping_required")
        if not payload.get("mapping_id"):
            errors.append("activity_mapping_reference_required")
        if not payload.get("source_revision_id"):
            errors.append("current_source_schedule_revision_required")
        elif payload.get("source_revision_id") != configuration.get("current_source_revision_id"):
            errors.append("p6_source_revision_changed")
        if not payload.get("external_project_id"):
            errors.append("confirmed_p6_project_mapping_required")
        elif payload.get("external_project_id") != configuration.get("external_project_id"):
            errors.append("p6_project_mapping_changed")
        if "value" not in payload:
            errors.append("proposed_value_required")
        return tuple(errors)

    def validate_export_context(self, proposal, connection, repository):
        mapping_id = proposal.proposed_fields.get("mapping_id")
        if not mapping_id:
            return ("activity_mapping_reference_required",)
        mapping = repository.get(
            "mappings", mapping_id, proposal.organization_id, proposal.project_id
        )
        if not mapping:
            return ("activity_mapping_not_found",)
        if (
            mapping.status != "confirmed"
            or mapping.connection_id != connection.id
            or mapping.external_record_id != proposal.proposed_fields.get("record_id")
        ):
            return ("p6_activity_mapping_changed",)
        return ()

    def seed_test_activity(self, record_id: str, fields: dict[str, Any], version: str = "1"):
        self._test_records[record_id] = {
            "record_id": record_id,
            "version": version,
            "fields": dict(fields),
        }

    def execute_approved_export(self, payload, idempotency_key, expected_version):
        if idempotency_key in self._idempotency:
            return {**self._idempotency[idempotency_key], "replayed": True}
        record_id = str(payload["record_id"])
        current = self._test_records.get(record_id)
        if current is None:
            raise AdapterError("stale_target", "P6 test target does not exist")
        if expected_version is None or current["version"] != expected_version:
            raise AdapterError("version_conflict", "Expected P6 activity version does not match")
        updated_fields = dict(current["fields"])
        updated_fields[str(payload["field"])] = payload["value"]
        result = {
            "record_id": record_id,
            "version": str(int(current["version"]) + 1),
            "fields": payload,
            "applied_field": payload["field"],
            "applied_value": payload["value"],
            "replayed": False,
        }
        self._test_records[record_id] = {
            "record_id": record_id,
            "version": result["version"],
            "fields": updated_fields,
        }
        self._idempotency[idempotency_key] = result
        return result

    def retrieve_external_record(self, record_id):
        if record_id not in self._test_records:
            raise AdapterError("not_found", "P6 test target not found")
        current = self._test_records[record_id]
        # Reconciliation compares the approved envelope, retained by the idempotency record.
        execution = next(
            (value for value in self._idempotency.values() if value["record_id"] == record_id), None
        )
        return execution or current
