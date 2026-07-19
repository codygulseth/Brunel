from datetime import UTC, datetime
from hashlib import sha256
import json
from uuid import uuid4
from .interfaces import AdapterError, SecretProvider
from .models import (
    AuditEvent,
    Capability,
    ConnectionStatus,
    ExportExecution,
    ExportProposal,
    ExportStatus,
    ExternalCitation,
    ExternalIdentityMapping,
    ImportSession,
    IntegrationConflict,
    IntegrationConnection,
    IntegrationHealth,
    NormalizedField,
    NormalizedRecord,
    NotificationRequest,
    RawExternalRecord,
    Reconciliation,
    SecretReference,
)
from .registry import AdapterRegistry
from .repository import JsonIntegrationRepository


class IntegrationService:
    def __init__(
        self,
        repository: JsonIntegrationRepository,
        registry: AdapterRegistry,
        secrets: SecretProvider,
    ):
        self.repository = repository
        self.registry = registry
        self.secrets = secrets

    def _hash(self, value: object) -> str:
        return sha256(
            json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()
        ).hexdigest()

    def _proposal_hash(self, proposal: ExportProposal) -> str:
        return self._hash(
            {
                "capability": proposal.target_capability,
                "source_type": proposal.brunel_source_type,
                "source_id": proposal.brunel_source_id,
                "target_record": proposal.target_external_record_id,
                "action": proposal.proposed_action,
                "fields": proposal.proposed_fields,
                "evidence": proposal.evidence,
                "rationale": proposal.human_rationale,
                "expected_version": proposal.expected_external_version,
            }
        )

    def _audit(self, org, event, subject, actor="brunel", project=None, metadata=None):
        safe = {
            k: v
            for k, v in (metadata or {}).items()
            if not any(x in k.casefold() for x in ("secret", "token", "password", "authorization"))
        }
        item = AuditEvent(
            id=f"audit_{uuid4().hex[:16]}",
            organization_id=org,
            project_id=project,
            event_type=event,
            subject_id=subject,
            actor=actor,
            metadata={k: str(v) for k, v in safe.items()},
        )
        self.repository.save("audit", item.id, item)

    def _notify(self, org, event, subject, summary, project=None):
        item = NotificationRequest(
            id=f"out_{uuid4().hex[:16]}",
            organization_id=org,
            project_id=project,
            event_type=event,
            subject_id=subject,
            summary=summary,
        )
        self.repository.save("outbox", item.id, item)

    def _connection(self, org, project, cid):
        value = self.repository.get("connections", cid, org, project)
        if not value:
            raise ValueError("Connection not found in requested organization/project")
        return value

    def _authorize(self, connection, actor, *, external_write=False):
        allowed = (
            connection.external_write_approver_ids
            if external_write
            else connection.authorized_principal_ids
        )
        if actor not in allowed:
            self._audit(
                connection.organization_id,
                "authorization_failure",
                connection.id,
                actor,
                connection.project_id,
            )
            raise PermissionError("Integration operation is not authorized for this project")

    def create_secret_reference(self, org, reference: SecretReference, actor):
        self.repository.save("secrets", reference.id, reference)
        self._audit(org, "secret_reference_assigned", reference.id, actor)
        return reference

    def create_connection(
        self,
        org,
        project,
        adapter_name,
        display_name,
        actor,
        *,
        secret_reference_id=None,
        configuration=None,
        write_enabled=False,
        authorized_principal_ids=None,
        external_write_approver_ids=(),
    ):
        manifest = self.registry.get(adapter_name).manifest
        if write_enabled and not manifest.write_capable:
            raise ValueError("Adapter does not declare write capability")
        if write_enabled and not external_write_approver_ids:
            raise ValueError("Write-enabled connection requires explicit external-write approvers")
        cid = f"connection_{uuid4().hex[:16]}"
        status = (
            ConnectionStatus.READY_FOR_TEST
            if all(x in (configuration or {}) for x in manifest.required_configuration)
            else ConnectionStatus.CONFIGURATION_REQUIRED
        )
        item = IntegrationConnection(
            id=cid,
            organization_id=org,
            project_id=project,
            adapter_name=adapter_name,
            adapter_category=manifest.category,
            display_name=display_name,
            status=status,
            capabilities=manifest.supported_operations,
            secret_reference_id=secret_reference_id,
            configuration=configuration or {},
            write_enabled=write_enabled,
            authorized_principal_ids=tuple(authorized_principal_ids or (actor,)),
            external_write_approver_ids=tuple(external_write_approver_ids),
            created_by=actor,
            synchronization_direction="bidirectional_proposals_only"
            if write_enabled
            else "import_only",
        )
        self.repository.save("connections", cid, item)
        self._audit(org, "connection_created", cid, actor, project)
        return item

    def test_connection(self, org, project, cid, actor):
        connection = self._connection(org, project, cid)
        self._authorize(connection, actor)
        adapter = self.registry.get(connection.adapter_name)
        adapter.require(Capability.CONNECTION_TEST)
        secret = (
            self.secrets.resolve(connection.secret_reference_id)
            if connection.secret_reference_id
            else None
        )
        if connection.secret_reference_id and secret is None:
            raise AdapterError("authentication", "Secret reference unavailable")
        result = adapter.test_connection(connection.configuration, secret)
        if result.get("mutated_external_data"):
            raise AdapterError("validation", "Connection test attempted mutation")
        status = ConnectionStatus.ACTIVE if result.get("ok") else ConnectionStatus.DEGRADED
        updated = connection.model_copy(
            update={
                "status": status,
                "last_successful_test": datetime.now(UTC)
                if result.get("ok")
                else connection.last_successful_test,
                "failure_state": None if result.get("ok") else "connection_test_failed",
            }
        )
        self.repository.save("connections", cid, updated)
        self._audit(org, "connection_test", cid, actor, project, {"ok": result.get("ok")})
        return updated

    def transition_connection(self, org, project, cid, status, actor):
        connection = self._connection(org, project, cid)
        self._authorize(connection, actor)
        if status not in {
            ConnectionStatus.ACTIVE,
            ConnectionStatus.SUSPENDED,
            ConnectionStatus.DISABLED,
        }:
            raise ValueError("Unsupported connection lifecycle transition")
        if status == ConnectionStatus.ACTIVE and connection.last_successful_test is None:
            raise ValueError("Successful non-mutating connection test required")
        updated = connection.model_copy(update={"status": status})
        self.repository.save("connections", cid, updated)
        self._audit(org, f"connection_{status}", cid, actor, project)
        return updated

    def import_records(
        self,
        org,
        project,
        cid,
        actor,
        *,
        scope=None,
        cursor=None,
        defer_domain_admission=False,
    ):
        connection = self._connection(org, project, cid)
        self._authorize(connection, actor)
        if connection.status != ConnectionStatus.ACTIVE:
            raise ValueError("Active connection required")
        adapter = self.registry.get(connection.adapter_name)
        adapter.require(Capability.IMPORT_RECORDS)
        sid = f"import_{uuid4().hex[:16]}"
        session = ImportSession(
            id=sid,
            organization_id=org,
            project_id=project,
            connection_id=cid,
            requested_capability=Capability.IMPORT_RECORDS,
            requested_scope=scope or {},
            cursor_requested=cursor,
            status="running",
        )
        self.repository.save("sessions", sid, session)
        self._audit(org, "import_requested", sid, actor, project)
        try:
            payloads, next_cursor = adapter.import_records(scope or {}, cursor)
        except AdapterError as exc:
            failed = session.model_copy(
                update={
                    "status": "failed",
                    "completed_at": datetime.now(UTC),
                    "errors": (f"{exc.category}: {exc}",),
                }
            )
            self.repository.save("sessions", sid, failed, immutable=True)
            self._notify(
                org, "import_failed", sid, "Import failed; review safe error details", project
            )
            return failed, ()
        normalized = []
        duplicates = 0
        for payload in payloads:
            external_id = str(
                payload.get("external_id") or payload.get("id") or self._hash(payload)[:16]
            )
            version = str(
                payload.get("external_version") or payload.get("version") or self._hash(payload)
            )
            rid = self._hash((cid, external_id, version))
            raw_id = f"raw_{rid[:16]}"
            existing = self.repository.get("raw", raw_id, org, project)
            if existing:
                duplicates += 1
                continue
            raw = RawExternalRecord(
                id=raw_id,
                organization_id=org,
                project_id=project,
                connection_id=cid,
                record_type=str(payload.get("record_type", "generic")),
                external_record_id=external_id,
                external_version=version,
                retrieved_at=datetime.now(UTC),
                content_hash=self._hash(payload),
                payload=payload,
                source_url=payload.get("source_url"),
                import_session_id=sid,
                authorization_scope=(org, project),
            )
            self.repository.save("raw", raw_id, raw, immutable=True)
            self._audit(org, "raw_record_received", raw_id, actor, project)
            fields = []
            citation = ExternalCitation(
                connection_id=cid,
                external_system=connection.adapter_name,
                external_project=connection.external_project,
                record_type=raw.record_type,
                external_record_id=external_id,
                external_revision=version,
                source_timestamp=raw.source_timestamp,
                imported_timestamp=raw.retrieved_at,
                source_url=raw.source_url,
                import_session_id=sid,
            )
            for key, value in payload.items():
                fields.append(
                    NormalizedField(
                        field_name=key,
                        source_field=key,
                        source_value=value,
                        normalized_value=value,
                        transformation="identity",
                        citation=citation,
                    )
                )
            item = NormalizedRecord(
                id=f"normalized_{rid[:16]}",
                organization_id=org,
                project_id=project,
                raw_record_id=raw_id,
                target_domain=str(payload.get("target_domain", "unsupported")),
                fields=tuple(fields),
                unsupported_fields={},
                status="proposed_for_review",
            )
            self.repository.save("normalized", item.id, item)
            normalized.append(item)
            self._audit(org, "record_normalized", item.id, actor, project)
        completed = session.model_copy(
            update={
                "status": "awaiting_domain_admission"
                if defer_domain_admission
                else "completed_with_review_items"
                if normalized
                else "completed",
                "completed_at": None if defer_domain_admission else datetime.now(UTC),
                "raw_records_received": len(payloads) - duplicates,
                "records_normalized": len(normalized),
                "records_requiring_review": len(normalized),
                "duplicates": duplicates,
                "cursor_pending": next_cursor if defer_domain_admission else None,
                "cursor_committed": None if defer_domain_admission else next_cursor,
            }
        )
        self.repository.save("sessions", sid, completed)
        self._notify(
            org,
            "import_completed_with_review_items",
            sid,
            "Imported records await canonical domain admission review",
            project,
        )
        return completed, tuple(normalized)

    def finalize_domain_admission(self, org, project, session_id, actor, admitted_count):
        session = self.repository.get("sessions", session_id, org, project)
        if not session or session.status != "awaiting_domain_admission":
            raise ValueError("Import session is not awaiting canonical domain admission")
        completed = session.model_copy(
            update={
                "status": "completed",
                "completed_at": datetime.now(UTC),
                "cursor_committed": session.cursor_pending,
                "cursor_pending": None,
                "records_admitted": admitted_count,
                "records_requiring_review": max(
                    0, session.records_requiring_review - admitted_count
                ),
            }
        )
        self.repository.save("sessions", session_id, completed)
        self._audit(org, "import_domain_admission_completed", session_id, actor, project)
        return completed

    def confirm_mapping(self, org, project, normalized_id, brunel_type, brunel_id, actor):
        record = self.repository.get("normalized", normalized_id, org, project)
        if not record:
            raise ValueError("Normalized record not found")
        raw = self.repository.get("raw", record.raw_record_id, org, project)
        mid = self._hash((raw.connection_id, raw.external_record_id, brunel_type, brunel_id))[:16]
        mapping = ExternalIdentityMapping(
            id=f"mapping_{mid}",
            organization_id=org,
            project_id=project,
            brunel_record_type=brunel_type,
            brunel_record_id=brunel_id,
            connection_id=raw.connection_id,
            external_record_type=raw.record_type,
            external_record_id=raw.external_record_id,
            external_revision_id=raw.external_version,
            first_seen=raw.retrieved_at,
            latest_seen=raw.retrieved_at,
            last_synchronized_version=raw.external_version,
            status="confirmed",
            confidence=1,
            reviewer_disposition=f"confirmed by {actor}",
        )
        self.repository.save("mappings", mapping.id, mapping)
        self.repository.save(
            "normalized",
            record.id,
            record.model_copy(update={"status": "admitted", "admitted_record_id": brunel_id}),
        )
        self._audit(org, "mapping_confirmation", mapping.id, actor, project)
        return mapping

    def record_external_deletion(self, org, project, raw_id, actor):
        raw = self.repository.get("raw", raw_id, org, project)
        if not raw:
            raise ValueError("Raw external record not found")
        deletion = raw.model_copy(
            update={
                "id": f"{raw.id}_deleted",
                "deleted_externally": True,
                "retrieved_at": datetime.now(UTC),
            }
        )
        self.repository.save("raw", deletion.id, deletion, immutable=True)
        conflict = IntegrationConflict(
            id=f"conflict_{uuid4().hex[:16]}",
            organization_id=org,
            project_id=project,
            connection_id=raw.connection_id,
            conflict_type="external_deletion",
            record_ids=(raw.id, deletion.id),
            conflicting_fields={"external_status": ("present", "deleted")},
        )
        self.repository.save("conflicts", conflict.id, conflict)
        self._audit(org, "deletion_detected", raw.id, actor, project)
        self._notify(
            org,
            "external_deletion_detected",
            conflict.id,
            "External deletion preserved as reviewable history",
            project,
        )
        return conflict

    def review_mapping(self, org, project, mapping_id, decision, actor):
        mapping = self.repository.get("mappings", mapping_id, org, project)
        if not mapping:
            raise ValueError("External identity mapping not found")
        connection = self._connection(org, project, mapping.connection_id)
        self._authorize(connection, actor)
        if decision not in {"confirm", "reject"}:
            raise ValueError("Mapping decision must be confirm or reject")
        updated = mapping.model_copy(
            update={
                "status": "confirmed" if decision == "confirm" else "rejected",
                "confidence": 1 if decision == "confirm" else 0,
                "reviewer_disposition": f"{decision}ed by {actor}",
                "latest_seen": datetime.now(UTC),
            }
        )
        self.repository.save("mappings", mapping_id, updated)
        self._audit(org, f"mapping_{decision}", mapping_id, actor, project)
        return updated

    def review_conflict(self, org, project, conflict_id, disposition, actor):
        conflict = self.repository.get("conflicts", conflict_id, org, project)
        if not conflict:
            raise ValueError("Integration conflict not found")
        connection = self._connection(org, project, conflict.connection_id)
        self._authorize(connection, actor)
        if disposition not in {"acknowledged", "resolved", "dismissed"}:
            raise ValueError("Unsupported integration conflict disposition")
        updated = conflict.model_copy(update={"review_status": disposition})
        self.repository.save("conflicts", conflict_id, updated)
        self._audit(org, "integration_conflict_review", conflict_id, actor, project)
        return updated

    def create_export_proposal(
        self,
        org,
        project,
        cid,
        capability,
        source_type,
        source_id,
        action,
        fields,
        evidence,
        rationale,
        actor,
        expected_version=None,
    ):
        connection = self._connection(org, project, cid)
        self._authorize(connection, actor)
        pid = f"export_{uuid4().hex[:16]}"
        item = ExportProposal(
            id=pid,
            organization_id=org,
            project_id=project,
            connection_id=cid,
            target_capability=capability,
            brunel_source_type=source_type,
            brunel_source_id=source_id,
            proposed_action=action,
            proposed_fields=fields,
            evidence=evidence,
            human_rationale=rationale,
            expected_external_version=expected_version,
            payload_hash="pending",
            idempotency_key="pending",
            status=ExportStatus.VALIDATION_REQUIRED,
        )
        payload_hash = self._proposal_hash(item)
        item = item.model_copy(
            update={
                "payload_hash": payload_hash,
                "idempotency_key": self._hash((cid, capability, source_id, action, payload_hash)),
            }
        )
        self.repository.save("proposals", pid, item)
        self._audit(org, "export_proposal_created", pid, actor, project)
        return item

    def validate_export(self, org, project, pid, actor):
        proposal = self.repository.get("proposals", pid, org, project)
        if not proposal:
            raise ValueError("Export proposal not found")
        connection = self._connection(org, project, proposal.connection_id)
        self._authorize(connection, actor)
        adapter = self.registry.get(connection.adapter_name)
        errors = []
        if connection.status != ConnectionStatus.ACTIVE:
            errors.append("connection_not_active")
        if not connection.write_enabled:
            errors.append("connection_read_only")
        if (
            not adapter.manifest.write_capable
            or proposal.target_capability not in adapter.manifest.supported_operations
        ):
            errors.append("unsupported_write_capability")
        if not proposal.evidence:
            errors.append("source_evidence_required")
        errors.extend(
            adapter.validate_export_payload(proposal.proposed_fields, connection.configuration)
        )
        errors.extend(adapter.validate_export_context(proposal, connection, self.repository))
        status = ExportStatus.READY_FOR_REVIEW if not errors else ExportStatus.VALIDATION_REQUIRED
        updated = proposal.model_copy(update={"status": status, "validation_errors": tuple(errors)})
        self.repository.save("proposals", pid, updated)
        self._audit(org, "export_validation", pid, actor, project, {"valid": not errors})
        return updated

    def approve_export(self, org, project, pid, actor, rationale, expires_at):
        proposal = self.repository.get("proposals", pid, org, project)
        if not proposal or proposal.status != ExportStatus.READY_FOR_REVIEW:
            raise ValueError("Validated export proposal required")
        connection = self._connection(org, project, proposal.connection_id)
        self._authorize(connection, actor, external_write=True)
        updated = proposal.model_copy(
            update={
                "status": ExportStatus.APPROVED,
                "reviewer": actor,
                "approved_at": datetime.now(UTC),
                "approved_payload_hash": proposal.payload_hash,
                "approval_rationale": rationale,
                "expires_at": expires_at,
            }
        )
        self.repository.save("proposals", pid, updated)
        self._audit(org, "export_approval", pid, actor, project)
        return updated

    def reject_export(self, org, project, pid, actor, rationale):
        proposal = self.repository.get("proposals", pid, org, project)
        if not proposal or proposal.status not in {
            ExportStatus.VALIDATION_REQUIRED,
            ExportStatus.READY_FOR_REVIEW,
            ExportStatus.APPROVED,
        }:
            raise ValueError("Reviewable export proposal required")
        connection = self._connection(org, project, proposal.connection_id)
        self._authorize(connection, actor, external_write=True)
        updated = proposal.model_copy(
            update={
                "status": ExportStatus.REJECTED,
                "reviewer": actor,
                "approval_rationale": rationale,
            }
        )
        self.repository.save("proposals", pid, updated)
        self._audit(org, "export_rejection", pid, actor, project)
        return updated

    def execute_export(self, org, project, pid, actor):
        proposal = self.repository.get("proposals", pid, org, project)
        if proposal:
            connection = self._connection(org, project, proposal.connection_id)
            self._authorize(connection, actor, external_write=True)
            previous = next(
                (
                    x
                    for x in self.repository.list("executions", org, project)
                    if x.idempotency_key == proposal.idempotency_key and x.status == "executed"
                ),
                None,
            )
            if previous:
                return previous.model_copy(update={"replayed": True})
        if not proposal or proposal.status != ExportStatus.APPROVED:
            raise ValueError("Explicitly approved export proposal required")
        if proposal.expires_at and proposal.expires_at <= datetime.now(UTC):
            raise ValueError("Export approval expired")
        if proposal.approved_payload_hash != self._proposal_hash(proposal):
            raise ValueError("Approval invalidated by payload change")
        connection = self._connection(org, project, proposal.connection_id)
        adapter = self.registry.get(connection.adapter_name)
        if connection.status != ConnectionStatus.ACTIVE or not connection.write_enabled:
            raise ValueError("Active explicitly write-enabled connection required")
        errors = adapter.validate_export_payload(proposal.proposed_fields, connection.configuration)
        errors += adapter.validate_export_context(proposal, connection, self.repository)
        if errors:
            raise ValueError("Export proposal is no longer valid: " + ", ".join(errors))
        adapter.require(Capability.EXECUTE_APPROVED_EXPORT)
        response = adapter.execute_approved_export(
            proposal.proposed_fields, proposal.idempotency_key, proposal.expected_external_version
        )
        execution = ExportExecution(
            id=f"execution_{uuid4().hex[:16]}",
            organization_id=org,
            project_id=project,
            proposal_id=pid,
            idempotency_key=proposal.idempotency_key,
            request_metadata={
                "adapter": connection.adapter_name,
                "payload_hash": proposal.payload_hash,
            },
            external_record_id=response.get("record_id"),
            external_version=response.get("version"),
            response_metadata={
                k: v for k, v in response.items() if k not in {"token", "secret", "authorization"}
            },
            status="executed",
            replayed=bool(response.get("replayed")),
        )
        self.repository.save("executions", execution.id, execution, immutable=True)
        self.repository.save(
            "proposals",
            pid,
            proposal.model_copy(update={"status": ExportStatus.RECONCILIATION_REQUIRED}),
        )
        self._audit(org, "export_execution", execution.id, actor, project)
        return execution

    def reconcile(self, org, project, pid, execution_id, actor):
        proposal = self.repository.get("proposals", pid, org, project)
        execution = self.repository.get("executions", execution_id, org, project)
        if not proposal or not execution:
            raise ValueError("Proposal and execution required")
        connection = self._connection(org, project, proposal.connection_id)
        self._authorize(connection, actor, external_write=True)
        adapter = self.registry.get(connection.adapter_name)
        actual = adapter.retrieve_external_record(execution.external_record_id)
        actual_fields = actual.get("fields", {})
        differences = {
            k: (v, actual_fields.get(k))
            for k, v in proposal.proposed_fields.items()
            if actual_fields.get(k) != v
        }
        status = "matched" if not differences else "partial_match"
        result = Reconciliation(
            id=f"reconcile_{uuid4().hex[:16]}",
            organization_id=org,
            project_id=project,
            proposal_id=pid,
            execution_id=execution_id,
            status=status,
            intended_fields=proposal.proposed_fields,
            actual_fields=actual_fields,
            differences=differences,
            reviewed_required=bool(differences),
        )
        self.repository.save("reconciliations", result.id, result, immutable=True)
        self._audit(org, "export_reconciliation", result.id, actor, project)
        return result

    def health(self, org, project=None):
        connections = self.repository.list("connections", org, project)
        sessions = self.repository.list("sessions", org, project)
        proposals = self.repository.list("proposals", org, project)
        reconciliations = self.repository.list("reconciliations", org, project)
        return IntegrationHealth(
            organization_id=org,
            project_id=project,
            connections=len(connections),
            active=sum(x.status == ConnectionStatus.ACTIVE for x in connections),
            degraded=sum(x.status == ConnectionStatus.DEGRADED for x in connections),
            failed_sessions=sum(x.status == "failed" for x in sessions),
            unresolved_conflicts=sum(
                x.review_status == "proposed"
                for x in self.repository.list("conflicts", org, project)
            ),
            proposals_awaiting_approval=sum(
                x.status == ExportStatus.READY_FOR_REVIEW for x in proposals
            ),
            reconciliations_requiring_review=sum(x.reviewed_required for x in reconciliations),
        )
