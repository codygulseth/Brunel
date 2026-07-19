from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SharingLevel(StrEnum):
    PROJECT_ONLY = "project_only"
    PORTFOLIO_SHARED = "portfolio_shared"
    ORGANIZATION_SHARED = "organization_shared"
    BENCHMARK_ONLY = "benchmark_only_anonymized"
    RESTRICTED = "restricted"


class ReviewStatus(StrEnum):
    PROPOSED = "proposed"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class Evidence(Frozen):
    project_id: str
    record_type: str
    record_id: str
    citation: dict[str, Any]
    excerpt: str
    recorded_on: date | None = None
    confidentiality: SharingLevel = SharingLevel.PROJECT_ONLY


class ProjectMembership(Frozen):
    project_id: str
    project_status: str
    sharing_level: SharingLevel
    benchmark_eligible: bool = False
    taxonomy: dict[str, str] = {}
    authorized_principal_ids: tuple[str, ...] = ()
    evidence: tuple[Evidence, ...] = ()


class Portfolio(Frozen):
    id: str
    organization_id: str
    name: str
    members: tuple[ProjectMembership, ...] = ()
    authorized_principal_ids: tuple[str, ...] = ()
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TaxonomyMapping(Frozen):
    id: str
    organization_id: str
    project_id: str
    original_metadata: dict[str, str]
    normalized_values: dict[str, str]
    mapping_method: str
    confidence: float = Field(ge=0, le=1)
    uncertainty: tuple[str, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    review_status: ReviewStatus = ReviewStatus.PROPOSED
    reviewer: str | None = None


class EnterpriseEntity(Frozen):
    id: str
    organization_id: str
    entity_type: str
    canonical_name: str
    aliases: tuple[str, ...] = ()
    external_ids: dict[str, str] = {}
    review_status: ReviewStatus = ReviewStatus.PROPOSED
    evidence: tuple[Evidence, ...] = ()


class EntityMatchCandidate(Frozen):
    id: str
    organization_id: str
    left_entity_id: str
    right_entity_id: str
    signals: tuple[str, ...]
    confidence: float = Field(ge=0, le=1)
    exact_identifier_match: bool = False
    auto_merged: bool = False
    review_status: ReviewStatus = ReviewStatus.PROPOSED


class Lesson(Frozen):
    id: str
    organization_id: str
    source_project_id: str
    title: str
    original_source_wording: str
    normalized_lesson: str
    project_context: dict[str, str]
    related_system_or_trade: str | None = None
    outcome_as_recorded: str | None = None
    recommendation_as_recorded: str | None = None
    proposed_reusable_guidance: str | None = None
    confidence: float = Field(ge=0, le=1)
    uncertainty: tuple[str, ...]
    evidence: tuple[Evidence, ...]
    approved_for_enterprise_reuse: bool = False
    review_status: ReviewStatus = ReviewStatus.PROPOSED


class MetricRecord(Frozen):
    id: str
    organization_id: str
    project_id: str
    metric_name: str
    value: float
    unit: str
    occurred_on: date
    dimensions: dict[str, str] = {}
    input_record_ids: tuple[str, ...]
    citations: tuple[Evidence, ...]
    calculation_version: str = "enterprise-metric-1"
    inclusion_rule: str = "reviewed canonical record"
    exclusion_rule: str = "missing or incompatible evidence"
    missing_data_treatment: str = "exclude; never impute silently"
    review_status: ReviewStatus = ReviewStatus.PROPOSED


class BenchmarkDefinition(Frozen):
    id: str
    organization_id: str
    name: str
    description: str
    metric_name: str
    unit: str
    eligible_project_criteria: dict[str, str] = {}
    eligible_record_criteria: dict[str, str] = {}
    exclusions: tuple[str, ...] = ()
    grouping_dimensions: tuple[str, ...] = ()
    aggregation_method: str = "median"
    minimum_sample_size: int = Field(default=4, ge=2)
    minimum_group_size: int = Field(default=3, ge=2)
    calculation_version: str = "benchmark-1"
    review_status: ReviewStatus = ReviewStatus.PROPOSED
    reviewer: str | None = None


class MetricProvenance(Frozen):
    metric_definition_id: str
    calculation_version: str
    included_record_ids: tuple[str, ...]
    excluded_record_ids: tuple[str, ...]
    source_project_ids: tuple[str, ...]
    authorized_citations: tuple[Evidence, ...]
    inclusion_rules: tuple[str, ...]
    exclusion_rules: tuple[str, ...]
    missing_data_treatment: str
    calculation_timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class BenchmarkResult(Frozen):
    id: str
    organization_id: str
    portfolio_id: str
    definition_id: str
    value: float | None
    unit: str
    sample_size: int
    source_project_count: int
    date_range: tuple[date, date] | None
    distribution: dict[str, float] = {}
    suppressed: bool = False
    calculation_explanation: str
    confidence: str
    limitations: tuple[str, ...]
    provenance: MetricProvenance


class ComparableProject(Frozen):
    project_id: str
    matching_attributes: tuple[str, ...]
    nonmatching_attributes: tuple[str, ...]
    missing_attributes: tuple[str, ...]
    confidence: float = Field(ge=0, le=1)
    human_review_required: bool = True


class ComparableSelection(Frozen):
    id: str
    organization_id: str
    target_project_id: str
    results: tuple[ComparableProject, ...]
    criteria: tuple[str, ...]
    review_status: ReviewStatus = ReviewStatus.PROPOSED


class DataQualityAssessment(Frozen):
    id: str
    organization_id: str
    project_id: str
    status: str
    findings: tuple[str, ...]
    eligible: bool
    assessed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AuditEvent(Frozen):
    id: str
    organization_id: str
    event_type: str
    subject_id: str
    actor: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class NotificationRequest(Frozen):
    id: str
    organization_id: str
    event_type: str
    subject_id: str
    summary: str
    status: str = "queued_local_only"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EnterpriseDashboard(Frozen):
    organization_id: str
    projects: int
    benchmark_eligible: int
    restricted_projects: int
    taxonomy_review_required: int
    lessons_awaiting_review: int
    entity_matches_awaiting_review: int
    benchmark_definitions_awaiting_review: int
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
