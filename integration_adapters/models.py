from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Capability(StrEnum):
    CONNECTION_TEST = "connection_test"
    DISCOVER_PROJECTS = "discover_projects"
    IMPORT_DOCUMENTS = "import_documents"
    IMPORT_RECORDS = "import_records"
    IMPORT_REVISIONS = "import_revisions"
    IMPORT_ATTACHMENTS = "import_attachments"
    IMPORT_SCHEDULE = "import_schedule"
    IMPORT_CORRESPONDENCE = "import_correspondence"
    IMPORT_PHOTOS = "import_photos"
    IMPORT_USERS = "import_users"
    PROPOSE_EXPORT = "propose_export"
    EXECUTE_APPROVED_EXPORT = "execute_approved_export"
    RECONCILE_EXPORT = "reconcile_export"
    RETRIEVE_EXTERNAL_RECORD = "retrieve_external_record"
    LIST_CHANGES = "list_changes_since_cursor"
    IMPORT_XER = "import_xer"
    IMPORT_P6_XML = "import_p6_xml"
    API_READ = "api_read"
    API_WRITE = "api_write"
    SECURE_FILE_EXPORT = "secure_file_export"


class ConnectionStatus(StrEnum):
    PROPOSED = "proposed"
    CONFIGURATION_REQUIRED = "configuration_required"
    AUTHENTICATION_REQUIRED = "authentication_required"
    READY_FOR_TEST = "ready_for_test"
    ACTIVE = "active"
    DEGRADED = "degraded"
    SUSPENDED = "suspended"
    DISABLED = "disabled"
    REVOKED = "revoked"


class ExportStatus(StrEnum):
    DRAFT = "draft"
    VALIDATION_REQUIRED = "validation_required"
    READY_FOR_REVIEW = "ready_for_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    EXECUTING = "executing"
    EXECUTED = "executed"
    FAILED = "failed"
    RECONCILIATION_REQUIRED = "reconciliation_required"
    SUPERSEDED = "superseded"
    WITHDRAWN = "withdrawn"


class AdapterManifest(Frozen):
    adapter_name: str
    adapter_version: str
    category: str
    supported_record_types: tuple[str, ...]
    supported_operations: tuple[Capability, ...]
    write_capable: bool = False
    pagination: bool = False
    incremental_sync: bool = False
    webhooks: bool = False
    attachments: bool = False
    revisions: bool = False
    delete_events: bool = False
    idempotency: bool = True
    known_limitations: tuple[str, ...] = ()
    required_configuration: tuple[str, ...] = ()
    required_permissions: tuple[str, ...] = ()


class SecretReference(Frozen):
    id: str
    provider_type: str
    credential_purpose: str
    external_tenant: str | None = None
    expires_at: datetime | None = None
    rotation_status: str = "unknown"
    last_validated_at: datetime | None = None
    authorization_scope: tuple[str, ...] = ()


class IntegrationConnection(Frozen):
    id: str
    organization_id: str
    project_id: str | None = None
    adapter_name: str
    adapter_category: str
    external_tenant: str | None = None
    external_project: str | None = None
    environment: str = "test"
    display_name: str
    status: ConnectionStatus = ConnectionStatus.PROPOSED
    capabilities: tuple[Capability, ...] = ()
    synchronization_direction: str = "import_only"
    secret_reference_id: str | None = None
    configuration: dict[str, str] = {}
    write_enabled: bool = False
    authorized_principal_ids: tuple[str, ...] = ()
    external_write_approver_ids: tuple[str, ...] = ()
    created_by: str
    reviewed_by: str | None = None
    last_successful_test: datetime | None = None
    last_successful_import: datetime | None = None
    last_successful_export: datetime | None = None
    failure_state: str | None = None


class ExternalCitation(Frozen):
    connection_id: str
    external_system: str
    external_project: str | None
    record_type: str
    external_record_id: str
    external_revision: str | None = None
    source_timestamp: datetime | None = None
    imported_timestamp: datetime
    source_url: str | None = None
    field_path: str | None = None
    text_span: str | None = None
    attachment_id: str | None = None
    page: int | None = None
    visual_region: tuple[float, float, float, float] | None = None
    import_session_id: str


class RawExternalRecord(Frozen):
    id: str
    organization_id: str
    project_id: str
    connection_id: str
    record_type: str
    external_record_id: str
    external_version: str
    retrieved_at: datetime
    source_timestamp: datetime | None = None
    content_hash: str
    payload: dict[str, Any]
    source_url: str | None = None
    import_session_id: str
    authorization_scope: tuple[str, ...]
    deleted_externally: bool = False


class NormalizedField(Frozen):
    field_name: str
    source_field: str
    source_value: Any
    normalized_value: Any
    transformation: str
    uncertainty: tuple[str, ...] = ()
    citation: ExternalCitation
    validation_status: str = "valid"


class NormalizedRecord(Frozen):
    id: str
    organization_id: str
    project_id: str
    raw_record_id: str
    target_domain: str
    fields: tuple[NormalizedField, ...]
    unsupported_fields: dict[str, Any] = {}
    status: str = "proposed_for_review"
    conflicts: tuple[str, ...] = ()
    admitted_record_id: str | None = None


class ImportSession(Frozen):
    id: str
    organization_id: str
    project_id: str
    connection_id: str
    requested_capability: Capability
    requested_scope: dict[str, str] = {}
    cursor_requested: str | None = None
    cursor_pending: str | None = None
    cursor_committed: str | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    status: str = "requested"
    raw_records_received: int = 0
    records_normalized: int = 0
    records_admitted: int = 0
    records_rejected: int = 0
    records_requiring_review: int = 0
    duplicates: int = 0
    conflicts: int = 0
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()


class ExternalIdentityMapping(Frozen):
    id: str
    organization_id: str
    project_id: str
    brunel_record_type: str
    brunel_record_id: str
    connection_id: str
    external_record_type: str
    external_record_id: str
    external_revision_id: str | None = None
    first_seen: datetime
    latest_seen: datetime
    last_synchronized_version: str | None = None
    status: str = "proposed"
    mapping_method: str = "exact_external_id"
    confidence: float = Field(ge=0, le=1)
    reviewer_disposition: str | None = None


class IntegrationConflict(Frozen):
    id: str
    organization_id: str
    project_id: str
    connection_id: str
    conflict_type: str
    record_ids: tuple[str, ...]
    conflicting_fields: dict[str, tuple[Any, Any]]
    citations: tuple[ExternalCitation, ...] = ()
    severity_proposal: str = "moderate"
    uncertainty: tuple[str, ...] = ("Conflict requires human review; no silent resolution.",)
    review_status: str = "proposed"


class ExportProposal(Frozen):
    id: str
    organization_id: str
    project_id: str
    connection_id: str
    target_capability: Capability
    brunel_source_type: str
    brunel_source_id: str
    target_external_record_id: str | None = None
    proposed_action: str
    proposed_fields: dict[str, Any]
    evidence: tuple[dict[str, Any], ...]
    human_rationale: str
    expected_external_version: str | None = None
    payload_hash: str
    idempotency_key: str
    status: ExportStatus = ExportStatus.DRAFT
    validation_errors: tuple[str, ...] = ()
    reviewer: str | None = None
    approved_at: datetime | None = None
    approved_payload_hash: str | None = None
    approval_rationale: str | None = None
    expires_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ExportExecution(Frozen):
    id: str
    organization_id: str
    project_id: str
    proposal_id: str
    idempotency_key: str
    request_metadata: dict[str, str]
    external_record_id: str | None = None
    external_version: str | None = None
    response_metadata: dict[str, Any] = {}
    status: str
    executed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    replayed: bool = False


class Reconciliation(Frozen):
    id: str
    organization_id: str
    project_id: str
    proposal_id: str
    execution_id: str
    status: str
    intended_fields: dict[str, Any]
    actual_fields: dict[str, Any]
    differences: dict[str, tuple[Any, Any]] = {}
    reviewed_required: bool = True
    reconciled_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AuditEvent(Frozen):
    id: str
    organization_id: str
    project_id: str | None = None
    event_type: str
    subject_id: str
    actor: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, str] = {}


class NotificationRequest(Frozen):
    id: str
    organization_id: str
    project_id: str | None = None
    event_type: str
    subject_id: str
    summary: str
    status: str = "queued_local_only"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class IntegrationHealth(Frozen):
    organization_id: str
    project_id: str | None
    connections: int
    active: int
    degraded: int
    failed_sessions: int
    unresolved_conflicts: int
    proposals_awaiting_approval: int
    reconciliations_requiring_review: int
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
