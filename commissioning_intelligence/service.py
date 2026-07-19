from datetime import date
from hashlib import sha256
from uuid import uuid4

from .models import (
    Asset,
    AuditEvent,
    Checklist,
    CloseoutRecord,
    CommissioningDashboard,
    CommissioningSystem,
    Deficiency,
    DeficiencyStatus,
    Evidence,
    Instrument,
    NotificationRequest,
    ReadinessAssessment,
    ReadinessStatus,
    Requirement,
    ReviewStatus,
    TestExecution,
    TestProcedure,
    TurnoverDashboard,
    TurnoverItem,
    TurnoverPackage,
    WorkflowLink,
)
from .repository import JsonCommissioningRepository


class CommissioningService:
    def __init__(self, repository: JsonCommissioningRepository):
        self.repository = repository

    def _id(self, prefix: str, *parts: str) -> str:
        return f"{prefix}_{sha256('|'.join(parts).encode()).hexdigest()[:16]}"

    def _audit(self, project: str, event: str, subject: str, actor: str = "brunel") -> None:
        item = AuditEvent(
            id=f"audit_{uuid4().hex[:16]}",
            project_id=project,
            event_type=event,
            subject_id=subject,
            actor=actor,
        )
        self.repository.save("audit", item.id, item)

    def _notify(self, project: str, event: str, subject: str, summary: str) -> None:
        item = NotificationRequest(
            id=f"out_{uuid4().hex[:16]}",
            project_id=project,
            event_type=event,
            subject_id=subject,
            summary=summary,
        )
        self.repository.save("outbox", item.id, item)

    def _get(self, category: str, project: str, identifier: str):
        value = self.repository.get(category, identifier, project)
        if value is None:
            raise ValueError(f"{category.rstrip('s').title()} not found in requested project")
        return value

    def create_system(
        self,
        project_id: str,
        name: str,
        *,
        parent_system_id: str | None = None,
        discipline: str | None = None,
        location: str | None = None,
        evidence: tuple[Evidence, ...] = (),
    ) -> CommissioningSystem:
        if parent_system_id:
            self._get("systems", project_id, parent_system_id)
        sid = self._id("csys", project_id, name, parent_system_id or "root")
        item = CommissioningSystem(
            id=sid,
            project_id=project_id,
            name=name,
            parent_system_id=parent_system_id,
            discipline=discipline,
            location=location,
            evidence=evidence,
        )
        self.repository.save("systems", sid, item)
        self._audit(project_id, "system_created", sid)
        return item

    def create_asset(
        self,
        project_id: str,
        system_id: str,
        tag: str,
        equipment_type: str,
        *,
        manufacturer: str | None = None,
        model: str | None = None,
        product_lineage: dict[str, str] | None = None,
        evidence: tuple[Evidence, ...] = (),
        links: tuple[WorkflowLink, ...] = (),
    ) -> Asset:
        self._get("systems", project_id, system_id)
        existing = [
            x
            for x in self.repository.list("assets", project_id)
            if x.equipment_tag.casefold() == tag.casefold()
        ]
        if existing:
            raise ValueError("Duplicate project equipment tag")
        lineage = product_lineage or {}
        values = {v.casefold() for v in lineage.values() if v}
        conflicts = (
            (
                "Specified, submitted, procured, delivered, or installed product identifiers conflict; human review required.",
            )
            if len(values) > 1
            else ()
        )
        aid = self._id("asset", project_id, tag)
        item = Asset(
            id=aid,
            project_id=project_id,
            equipment_tag=tag,
            equipment_type=equipment_type,
            system_id=system_id,
            manufacturer=manufacturer,
            model=model,
            product_lineage=lineage,
            conflicts=conflicts,
            evidence=evidence,
            links=links,
        )
        self.repository.save("assets", aid, item)
        self._audit(project_id, "asset_created", aid)
        return item

    def extract_requirements(
        self, project_id: str, evidence: tuple[Evidence, ...], *, system_id: str | None = None
    ) -> tuple[Requirement, ...]:
        if system_id:
            self._get("systems", project_id, system_id)
        keywords = {
            "startup": "startup",
            "test": "testing",
            "training": "training",
            "warranty": "warranty",
            "manual": "om_manual",
            "spare": "spare_parts",
            "as-built": "as_built",
            "checklist": "checklist",
        }
        result = []
        for source in evidence:
            category = next(
                (value for key, value in keywords.items() if key in source.excerpt.casefold()), None
            )
            if category is None:
                continue
            rid = self._id("req", project_id, source.record_id, category)
            item = Requirement(
                id=rid,
                project_id=project_id,
                original_text=source.excerpt,
                normalized_text=source.excerpt.strip(),
                category=category,
                system_id=system_id,
                citation=source,
                confidence=0.8,
                uncertainty=(
                    "Extracted requirement requires human review when source authority or applicability is ambiguous.",
                ),
            )
            self.repository.save("requirements", rid, item)
            self._audit(project_id, "requirement_extracted", rid)
            result.append(item)
        return tuple(result)

    def review_requirement(
        self, project_id: str, requirement_id: str, actor: str, accept: bool
    ) -> Requirement:
        item = self._get("requirements", project_id, requirement_id)
        updated = item.model_copy(
            update={
                "review_status": ReviewStatus.CONFIRMED if accept else ReviewStatus.REJECTED,
                "reviewer": actor,
            }
        )
        self.repository.save("requirements", item.id, updated)
        self._audit(project_id, "requirement_review", item.id, actor)
        return updated

    def create_checklist(
        self,
        project_id: str,
        system_id: str,
        title: str,
        items: tuple[dict, ...],
        *,
        asset_id: str | None = None,
    ) -> Checklist:
        self._get("systems", project_id, system_id)
        cid = f"check_{uuid4().hex[:16]}"
        value = Checklist(
            id=cid,
            project_id=project_id,
            system_id=system_id,
            asset_id=asset_id,
            title=title,
            items=items,
        )
        self.repository.save("checklists", cid, value)
        self._audit(project_id, "checklist_created", cid)
        return value

    def respond_checklist(
        self,
        project_id: str,
        checklist_id: str,
        item_id: str,
        response: dict,
        evidence: tuple[Evidence, ...],
        actor: str,
    ) -> Checklist:
        item = self._get("checklists", project_id, checklist_id)
        if item.status == ReviewStatus.CONFIRMED:
            raise ValueError("Accepted checklist results are immutable; create a revision")
        if item_id not in {str(x.get("id")) for x in item.items}:
            raise ValueError("Checklist item not found")
        responses = dict(item.responses)
        responses[item_id] = {
            **response,
            "evidence_ids": [x.record_id for x in evidence],
            "human_confirmed": False,
        }
        updated = item.model_copy(
            update={"responses": responses, "evidence": item.evidence + evidence}
        )
        self.repository.save("checklists", item.id, updated)
        self._audit(project_id, "checklist_response", item.id, actor)
        return updated

    def create_procedure(
        self,
        project_id: str,
        system_id: str,
        title: str,
        steps: tuple[dict, ...],
        evidence: tuple[Evidence, ...],
        *,
        procedure_id: str | None = None,
    ) -> TestProcedure:
        self._get("systems", project_id, system_id)
        pid = procedure_id or f"proc_{uuid4().hex[:16]}"
        revisions = [
            x.revision for x in self.repository.list("procedures", project_id) if x.id == pid
        ]
        revision = max(revisions, default=0) + 1
        revision_id = f"{pid}_r{revision}"
        item = TestProcedure(
            id=pid,
            project_id=project_id,
            revision_id=revision_id,
            revision=revision,
            title=title,
            system_id=system_id,
            procedure_type="functional",
            steps=steps,
            evidence=evidence,
        )
        self.repository.save("procedures", revision_id, item, immutable=True)
        self._audit(project_id, "procedure_revision", revision_id)
        return item

    def record_test(
        self,
        project_id: str,
        procedure_revision_id: str,
        system_id: str,
        test_date: date,
        expected: tuple[str, ...],
        reported: tuple[str, ...],
        outcome: str,
        evidence: tuple[Evidence, ...],
        *,
        retest_of_id: str | None = None,
        instrument_ids: tuple[str, ...] = (),
    ) -> TestExecution:
        self._get("procedures", project_id, procedure_revision_id)
        if retest_of_id:
            self._get("executions", project_id, retest_of_id)
        eid = f"test_{uuid4().hex[:16]}"
        item = TestExecution(
            id=eid,
            project_id=project_id,
            procedure_revision_id=procedure_revision_id,
            system_id=system_id,
            test_date=test_date,
            expected_results=expected,
            reported_results=reported,
            reported_outcome=outcome,
            evidence=evidence,
            retest_of_id=retest_of_id,
            instrument_ids=instrument_ids,
        )
        self.repository.save("executions", eid, item)
        self._audit(project_id, "test_execution", eid)
        if outcome.casefold() in {"failed", "incomplete"}:
            self._notify(
                project_id,
                "test_result_awaiting_review",
                eid,
                "Reported test exception requires human review",
            )
        return item

    def add_instrument(
        self,
        project_id: str,
        instrument_type: str,
        serial: str,
        *,
        expiration: date | None = None,
        certificate: Evidence | None = None,
    ) -> Instrument:
        iid = self._id("inst", project_id, serial)
        item = Instrument(
            id=iid,
            project_id=project_id,
            instrument_type=instrument_type,
            serial_number=serial,
            expiration_date=expiration,
            certificate=certificate,
        )
        self.repository.save("instruments", iid, item)
        self._audit(project_id, "instrument_recorded", iid)
        return item

    def instrument_findings(
        self, project_id: str, test_date: date, instrument_ids: tuple[str, ...]
    ) -> tuple[str, ...]:
        findings = []
        for identifier in instrument_ids:
            instrument = self._get("instruments", project_id, identifier)
            if instrument.certificate is None:
                findings.append(f"{identifier}: missing calibration evidence; review required")
            if instrument.expiration_date and instrument.expiration_date < test_date:
                findings.append(
                    f"{identifier}: calibration expired before reported test; review required"
                )
        return tuple(findings)

    def create_deficiency(
        self,
        project_id: str,
        system_id: str,
        title: str,
        description: str,
        evidence: tuple[Evidence, ...],
        *,
        source_record_id: str | None = None,
    ) -> Deficiency:
        self._get("systems", project_id, system_id)
        did = f"def_{uuid4().hex[:16]}"
        item = Deficiency(
            id=did,
            project_id=project_id,
            title=title,
            description=description,
            system_id=system_id,
            source_record_id=source_record_id,
            evidence=evidence,
        )
        self.repository.save("deficiencies", did, item)
        self._audit(project_id, "deficiency_created", did)
        return item

    def transition_deficiency(
        self,
        project_id: str,
        deficiency_id: str,
        status: DeficiencyStatus,
        actor: str,
        *,
        evidence: tuple[Evidence, ...] = (),
        rationale: str = "",
    ) -> Deficiency:
        item = self._get("deficiencies", project_id, deficiency_id)
        human_only = {DeficiencyStatus.VERIFIED, DeficiencyStatus.CLOSED}
        if status in human_only and (not evidence or not rationale):
            raise ValueError(
                "Verification or closure requires authorized human rationale and evidence"
            )
        allowed = {
            DeficiencyStatus.PROPOSED: {DeficiencyStatus.UNDER_REVIEW, DeficiencyStatus.REJECTED},
            DeficiencyStatus.UNDER_REVIEW: {DeficiencyStatus.OPEN, DeficiencyStatus.REJECTED},
            DeficiencyStatus.OPEN: {
                DeficiencyStatus.CORRECTION_REPORTED,
                DeficiencyStatus.DEFERRED,
            },
            DeficiencyStatus.CORRECTION_REPORTED: {DeficiencyStatus.READY_FOR_VERIFICATION},
            DeficiencyStatus.READY_FOR_VERIFICATION: {
                DeficiencyStatus.VERIFIED,
                DeficiencyStatus.REOPENED,
            },
            DeficiencyStatus.VERIFIED: {DeficiencyStatus.CLOSED, DeficiencyStatus.REOPENED},
            DeficiencyStatus.CLOSED: {DeficiencyStatus.REOPENED},
            DeficiencyStatus.REOPENED: {DeficiencyStatus.OPEN},
        }
        if status not in allowed.get(item.status, set()):
            raise ValueError("Invalid deficiency transition")
        updated = item.model_copy(
            update={
                "status": status,
                "closure_evidence": item.closure_evidence + evidence,
                "reviewer_disposition": rationale or item.reviewer_disposition,
                "version": item.version + 1,
            }
        )
        self.repository.save("deficiencies", item.id, updated)
        self._audit(project_id, f"deficiency_{status}", item.id, actor)
        if status == DeficiencyStatus.REOPENED:
            self._notify(
                project_id,
                "deficiency_reopened",
                item.id,
                "Deficiency reopened by authorized reviewer",
            )
        return updated

    def assess_readiness(
        self, project_id: str, system_id: str, purpose: str
    ) -> ReadinessAssessment:
        self._get("systems", project_id, system_id)
        requirements = [
            x for x in self.repository.list("requirements", project_id) if x.system_id == system_id
        ]
        tests = [
            x for x in self.repository.list("executions", project_id) if x.system_id == system_id
        ]
        deficiencies = [
            x
            for x in self.repository.list("deficiencies", project_id)
            if x.system_id == system_id
            and x.status not in {DeficiencyStatus.CLOSED, DeficiencyStatus.REJECTED}
        ]
        factors = (
            f"{len(requirements)} requirement records",
            f"{len(tests)} reported test executions",
            f"{len(deficiencies)} unresolved deficiency records",
        )
        if not requirements:
            status = ReadinessStatus.INSUFFICIENT_EVIDENCE
        elif deficiencies:
            status = ReadinessStatus.READINESS_CONCERNS
        elif not tests:
            status = ReadinessStatus.NOT_READY
        else:
            status = ReadinessStatus.READY_FOR_HUMAN_REVIEW
        evidence = tuple(e for item in requirements for e in (item.citation,)) + tuple(
            e for item in tests for e in item.evidence
        )
        rid = f"ready_{uuid4().hex[:16]}"
        result = ReadinessAssessment(
            id=rid,
            project_id=project_id,
            system_id=system_id,
            purpose=purpose,
            status=status,
            factors=factors,
            blockers=tuple(x.id for x in deficiencies),
            evidence=evidence,
            human_authorization=False,
        )
        self.repository.save("readiness", rid, result, immutable=True)
        self._audit(project_id, "readiness_assessed", rid)
        return result

    def create_turnover_package(
        self,
        project_id: str,
        package_type: str,
        item_types: tuple[str, ...],
        *,
        system_id: str | None = None,
    ) -> TurnoverPackage:
        if system_id:
            self._get("systems", project_id, system_id)
        pid = f"turn_{uuid4().hex[:16]}"
        items = tuple(TurnoverItem(id=f"item_{uuid4().hex[:12]}", item_type=x) for x in item_types)
        package = TurnoverPackage(
            id=pid,
            project_id=project_id,
            package_type=package_type,
            system_id=system_id,
            items=items,
        )
        self.repository.save("packages", pid, package)
        self._audit(project_id, "turnover_package_created", pid)
        return package

    def add_turnover_item(
        self,
        project_id: str,
        package_id: str,
        item_id: str,
        record_id: str,
        evidence: tuple[Evidence, ...],
        actor: str,
    ) -> TurnoverPackage:
        package = self._get("packages", project_id, package_id)
        if package.accepted_as_recorded:
            raise ValueError("Accepted turnover package is immutable; create a revision")
        if item_id not in {x.id for x in package.items}:
            raise ValueError("Turnover item not found")
        items = tuple(
            x.model_copy(
                update={"status": "received", "record_id": record_id, "evidence": evidence}
            )
            if x.id == item_id
            else x
            for x in package.items
        )
        complete = all(not x.required or x.status == "received" for x in items)
        updated = package.model_copy(
            update={
                "items": items,
                "completeness_proposal": "appears_complete_for_human_review"
                if complete
                else "incomplete",
            }
        )
        self.repository.save("packages", package.id, updated)
        self._audit(project_id, "turnover_document_ingested", package.id, actor)
        return updated

    def add_closeout_record(
        self,
        project_id: str,
        record_type: str,
        attributes: dict,
        evidence: tuple[Evidence, ...],
        *,
        system_id: str | None = None,
        asset_id: str | None = None,
        document_revision_id: str | None = None,
    ) -> CloseoutRecord:
        rid = f"close_{uuid4().hex[:16]}"
        item = CloseoutRecord(
            id=rid,
            project_id=project_id,
            record_type=record_type,
            system_id=system_id,
            asset_id=asset_id,
            attributes=attributes,
            evidence=evidence,
            document_revision_id=document_revision_id,
        )
        self.repository.save("closeout", rid, item)
        self._audit(project_id, f"{record_type}_recorded", rid)
        return item

    def commissioning_dashboard(self, project_id: str) -> CommissioningDashboard:
        requirements = self.repository.list("requirements", project_id)
        tests = self.repository.list("executions", project_id)
        deficiencies = self.repository.list("deficiencies", project_id)
        readiness = self.repository.list("readiness", project_id)
        return CommissioningDashboard(
            project_id=project_id,
            systems=len(self.repository.list("systems", project_id)),
            assets=len(self.repository.list("assets", project_id)),
            requirements_awaiting_review=sum(
                x.review_status == ReviewStatus.PROPOSED for x in requirements
            ),
            tests_awaiting_review=sum(x.reviewer_disposition is None for x in tests),
            failed_or_incomplete_tests=sum(
                x.reported_outcome.casefold() in {"failed", "incomplete"} for x in tests
            ),
            open_deficiencies=sum(
                x.status not in {DeficiencyStatus.CLOSED, DeficiencyStatus.REJECTED}
                for x in deficiencies
            ),
            readiness_concerns=sum(
                x.status
                in {
                    ReadinessStatus.NOT_READY,
                    ReadinessStatus.READINESS_CONCERNS,
                    ReadinessStatus.INSUFFICIENT_EVIDENCE,
                }
                for x in readiness
            ),
        )

    def turnover_dashboard(self, project_id: str) -> TurnoverDashboard:
        packages = self.repository.list("packages", project_id)
        items = [x for package in packages for x in package.items]
        missing = [x for x in items if x.required and x.status != "received"]
        return TurnoverDashboard(
            project_id=project_id,
            packages=len(packages),
            packages_awaiting_review=sum(x.status == ReviewStatus.PROPOSED for x in packages),
            missing_items=len(missing),
            missing_manuals=sum("manual" in x.item_type for x in missing),
            missing_warranties=sum("warranty" in x.item_type for x in missing),
            missing_training=sum("training" in x.item_type for x in missing),
            missing_as_builts=sum(
                "as-built" in x.item_type or "as_built" in x.item_type for x in missing
            ),
        )

    def search(self, project_id: str, query: str) -> tuple[object, ...]:
        q = query.casefold()
        found = []
        for category in (
            "systems",
            "assets",
            "requirements",
            "executions",
            "deficiencies",
            "packages",
            "closeout",
        ):
            found.extend(
                x
                for x in self.repository.list(category, project_id)
                if q in x.model_dump_json().casefold()
            )
        return tuple(found)
