from datetime import date
from hashlib import sha256
from statistics import mean, median
from uuid import uuid4
from .models import (
    AuditEvent,
    BenchmarkDefinition,
    BenchmarkResult,
    ComparableProject,
    ComparableSelection,
    DataQualityAssessment,
    EnterpriseDashboard,
    EnterpriseEntity,
    EntityMatchCandidate,
    Evidence,
    Lesson,
    MetricProvenance,
    MetricRecord,
    NotificationRequest,
    Portfolio,
    ProjectMembership,
    ReviewStatus,
    SharingLevel,
    TaxonomyMapping,
)
from .repository import JsonEnterpriseRepository


class EnterpriseIntelligenceService:
    def __init__(self, repository: JsonEnterpriseRepository):
        self.repository = repository

    def _id(self, prefix: str, *parts: str) -> str:
        return f"{prefix}_{sha256('|'.join(parts).encode()).hexdigest()[:16]}"

    def _audit(self, org: str, event: str, subject: str, actor: str = "brunel") -> None:
        value = AuditEvent(
            id=f"audit_{uuid4().hex[:16]}",
            organization_id=org,
            event_type=event,
            subject_id=subject,
            actor=actor,
        )
        self.repository.save("audit", value.id, value)

    def _notify(self, org: str, event: str, subject: str, summary: str) -> None:
        value = NotificationRequest(
            id=f"out_{uuid4().hex[:16]}",
            organization_id=org,
            event_type=event,
            subject_id=subject,
            summary=summary,
        )
        self.repository.save("outbox", value.id, value)

    def _portfolio(self, org: str, pid: str) -> Portfolio:
        value = self.repository.get("portfolios", pid, org)
        if not value:
            raise ValueError("Portfolio not found in requested organization")
        return value

    def authorize(
        self, org: str, portfolio_id: str, principal_id: str, project_id: str | None = None
    ) -> Portfolio:
        portfolio = self._portfolio(org, portfolio_id)
        if principal_id not in portfolio.authorized_principal_ids:
            raise PermissionError("Enterprise portfolio access denied")
        if project_id:
            member = next((x for x in portfolio.members if x.project_id == project_id), None)
            if member is None or principal_id not in member.authorized_principal_ids:
                raise PermissionError("Project evidence access denied")
        return portfolio

    def create_portfolio(
        self, org: str, name: str, principal_ids: tuple[str, ...], actor: str
    ) -> Portfolio:
        pid = self._id("portfolio", org, name)
        value = Portfolio(
            id=pid, organization_id=org, name=name, authorized_principal_ids=principal_ids
        )
        self.repository.save("portfolios", pid, value)
        self._audit(org, "portfolio_created", pid, actor)
        return value

    def add_project(
        self,
        org: str,
        portfolio_id: str,
        project_id: str,
        principal_ids: tuple[str, ...],
        sharing: SharingLevel,
        actor: str,
        *,
        taxonomy: dict[str, str] | None = None,
        eligible: bool = False,
    ) -> Portfolio:
        value = self._portfolio(org, portfolio_id)
        if any(x.project_id == project_id for x in value.members):
            raise ValueError("Project already belongs to portfolio")
        member = ProjectMembership(
            project_id=project_id,
            project_status="active",
            sharing_level=sharing,
            benchmark_eligible=eligible,
            taxonomy=taxonomy or {},
            authorized_principal_ids=principal_ids,
        )
        updated = value.model_copy(update={"members": value.members + (member,)})
        self.repository.save("portfolios", value.id, updated)
        self._audit(org, "project_membership_added", project_id, actor)
        return updated

    def map_taxonomy(
        self,
        org: str,
        project_id: str,
        original: dict[str, str],
        normalized: dict[str, str],
        evidence: tuple[Evidence, ...],
        actor: str,
    ) -> TaxonomyMapping:
        confidence = (
            1.0 if all(value in original.values() for value in normalized.values()) else 0.6
        )
        mapping = TaxonomyMapping(
            id=self._id("taxonomy", org, project_id),
            organization_id=org,
            project_id=project_id,
            original_metadata=original,
            normalized_values=normalized,
            mapping_method="exact" if confidence == 1 else "deterministic_candidate",
            confidence=confidence,
            uncertainty=()
            if confidence == 1
            else ("Ambiguous taxonomy mapping requires human review.",),
            evidence=evidence,
        )
        self.repository.save("taxonomy", mapping.id, mapping)
        self._audit(org, "taxonomy_mapping", mapping.id, actor)
        return mapping

    def create_entity(
        self,
        org: str,
        entity_type: str,
        name: str,
        evidence: tuple[Evidence, ...],
        *,
        external_ids: dict[str, str] | None = None,
    ) -> EnterpriseEntity:
        eid = f"entity_{uuid4().hex[:16]}"
        value = EnterpriseEntity(
            id=eid,
            organization_id=org,
            entity_type=entity_type,
            canonical_name=name,
            external_ids=external_ids or {},
            evidence=evidence,
        )
        self.repository.save("entities", eid, value)
        self._audit(org, "entity_candidate_created", eid)
        return value

    def propose_entity_match(self, org: str, left_id: str, right_id: str) -> EntityMatchCandidate:
        left = self.repository.get("entities", left_id, org)
        right = self.repository.get("entities", right_id, org)
        if not left or not right:
            raise ValueError("Enterprise entity not found in organization")
        shared_ids = set(left.external_ids.items()) & set(right.external_ids.items())
        exact_name = left.canonical_name.casefold() == right.canonical_name.casefold()
        confidence = 0.98 if shared_ids else 0.85 if exact_name else 0.35
        signals = (
            ("shared external identifier",)
            if shared_ids
            else ("exact normalized name",)
            if exact_name
            else ("weak name similarity requires human review",)
        )
        mid = self._id("match", org, left_id, right_id)
        value = EntityMatchCandidate(
            id=mid,
            organization_id=org,
            left_entity_id=left_id,
            right_entity_id=right_id,
            signals=signals,
            confidence=confidence,
            exact_identifier_match=bool(shared_ids),
            auto_merged=False,
        )
        self.repository.save("entity_matches", mid, value)
        self._audit(org, "entity_match_candidate", mid)
        return value

    def review_entity_match(
        self, org: str, match_id: str, accept: bool, actor: str
    ) -> EntityMatchCandidate:
        value = self.repository.get("entity_matches", match_id, org)
        if not value:
            raise ValueError("Entity match not found")
        updated = value.model_copy(
            update={
                "review_status": ReviewStatus.APPROVED if accept else ReviewStatus.REJECTED,
                "auto_merged": False,
            }
        )
        self.repository.save("entity_matches", match_id, updated)
        self._audit(org, "entity_match_review", match_id, actor)
        return updated

    def propose_lesson(
        self,
        org: str,
        project_id: str,
        title: str,
        wording: str,
        evidence: tuple[Evidence, ...],
        context: dict[str, str],
    ) -> Lesson:
        lid = f"lesson_{uuid4().hex[:16]}"
        value = Lesson(
            id=lid,
            organization_id=org,
            source_project_id=project_id,
            title=title,
            original_source_wording=wording,
            normalized_lesson=wording.strip(),
            project_context=context,
            confidence=0.6,
            uncertainty=(
                "Historical correlation is not causation; lesson requires human approval for reuse.",
            ),
            evidence=evidence,
        )
        self.repository.save("lessons", lid, value)
        self._audit(org, "lesson_generated", lid)
        self._notify(org, "lesson_awaiting_approval", lid, title)
        return value

    def review_lesson(self, org: str, lesson_id: str, accept: bool, actor: str) -> Lesson:
        value = self.repository.get("lessons", lesson_id, org)
        if not value:
            raise ValueError("Lesson not found")
        updated = value.model_copy(
            update={
                "approved_for_enterprise_reuse": accept,
                "review_status": ReviewStatus.APPROVED if accept else ReviewStatus.REJECTED,
            }
        )
        self.repository.save("lessons", lesson_id, updated)
        self._audit(org, "lesson_review", lesson_id, actor)
        return updated

    def lesson_applicability(self, lesson: Lesson, current: dict[str, str]) -> dict[str, object]:
        keys = set(lesson.project_context) & set(current)
        matches = [k for k in keys if lesson.project_context[k] == current[k]]
        missing = [k for k in lesson.project_context if k not in current]
        ratio = len(matches) / max(len(keys), 1)
        label = (
            "likely_relevant_for_review"
            if ratio >= 0.75
            else "potentially_relevant"
            if ratio >= 0.4
            else "not_enough_evidence"
        )
        return {
            "classification": label,
            "matching_attributes": matches,
            "missing_attributes": missing,
            "confidence": round(ratio, 2),
            "human_review_required": True,
        }

    def add_metric(
        self,
        org: str,
        project_id: str,
        name: str,
        value: float,
        unit: str,
        on: date,
        evidence: tuple[Evidence, ...],
        dimensions: dict[str, str],
        actor: str,
    ) -> MetricRecord:
        if not evidence or any(x.project_id != project_id for x in evidence):
            raise ValueError("Metric requires project-matched citations")
        mid = f"metric_{uuid4().hex[:16]}"
        item = MetricRecord(
            id=mid,
            organization_id=org,
            project_id=project_id,
            metric_name=name,
            value=value,
            unit=unit,
            occurred_on=on,
            dimensions=dimensions,
            input_record_ids=tuple(x.record_id for x in evidence),
            citations=evidence,
        )
        self.repository.save("metrics", mid, item)
        self._audit(org, "metric_recorded", mid, actor)
        return item

    def create_benchmark_definition(
        self,
        org: str,
        name: str,
        metric_name: str,
        unit: str,
        method: str,
        min_sample: int,
        actor: str,
        criteria: dict[str, str] | None = None,
        minimum_group_size: int = 3,
    ) -> BenchmarkDefinition:
        bid = self._id("benchmark_definition", org, name)
        item = BenchmarkDefinition(
            id=bid,
            organization_id=org,
            name=name,
            description=f"Reviewed {metric_name} benchmark",
            metric_name=metric_name,
            unit=unit,
            eligible_record_criteria=criteria or {},
            aggregation_method=method,
            minimum_sample_size=min_sample,
            minimum_group_size=minimum_group_size,
        )
        self.repository.save("benchmark_definitions", bid, item)
        self._audit(org, "benchmark_definition_created", bid, actor)
        return item

    def review_benchmark_definition(
        self, org: str, definition_id: str, actor: str
    ) -> BenchmarkDefinition:
        value = self.repository.get("benchmark_definitions", definition_id, org)
        if not value:
            raise ValueError("Benchmark definition not found")
        updated = value.model_copy(
            update={"review_status": ReviewStatus.APPROVED, "reviewer": actor}
        )
        self.repository.save("benchmark_definitions", definition_id, updated)
        self._audit(org, "benchmark_definition_approved", definition_id, actor)
        return updated

    def calculate_benchmark(
        self, org: str, definition_id: str, portfolio_id: str, principal_id: str
    ) -> BenchmarkResult:
        definition = self.repository.get("benchmark_definitions", definition_id, org)
        if not definition or definition.review_status != ReviewStatus.APPROVED:
            raise ValueError("Approved benchmark definition required")
        portfolio = self.authorize(org, portfolio_id, principal_id)
        eligible_members = tuple(
            member
            for member in portfolio.members
            if member.benchmark_eligible and member.sharing_level != SharingLevel.RESTRICTED
        )
        eligible_projects = {member.project_id for member in eligible_members}
        records = [
            x
            for x in self.repository.list("metrics", org)
            if x.metric_name == definition.metric_name
            and x.project_id in eligible_projects
            and all(
                x.dimensions.get(k) == v for k, v in definition.eligible_record_criteria.items()
            )
        ]
        values = sorted(x.value for x in records)
        sample = len(values)
        projects = tuple(sorted({x.project_id for x in records}))
        suppressed = (
            sample < definition.minimum_sample_size or len(projects) < definition.minimum_group_size
        )
        result_value = (
            None
            if suppressed
            else median(values)
            if definition.aggregation_method == "median"
            else mean(values)
            if definition.aggregation_method == "average"
            else sum(values)
        )
        distribution = (
            {}
            if suppressed
            else {
                "minimum": min(values),
                "maximum": max(values),
                "median": median(values),
                "average": mean(values),
            }
        )
        dates = [x.occurred_on for x in records]
        contributing_members = tuple(
            member for member in eligible_members if member.project_id in projects
        )
        full_provenance_authorized = all(
            principal_id in member.authorized_principal_ids
            and member.sharing_level != SharingLevel.BENCHMARK_ONLY
            for member in contributing_members
        )
        citations = tuple(
            c
            for record in records
            for c in record.citations
            if c.confidentiality
            in {
                SharingLevel.ORGANIZATION_SHARED,
                SharingLevel.PORTFOLIO_SHARED,
                SharingLevel.BENCHMARK_ONLY,
            }
        )
        provenance = MetricProvenance(
            metric_definition_id=definition.id,
            calculation_version=definition.calculation_version,
            included_record_ids=(
                tuple(x.id for x in records)
                if full_provenance_authorized and not suppressed
                else ()
            ),
            excluded_record_ids=(),
            source_project_ids=projects if full_provenance_authorized and not suppressed else (),
            authorized_citations=citations if full_provenance_authorized and not suppressed else (),
            inclusion_rules=(str(definition.eligible_record_criteria),),
            exclusion_rules=definition.exclusions,
            missing_data_treatment="exclude; never impute",
        )
        rid = f"benchmark_{uuid4().hex[:16]}"
        result = BenchmarkResult(
            id=rid,
            organization_id=org,
            portfolio_id=portfolio_id,
            definition_id=definition.id,
            value=result_value,
            unit=definition.unit,
            sample_size=sample,
            source_project_count=len(projects),
            date_range=(min(dates), max(dates)) if dates else None,
            distribution=distribution,
            suppressed=suppressed,
            calculation_explanation=f"{definition.aggregation_method} using {sample} cited records; no missing values imputed.",
            confidence="insufficient_sample" if suppressed else "qualified_historical_reference",
            limitations=(
                "Historical results are not guaranteed future outcomes.",
                "Correlation does not establish causation.",
            ),
            provenance=provenance,
        )
        self.repository.save("benchmarks", rid, result)
        self._audit(org, "benchmark_calculated", rid, principal_id)
        if suppressed:
            self._notify(
                org,
                "benchmark_small_sample",
                rid,
                "Benchmark suppressed by minimum-group safeguard",
            )
        return result

    def select_comparables(
        self,
        org: str,
        target_project_id: str,
        projects: dict[str, dict[str, str]],
        criteria: tuple[str, ...],
    ) -> ComparableSelection:
        target = projects.get(target_project_id)
        if target is None:
            raise ValueError("Target project metadata not provided")
        results = []
        for pid, metadata in projects.items():
            if pid == target_project_id:
                continue
            matching = tuple(k for k in criteria if k in target and metadata.get(k) == target[k])
            nonmatching = tuple(
                k for k in criteria if k in target and k in metadata and metadata[k] != target[k]
            )
            missing = tuple(k for k in criteria if k not in target or k not in metadata)
            confidence = len(matching) / max(len(criteria), 1)
            results.append(
                ComparableProject(
                    project_id=pid,
                    matching_attributes=matching,
                    nonmatching_attributes=nonmatching,
                    missing_attributes=missing,
                    confidence=confidence,
                )
            )
        selection = ComparableSelection(
            id=f"comparable_{uuid4().hex[:16]}",
            organization_id=org,
            target_project_id=target_project_id,
            results=tuple(sorted(results, key=lambda x: x.confidence, reverse=True)),
            criteria=criteria,
        )
        self.repository.save("comparables", selection.id, selection)
        self._audit(org, "comparable_selection", selection.id)
        return selection

    def assess_quality(
        self,
        org: str,
        project_id: str,
        taxonomy: dict[str, str],
        evidence_count: int,
        restricted: bool,
    ) -> DataQualityAssessment:
        findings = []
        if not taxonomy:
            findings.append("missing project taxonomy")
        if evidence_count == 0:
            findings.append("missing source citations")
        if restricted:
            findings.append("project confidentiality restriction")
        eligible = not restricted and bool(taxonomy) and evidence_count > 0
        status = "eligible" if eligible else "restricted" if restricted else "insufficient_data"
        value = DataQualityAssessment(
            id=self._id("quality", org, project_id),
            organization_id=org,
            project_id=project_id,
            status=status,
            findings=tuple(findings),
            eligible=eligible,
        )
        self.repository.save("quality", value.id, value)
        self._audit(org, "data_quality_assessed", value.id)
        return value

    def dashboard(self, org: str, portfolio_id: str, principal_id: str) -> EnterpriseDashboard:
        portfolio = self.authorize(org, portfolio_id, principal_id)
        result = EnterpriseDashboard(
            organization_id=org,
            projects=len(portfolio.members),
            benchmark_eligible=sum(x.benchmark_eligible for x in portfolio.members),
            restricted_projects=sum(
                x.sharing_level == SharingLevel.RESTRICTED for x in portfolio.members
            ),
            taxonomy_review_required=sum(
                x.review_status == ReviewStatus.PROPOSED
                for x in self.repository.list("taxonomy", org)
            ),
            lessons_awaiting_review=sum(
                x.review_status == ReviewStatus.PROPOSED
                for x in self.repository.list("lessons", org)
            ),
            entity_matches_awaiting_review=sum(
                x.review_status == ReviewStatus.PROPOSED
                for x in self.repository.list("entity_matches", org)
            ),
            benchmark_definitions_awaiting_review=sum(
                x.review_status == ReviewStatus.PROPOSED
                for x in self.repository.list("benchmark_definitions", org)
            ),
        )
        self._audit(org, "enterprise_dashboard_generated", portfolio_id, principal_id)
        return result
