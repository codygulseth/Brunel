"""P6-specific views over canonical integration and schedule records."""

from datetime import UTC, date, datetime
from pydantic import BaseModel, ConfigDict, Field


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class P6ProjectDiscovery(Frozen):
    connection_id: str
    external_project_id: str
    short_name: str | None = None
    name: str
    data_date: date | None = None
    planned_start: date | None = None
    scheduled_finish: date | None = None
    must_finish_by: date | None = None
    status: str | None = None
    source_format: str
    content_hash: str
    activity_count: int
    requires_mapping_review: bool = True
    warnings: tuple[str, ...] = ()


class P6Dashboard(Frozen):
    organization_id: str
    project_id: str
    connection_id: str
    connection_status: str
    external_project_id: str | None
    adapter_version: str
    latest_import_at: datetime | None = None
    latest_data_date: date | None = None
    latest_schedule_revision_id: str | None = None
    import_warnings: int = 0
    failed_imports: int = 0
    mapping_candidates: int = 0
    unresolved_conflicts: int = 0
    proposals_awaiting_approval: int = 0
    approved_awaiting_execution: int = 0
    reconciliations_requiring_review: int = 0
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class P6Answer(Frozen):
    answer: str
    citations: tuple[dict[str, object], ...] = ()
    limitations: tuple[str, ...] = (
        "Imported P6 values are evidence, not determinations of delay, responsibility, entitlement, or contractual compliance.",
    )
