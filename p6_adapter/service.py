"""P6 orchestration across canonical integration and schedule domain services."""

from __future__ import annotations

from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from integration_adapters.models import (
    Capability,
    ConnectionStatus,
    ExportStatus,
    ExternalIdentityMapping,
    IntegrationConflict,
)
from integration_adapters.service import IntegrationService
from schedule_intelligence.models import ScheduleType
from schedule_intelligence.service import ScheduleIntelligenceService
from .adapter import PrimaveraP6Adapter
from .models import P6Answer, P6Dashboard, P6ProjectDiscovery


def _date(value) -> date | None:
    if not value:
        return None
    text = str(value).strip().split(" ")[0].replace("/", "-")
    for candidate in (text, "-".join(reversed(text.split("-"))) if text.count("-") == 2 else ""):
        try:
            return date.fromisoformat(candidate)
        except ValueError:
            pass
    return None


class PrimaveraP6Service:
    def __init__(
        self,
        integrations: IntegrationService,
        schedules: ScheduleIntelligenceService,
        adapter: PrimaveraP6Adapter,
    ):
        self.integrations = integrations
        self.schedules = schedules
        self.adapter = adapter

    def capabilities(self):
        return self.adapter.manifest

    def discover_projects(self, org, project, connection_id, actor, file_path: Path):
        connection = self.integrations._connection(org, project, connection_id)
        self.integrations._authorize(connection, actor)
        if connection.adapter_name != self.adapter.manifest.adapter_name:
            raise ValueError("Connection is not a Primavera P6 connection")
        self._validate_file_transport(connection.configuration.get("transport"), file_path)
        parsed = self.adapter.parse(file_path, encoding=connection.configuration.get("encoding"))
        discoveries = tuple(
            P6ProjectDiscovery(
                connection_id=connection_id,
                external_project_id=item.external_project_id,
                short_name=item.short_name,
                name=item.name,
                data_date=_date(
                    item.metadata.get("last_recalc_date") or item.metadata.get("DataDate")
                ),
                planned_start=_date(
                    item.metadata.get("plan_start_date") or item.metadata.get("PlannedStartDate")
                ),
                scheduled_finish=_date(
                    item.metadata.get("scd_end_date") or item.metadata.get("ScheduledFinishDate")
                ),
                must_finish_by=_date(
                    item.metadata.get("must_finish_date") or item.metadata.get("MustFinishByDate")
                ),
                status=item.metadata.get("status_code") or item.metadata.get("Status"),
                source_format=parsed.source_format,
                content_hash=parsed.content_hash,
                activity_count=len(item.activities),
                warnings=parsed.warnings + item.warnings,
            )
            for item in parsed.projects
        )
        self.integrations._audit(
            org,
            "p6_project_discovery",
            connection_id,
            actor,
            project,
            {"projects": len(discoveries)},
        )
        if discoveries:
            self.integrations._notify(
                org,
                "p6_project_mapping_awaiting_review",
                connection_id,
                "P6 project discovery requires explicit mapping review",
                project,
            )
        return discoveries

    def map_project(self, org, project, connection_id, external_project_id, actor):
        connection = self.integrations._connection(org, project, connection_id)
        self.integrations._authorize(connection, actor)
        updated = connection.model_copy(
            update={
                "external_project": external_project_id,
                "configuration": {
                    **connection.configuration,
                    "external_project_id": external_project_id,
                },
                "reviewed_by": actor,
            }
        )
        self.integrations.repository.save("connections", connection_id, updated)
        self.integrations._audit(
            org,
            "p6_project_mapping_confirmation",
            connection_id,
            actor,
            project,
            {"external_project_id": external_project_id},
        )
        return updated

    def import_schedule(self, org, project, connection_id, actor, file_path: Path, *, name=None):
        connection = self.integrations._connection(org, project, connection_id)
        self.integrations._authorize(connection, actor)
        if connection.status != ConnectionStatus.ACTIVE:
            raise ValueError("Active P6 connection required")
        external_project = connection.external_project
        if not external_project:
            raise ValueError("Explicit P6-to-Brunel project mapping is required")
        self._validate_file_transport(connection.configuration.get("transport"), file_path)
        parsed = self.adapter.parse(file_path, encoding=connection.configuration.get("encoding"))
        source_project = next(
            (x for x in parsed.projects if x.external_project_id == external_project), None
        )
        if not source_project:
            raise ValueError("Mapped P6 project is not present in source")
        session, normalized = self.integrations.import_records(
            org,
            project,
            connection_id,
            actor,
            scope={
                "file_path": str(file_path),
                "external_project_id": external_project,
                "encoding": connection.configuration.get("encoding", ""),
            },
            defer_domain_admission=True,
        )
        if session.status == "failed":
            raise ValueError("P6 adapter import failed: " + "; ".join(session.errors))
        schedule_name = name or source_project.name
        existing_schedule = next(
            (
                x
                for x in self.schedules.repository.list("schedules", project)
                if x.name.casefold() == schedule_name.casefold()
            ),
            None,
        )
        predecessor = existing_schedule.current_revision_id if existing_schedule else None
        revision = self.schedules.import_schedule(
            project,
            file_path,
            schedule_name,
            ScheduleType.UPDATE,
            predecessor_revision_id=predecessor,
            imported_by=actor,
            mapping={
                "p6_project_id": external_project,
                "encoding": connection.configuration.get("encoding", ""),
            },
        )
        for record in normalized:
            self.integrations.confirm_mapping(
                org, project, record.id, "schedule_revision", revision.id, actor
            )
        self._propose_activity_mappings(org, project, connection_id, revision.id)
        self.integrations.repository.save(
            "connections",
            connection_id,
            connection.model_copy(
                update={
                    "configuration": {
                        **connection.configuration,
                        "current_source_revision_id": revision.id,
                    }
                }
            ),
        )
        session = self.integrations.finalize_domain_admission(
            org, project, session.id, actor, len(normalized)
        )
        self._detect_regression_conflict(org, project, connection_id, revision, predecessor)
        self.integrations._audit(
            org,
            "p6_schedule_revision_admitted",
            revision.id,
            actor,
            project,
            {"import_session": session.id, "external_project_id": external_project},
        )
        self.integrations._notify(
            org,
            "p6_revision_imported",
            revision.id,
            "New immutable P6 schedule revision imported",
            project,
        )
        return session, revision

    def _propose_activity_mappings(self, org, project, connection_id, revision_id):
        now = datetime.now(UTC)
        for activity in self.schedules.activities(project, revision_id):
            object_id = activity.source_fields.get("p6_object_id")
            if not object_id:
                continue
            identifier = (
                "mapping_"
                + sha256(
                    f"{connection_id}|activity|{object_id}|{activity.id}".encode()
                ).hexdigest()[:16]
            )
            if self.integrations.repository.get("mappings", identifier, org, project):
                continue
            mapping = ExternalIdentityMapping(
                id=identifier,
                organization_id=org,
                project_id=project,
                brunel_record_type="schedule_activity_revision",
                brunel_record_id=activity.id,
                connection_id=connection_id,
                external_record_type="p6_activity",
                external_record_id=object_id,
                external_revision_id=revision_id,
                first_seen=now,
                latest_seen=now,
                last_synchronized_version=None,
                status="proposed",
                mapping_method="exact_p6_object_id_requires_review",
                confidence=0.95,
            )
            self.integrations.repository.save("mappings", mapping.id, mapping)
            self.integrations._audit(
                org, "p6_activity_mapping_proposal", mapping.id, "brunel", project
            )

    def activity_mapping_candidates(self, org, project, connection_id):
        self.integrations._connection(org, project, connection_id)
        return tuple(
            x
            for x in self.integrations.repository.list("mappings", org, project)
            if x.connection_id == connection_id
            and x.external_record_type == "p6_activity"
            and x.status == "proposed"
        )

    def review_activity_mapping(self, org, project, mapping_id, decision, actor):
        return self.integrations.review_mapping(org, project, mapping_id, decision, actor)

    @staticmethod
    def _validate_file_transport(transport, file_path):
        suffix = Path(file_path).suffix.casefold()
        if transport == "xer_file" and suffix != ".xer":
            raise ValueError("xer_file connections accept only XER sources")
        if transport == "p6_xml_file" and suffix != ".xml":
            raise ValueError("p6_xml_file connections accept only P6 XML sources")
        if transport not in {"xer_file", "p6_xml_file", "test_in_memory"}:
            raise ValueError("Selected P6 transport does not support file import")

    def _detect_regression_conflict(self, org, project, connection_id, revision, predecessor_id):
        if not predecessor_id:
            return None
        predecessor = self.schedules.repository.get("revisions", predecessor_id, project)
        if not predecessor or not predecessor.data_date or not revision.data_date:
            return None
        if revision.data_date >= predecessor.data_date:
            return None
        conflict = IntegrationConflict(
            id=f"conflict_{uuid4().hex[:16]}",
            organization_id=org,
            project_id=project,
            connection_id=connection_id,
            conflict_type="p6_data_date_regressed",
            record_ids=(predecessor.id, revision.id),
            conflicting_fields={"data_date": (str(predecessor.data_date), str(revision.data_date))},
        )
        self.integrations.repository.save("conflicts", conflict.id, conflict)
        self.integrations._notify(
            org,
            "p6_data_date_regressed",
            conflict.id,
            "Imported P6 data date is older and requires review",
            project,
        )
        return conflict

    def revisions(self, project):
        return tuple(
            x
            for x in self.schedules.repository.list("revisions", project)
            if x.parser_name.startswith("primavera-p6")
        )

    def compare(self, project, old_revision_id, new_revision_id):
        return self.schedules.compare(project, old_revision_id, new_revision_id)

    def quality(self, project, revision_id):
        return self.schedules.assess_quality(project, revision_id)

    def search(self, project, query, revision_id=None):
        return self.schedules.search(project, query, revision_id)

    def create_export_proposal(
        self,
        org,
        project,
        connection_id,
        activity_revision_id,
        field,
        value,
        evidence,
        rationale,
        actor,
        expected_version,
    ):
        connection = self.integrations._connection(org, project, connection_id)
        activity = self.schedules.repository.get("activities", activity_revision_id, project)
        if not activity:
            raise ValueError("Project-scoped schedule activity not found")
        schedule = self.schedules.repository.get("schedules", activity.schedule_id, project)
        if not schedule or schedule.current_revision_id != activity.schedule_revision_id:
            raise ValueError("Current P6 source schedule revision required")
        if not connection.external_project:
            raise ValueError("Confirmed P6 project mapping required")
        if expected_version is None:
            raise ValueError("Expected P6 activity version required")
        mapping = next(
            (
                x
                for x in self.integrations.repository.list("mappings", org, project)
                if x.connection_id == connection_id
                and x.brunel_record_id == activity.id
                and x.external_record_type == "p6_activity"
                and x.status == "confirmed"
            ),
            None,
        )
        if not mapping:
            raise ValueError("Confirmed P6 activity object mapping required")
        object_id = mapping.external_record_id
        payload = {
            "record_id": object_id,
            "mapping_id": mapping.id,
            "field": field,
            "value": value,
            "source_revision_id": activity.schedule_revision_id,
            "external_project_id": connection.external_project,
        }
        return self.integrations.create_export_proposal(
            org,
            project,
            connection_id,
            Capability.EXECUTE_APPROVED_EXPORT,
            "schedule_activity",
            activity_revision_id,
            f"update_activity_{field}",
            payload,
            tuple(evidence),
            rationale,
            actor,
            expected_version,
        )

    def dashboard(self, org, project, connection_id):
        connection = self.integrations._connection(org, project, connection_id)
        sessions = tuple(
            x
            for x in self.integrations.repository.list("sessions", org, project)
            if x.connection_id == connection_id
        )
        revisions = self.revisions(project)
        proposals = tuple(
            x
            for x in self.integrations.repository.list("proposals", org, project)
            if x.connection_id == connection_id
        )
        reconciliations = self.integrations.repository.list("reconciliations", org, project)
        conflicts = tuple(
            x
            for x in self.integrations.repository.list("conflicts", org, project)
            if x.connection_id == connection_id
        )
        mapped_raw_ids = {
            x.raw_record_id
            for x in self.integrations.repository.list("normalized", org, project)
            if x.admitted_record_id is not None
        }
        normalized = self.integrations.repository.list("normalized", org, project)
        latest = revisions[-1] if revisions else None
        return P6Dashboard(
            organization_id=org,
            project_id=project,
            connection_id=connection_id,
            connection_status=connection.status.value,
            external_project_id=connection.external_project,
            adapter_version=self.adapter.manifest.adapter_version,
            latest_import_at=max(
                (x.completed_at for x in sessions if x.completed_at), default=None
            ),
            latest_data_date=latest.data_date if latest else None,
            latest_schedule_revision_id=latest.id if latest else None,
            import_warnings=sum(len(x.warnings) for x in sessions),
            failed_imports=sum(x.status == "failed" for x in sessions),
            mapping_candidates=sum(x.raw_record_id not in mapped_raw_ids for x in normalized),
            unresolved_conflicts=sum(x.review_status == "proposed" for x in conflicts),
            proposals_awaiting_approval=sum(
                x.status == ExportStatus.READY_FOR_REVIEW for x in proposals
            ),
            approved_awaiting_execution=sum(x.status == ExportStatus.APPROVED for x in proposals),
            reconciliations_requiring_review=sum(x.reviewed_required for x in reconciliations),
        )

    def answer(self, org, project, connection_id, question):
        self.integrations._connection(org, project, connection_id)
        q = question.casefold()
        if any(
            term in q
            for term in ("caused", "responsible", "entitlement", "contractual compliance", "delay")
        ):
            return P6Answer(
                answer="Brunel cannot determine delay, causation, responsibility, entitlement, or contractual schedule compliance from P6 evidence."
            )
        revisions = self.revisions(project)
        if not revisions:
            return P6Answer(answer="No project-scoped imported P6 evidence supports an answer.")
        latest = revisions[-1]
        raw = tuple(
            x
            for x in self.integrations.repository.list("raw", org, project)
            if x.connection_id == connection_id
        )
        citations = tuple(
            {
                "connection_id": connection_id,
                "external_p6_project_id": x.external_record_id,
                "source_revision": latest.id,
                "data_date": str(latest.data_date) if latest.data_date else None,
                "external_version": x.external_version,
                "source_file": x.payload.get("source_filename"),
                "source_table": "PROJECT",
                "import_session_id": x.import_session_id,
                "imported_timestamp": x.retrieved_at.isoformat(),
                "evidence_type": "imported_p6_value",
            }
            for x in raw[-2:]
        )
        if "data date" in q:
            return P6Answer(
                answer=f"The latest imported P6 data date is {latest.data_date or 'not provided'}. This is an imported source value.",
                citations=citations,
            )
        if "changed" in q or "changes" in q:
            comparisons = self.schedules.repository.list("comparisons", project)
            if comparisons:
                return P6Answer(
                    answer=f"The latest Brunel-calculated comparison contains {len(comparisons[-1].changes)} reviewable activity changes; it does not establish causation.",
                    citations=citations,
                )
        return P6Answer(
            answer=f"The latest imported P6 revision contains {latest.activity_count} activities. Values remain imported evidence rather than schedule determinations.",
            citations=citations,
        )
