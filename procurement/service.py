"""Deterministic procurement application service with human authority guardrails."""

from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
import json
import re
from uuid import uuid4

from .models import (
    AuditEvent,
    DeliveryRecord,
    EvidenceReference,
    ExposureAssessment,
    ExposureLevel,
    LeadTimeEvidence,
    NotificationRequest,
    ProcurementCandidate,
    ProcurementCategory,
    ProcurementDashboard,
    ProcurementDatePlan,
    ProcurementDependency,
    ProcurementForecast,
    ProcurementItem,
    ProcurementItemChange,
    ProcurementMilestone,
    ProcurementPlanComparison,
    ProcurementPlanRevision,
    ProcurementStatus,
    ReleaseAuthorization,
    RequiredOnSiteRecord,
)
from .repository import JsonProcurementRepository


class ProcurementService:
    """Owns procurement rules; adapters contain no commercial or schedule decisions."""

    TRANSITIONS = {
        ProcurementStatus.PLANNED: {
            ProcurementStatus.AWAITING_INFORMATION,
            ProcurementStatus.AWAITING_SUBMITTAL,
            ProcurementStatus.READY_FOR_RELEASE,
            ProcurementStatus.ON_HOLD,
            ProcurementStatus.CANCELLED,
        },
        ProcurementStatus.AWAITING_INFORMATION: {
            ProcurementStatus.PLANNED,
            ProcurementStatus.AWAITING_SUBMITTAL,
            ProcurementStatus.BLOCKED,
        },
        ProcurementStatus.AWAITING_SUBMITTAL: {
            ProcurementStatus.SUBMITTAL_IN_REVIEW,
            ProcurementStatus.BLOCKED,
        },
        ProcurementStatus.SUBMITTAL_IN_REVIEW: {
            ProcurementStatus.AWAITING_APPROVAL,
            ProcurementStatus.AWAITING_SUBMITTAL,
        },
        ProcurementStatus.AWAITING_APPROVAL: {
            ProcurementStatus.READY_FOR_RELEASE,
            ProcurementStatus.AWAITING_SUBMITTAL,
            ProcurementStatus.BLOCKED,
        },
        ProcurementStatus.READY_FOR_RELEASE: {
            ProcurementStatus.RELEASE_PENDING_AUTHORIZATION,
            ProcurementStatus.BLOCKED,
        },
        ProcurementStatus.RELEASE_PENDING_AUTHORIZATION: {
            ProcurementStatus.RELEASED,
            ProcurementStatus.READY_FOR_RELEASE,
            ProcurementStatus.BLOCKED,
        },
        ProcurementStatus.RELEASED: {
            ProcurementStatus.IN_FABRICATION,
            ProcurementStatus.READY_TO_SHIP,
            ProcurementStatus.IN_TRANSIT,
        },
        ProcurementStatus.IN_FABRICATION: {
            ProcurementStatus.FACTORY_TESTING,
            ProcurementStatus.READY_TO_SHIP,
            ProcurementStatus.BLOCKED,
        },
        ProcurementStatus.FACTORY_TESTING: {
            ProcurementStatus.READY_TO_SHIP,
            ProcurementStatus.BLOCKED,
        },
        ProcurementStatus.READY_TO_SHIP: {ProcurementStatus.IN_TRANSIT},
        ProcurementStatus.IN_TRANSIT: {ProcurementStatus.DELIVERED},
        ProcurementStatus.DELIVERED: {
            ProcurementStatus.INSPECTION_PENDING,
            ProcurementStatus.ACCEPTED,
        },
        ProcurementStatus.INSPECTION_PENDING: {
            ProcurementStatus.ACCEPTED,
            ProcurementStatus.BLOCKED,
        },
        ProcurementStatus.ACCEPTED: {
            ProcurementStatus.STORED,
            ProcurementStatus.INSTALLATION_READY,
        },
        ProcurementStatus.STORED: {ProcurementStatus.INSTALLATION_READY},
        ProcurementStatus.INSTALLATION_READY: {ProcurementStatus.INSTALLED},
        ProcurementStatus.INSTALLED: {ProcurementStatus.CLOSED},
        ProcurementStatus.BLOCKED: {
            ProcurementStatus.PLANNED,
            ProcurementStatus.READY_FOR_RELEASE,
            ProcurementStatus.IN_FABRICATION,
        },
        ProcurementStatus.ON_HOLD: {ProcurementStatus.PLANNED, ProcurementStatus.CANCELLED},
    }

    SIGNALS = re.compile(
        r"\b(furnish|provide|procure|purchase|long[- ]lead|release|fabricat|manufactur|ship|deliver|required on site|owner furnished|factory test|storage|startup|spare parts)\w*\b",
        re.I,
    )

    def __init__(self, repository: JsonProcurementRepository) -> None:
        self.repository = repository

    def extract_candidates(
        self, project_id: str, sources: list[dict[str, object]]
    ) -> tuple[ProcurementCandidate, ...]:
        results = []
        existing = {c.id: c for c in self.repository.list("candidates", project_id)}
        for source in sources:
            text = str(source.get("text", "")).strip()
            matches = tuple(dict.fromkeys(m.group(0).lower() for m in self.SIGNALS.finditer(text)))
            if not matches:
                continue
            source_id = str(source.get("source_id", source.get("document_id", "manual")))
            candidate_id = (
                "pcand_"
                + sha256(f"{project_id}|{source_id}|{text.casefold()}".encode()).hexdigest()[:20]
            )
            if candidate_id in existing:
                results.append(existing[candidate_id])
                continue
            title = str(source.get("title") or self._candidate_title(text))
            category = self._category(f"{title} {text}")
            citation = EvidenceReference(
                source_type=str(source.get("source_type", "project_evidence")),
                source_id=source_id,
                document_id=str(source.get("document_id")) if source.get("document_id") else None,
                document_name=str(source.get("document_name"))
                if source.get("document_name")
                else None,
                page_number=int(source["page_number"]) if source.get("page_number") else None,
                chunk_id=str(source.get("chunk_id")) if source.get("chunk_id") else None,
                exact_excerpt=text[:500],
                evidence_type=str(source.get("evidence_type", "source_statement")),
            )
            item = ProcurementCandidate(
                id=candidate_id,
                project_id=project_id,
                proposed_title=title,
                description=text,
                category=category,
                discipline=str(source.get("discipline")) if source.get("discipline") else None,
                equipment_tag=str(source.get("equipment_tag"))
                if source.get("equipment_tag")
                else None,
                citations=(citation,),
                extraction_reasons=matches,
                evidence_strength=min(0.95, 0.45 + len(matches) * 0.1),
                created_at=datetime.now(UTC),
            )
            self.repository.save("candidates", item.id, item)
            self._audit(project_id, "candidate_extracted", item.id, "system")
            self._notify(
                project_id,
                "candidate_awaiting_review",
                item.id,
                f"Procurement candidate awaiting review: {title}",
            )
            results.append(item)
        return tuple(results)

    def review_candidate(
        self,
        project_id: str,
        candidate_id: str,
        decision: str,
        reviewer: str,
        *,
        title: str | None = None,
        linked_item_id: str | None = None,
    ) -> tuple[ProcurementCandidate, ProcurementItem | None]:
        candidate = self._candidate(project_id, candidate_id)
        if candidate.review_status != "unreviewed":
            return candidate, self._item(
                project_id, candidate.linked_item_id
            ) if candidate.linked_item_id else None
        allowed = {
            "accept",
            "reject",
            "modify",
            "merge",
            "split",
            "not_applicable",
            "link_existing",
            "defer",
        }
        if decision not in allowed:
            raise ValueError("Unsupported candidate review decision")
        item = None
        if decision in {"accept", "modify"}:
            item = self.create_item(
                project_id,
                title or candidate.proposed_title,
                category=candidate.category,
                description=candidate.description,
                citations=candidate.citations,
                equipment_tag=candidate.equipment_tag,
                actor=reviewer,
                source_candidate_id=candidate.id,
            )
            linked_item_id = item.id
        elif decision == "link_existing":
            if not linked_item_id or not self._item(project_id, linked_item_id):
                raise ValueError("A project-scoped existing item is required")
            item = self._item(project_id, linked_item_id)
        updated = candidate.model_copy(
            update={
                "review_status": decision,
                "reviewer": reviewer,
                "reviewed_at": datetime.now(UTC),
                "linked_item_id": linked_item_id,
            }
        )
        self.repository.save("candidates", updated.id, updated)
        self._audit(project_id, "candidate_reviewed", updated.id, reviewer, {"decision": decision})
        return updated, item

    def create_item(
        self,
        project_id: str,
        title: str,
        *,
        category: ProcurementCategory = ProcurementCategory.OTHER,
        description: str = "",
        required_on_site: date | None = None,
        required_on_site_basis: str = "user_entered_target",
        citations: tuple[EvidenceReference, ...] = (),
        equipment_tag: str | None = None,
        actor: str = "local-user",
        source_candidate_id: str | None = None,
    ) -> ProcurementItem:
        duplicate = next(
            (
                x
                for x in self.list_items(project_id)
                if (equipment_tag and x.equipment_tag == equipment_tag)
                or (source_candidate_id and source_candidate_id in x.tags)
            ),
            None,
        )
        if duplicate:
            return duplicate
        number = f"PROC-{max([int(x.procurement_number.split('-')[-1]) for x in self.list_items(project_id) if x.procurement_number.startswith('PROC-') and x.procurement_number.split('-')[-1].isdigit()] or [0]) + 1:03d}"
        now = datetime.now(UTC)
        ros = (
            RequiredOnSiteRecord(
                id="ros_" + uuid4().hex,
                value=required_on_site,
                basis=required_on_site_basis,
                confirmed=False,
                planning_assumption=True,
            )
            if required_on_site
            else None
        )
        item = ProcurementItem(
            id="proc_" + uuid4().hex,
            project_id=project_id,
            procurement_number=number,
            title=title,
            description=description,
            category=category,
            equipment_tag=equipment_tag,
            required_on_site=ros,
            citations=citations,
            tags=(source_candidate_id,) if source_candidate_id else (),
            created_at=now,
            updated_at=now,
        )
        self.repository.save("items", item.id, item)
        self._audit(project_id, "procurement_item_created", item.id, actor, {"number": number})
        return item

    def list_items(
        self, project_id: str, *, status: ProcurementStatus | None = None, query: str | None = None
    ) -> tuple[ProcurementItem, ...]:
        items = tuple(
            x for x in self.repository.list("items", project_id) if isinstance(x, ProcurementItem)
        )
        if status:
            items = tuple(x for x in items if x.status == status)
        if query:
            needle = query.casefold()
            items = tuple(
                x
                for x in items
                if needle
                in " ".join(
                    str(v or "")
                    for v in (
                        x.procurement_number,
                        x.title,
                        x.description,
                        x.equipment_tag,
                        x.category,
                        x.discipline,
                        x.supplier,
                        x.manufacturer,
                        x.product,
                        x.model_number,
                        x.status,
                        x.notes,
                    )
                ).casefold()
            )
        return items

    def update_item(
        self, project_id: str, item_id: str, actor: str = "local-user", **updates
    ) -> ProcurementItem:
        item = self._require_item(project_id, item_id)
        safe = {
            k: v
            for k, v in updates.items()
            if k in ProcurementItem.model_fields
            and k not in {"id", "project_id", "procurement_number", "created_at", "schema_version"}
        }
        updated = item.model_copy(
            update={**safe, "updated_at": datetime.now(UTC), "version": item.version + 1}
        )
        self.repository.save("items", item.id, updated)
        self._audit(
            project_id, "procurement_item_updated", item.id, actor, {"fields": ",".join(safe)}
        )
        return updated

    def link_product_and_submittal(
        self,
        project_id: str,
        item_id: str,
        *,
        actor: str,
        submittal_id: str | None = None,
        product: str | None = None,
        manufacturer: str | None = None,
        model_number: str | None = None,
    ) -> ProcurementItem:
        """Link canonical references without copying submittal or product aggregates."""
        item = self._require_item(project_id, item_id)
        links = item.related_submittal_ids
        if submittal_id and submittal_id not in links:
            links += (submittal_id,)
        updated = self.update_item(
            project_id,
            item_id,
            actor,
            related_submittal_ids=links,
            product=product if product is not None else item.product,
            manufacturer=manufacturer if manufacturer is not None else item.manufacturer,
            model_number=model_number if model_number is not None else item.model_number,
        )
        self._audit(
            project_id,
            "product_submittal_linked",
            item_id,
            actor,
            {"submittal_id": submittal_id or ""},
        )
        return updated

    def add_lead_time(
        self,
        project_id: str,
        item_id: str,
        duration: int,
        unit: str,
        definition: str,
        source_type: str,
        *,
        actor: str,
        citation: EvidenceReference | None = None,
        confirmed: bool = False,
        active: bool = True,
        notes: str | None = None,
    ) -> ProcurementItem:
        item = self._require_item(project_id, item_id)
        if unit not in {"days", "weeks"}:
            raise ValueError("Lead-time unit must be days or weeks")
        old_active = next((x for x in item.lead_times if x.id == item.active_lead_time_id), None)
        evidence = LeadTimeEvidence(
            id="lead_" + uuid4().hex,
            project_id=project_id,
            procurement_item_id=item_id,
            duration=duration,
            unit=unit,
            definition=definition,
            source_type=source_type,
            citation=citation,
            confirmed=confirmed,
            planning_assumption=not confirmed,
            supersedes_id=old_active.id if old_active and active else None,
            active=active,
            notes=notes,
            created_at=datetime.now(UTC),
        )
        lead_times = tuple(
            x.model_copy(update={"active": False}) if active and x.active else x
            for x in item.lead_times
        ) + (evidence,)
        updated = self.update_item(
            project_id,
            item_id,
            actor,
            lead_times=lead_times,
            active_lead_time_id=evidence.id if active else item.active_lead_time_id,
        )
        self._audit(
            project_id,
            "lead_time_added",
            item_id,
            actor,
            {"definition": definition, "duration": str(duration), "unit": unit},
        )
        if old_active and old_active.calendar_days != evidence.calendar_days:
            self._notify(
                project_id,
                "lead_time_changed",
                item_id,
                "Active procurement lead time changed; review derived dates.",
            )
        return updated

    def calculate_dates(
        self,
        project_id: str,
        item_id: str,
        *,
        shipping_days: int | None = None,
        fabrication_days: int | None = None,
        procurement_processing_days: int | None = None,
        approval_correction_days: int = 0,
        design_review_days: int | None = None,
        resubmittal_days: int = 0,
        internal_review_days: int = 0,
        receiving_days: int = 0,
        buffer_days: int = 0,
        actor: str = "system",
    ) -> ProcurementDatePlan:
        item = self._require_item(project_id, item_id)
        active = next((x for x in item.lead_times if x.id == item.active_lead_time_id), None)
        if (
            fabrication_days is None
            and active
            and active.definition in {"fabrication", "release_to_ready_to_ship"}
        ):
            fabrication_days = active.calendar_days
        missing = []
        if not item.required_on_site:
            missing.append("required_on_site_date")
        if shipping_days is None:
            missing.append("shipping_duration")
        if fabrication_days is None:
            missing.append("fabrication_duration")
        if procurement_processing_days is None:
            missing.append("procurement_processing_duration")
        if design_review_days is None:
            missing.append("design_review_duration")
        values = dict(
            shipping_days=shipping_days,
            fabrication_days=fabrication_days,
            procurement_processing_days=procurement_processing_days,
            approval_correction_days=approval_correction_days,
            design_review_days=design_review_days,
            resubmittal_days=resubmittal_days,
            internal_review_days=internal_review_days,
            receiving_days=receiving_days,
            buffer_days=buffer_days,
        )
        dates = {}
        if not missing:
            ros = item.required_on_site.value
            ship = ros - timedelta(days=receiving_days + buffer_days)
            ready = ship - timedelta(days=shipping_days)
            fabrication = ready - timedelta(days=fabrication_days)
            release = fabrication - timedelta(days=procurement_processing_days)
            approval = release - timedelta(days=approval_correction_days)
            submit = approval - timedelta(
                days=design_review_days + resubmittal_days + internal_review_days
            )
            dates = {
                "latest_ship_date": ship,
                "latest_ready_to_ship_date": ready,
                "latest_fabrication_start": fabrication,
                "latest_release_date": release,
                "latest_approval_date": approval,
                "latest_submit_date": submit,
                "current_float_days": (release - date.today()).days,
            }
        plan = ProcurementDatePlan(
            id="plan_" + uuid4().hex,
            project_id=project_id,
            procurement_item_id=item_id,
            required_on_site_date=item.required_on_site.value if item.required_on_site else None,
            inputs=values,
            missing_inputs=tuple(missing),
            warnings=("Derived dates are planning calculations, not contractual milestones.",),
            calculated_at=datetime.now(UTC),
            **dates,
        )
        self.update_item(project_id, item_id, actor, date_plans=item.date_plans + (plan,))
        self._audit(project_id, "derived_dates_calculated", item_id, actor)
        return plan

    def add_dependency(
        self,
        project_id: str,
        item_id: str,
        dependency_type: str,
        target_reference: str,
        *,
        actor: str,
        status: str = "open",
        human_confirmed: bool = False,
    ) -> ProcurementItem:
        item = self._require_item(project_id, item_id)
        dep = ProcurementDependency(
            id="dep_" + uuid4().hex,
            dependency_type=dependency_type,
            target_reference=target_reference,
            status=status,
            human_confirmed=human_confirmed,
        )
        return self.update_item(project_id, item_id, actor, dependencies=item.dependencies + (dep,))

    def add_milestone(
        self,
        project_id: str,
        item_id: str,
        milestone_type: str,
        *,
        actor: str,
        planned_date: date | None = None,
        forecast_date: date | None = None,
        actual_date: date | None = None,
        human_confirmed: bool = False,
    ) -> ProcurementItem:
        item = self._require_item(project_id, item_id)
        milestone = ProcurementMilestone(
            id="mile_" + uuid4().hex,
            milestone_type=milestone_type,
            planned_date=planned_date,
            forecast_date=forecast_date,
            actual_date=actual_date,
            status="actual" if actual_date else "forecast" if forecast_date else "planned",
            human_confirmed=human_confirmed,
        )
        return self.update_item(
            project_id, item_id, actor, milestones=item.milestones + (milestone,)
        )

    def forecast(
        self,
        project_id: str,
        item_id: str,
        delivery_date: date | None,
        release_date: date | None,
        confidence: str,
        basis: str,
        actor: str,
        *,
        assumptions: tuple[str, ...] = (),
        confirmed: bool = False,
    ) -> ProcurementItem:
        item = self._require_item(project_id, item_id)
        previous = item.forecasts[-1].id if item.forecasts else None
        record = ProcurementForecast(
            id="forecast_" + uuid4().hex,
            forecast_delivery_date=delivery_date,
            forecast_release_date=release_date,
            confidence=confidence,
            basis=basis,
            assumptions=assumptions,
            created_by=actor,
            created_at=datetime.now(UTC),
            supersedes_id=previous,
            human_confirmed=confirmed,
        )
        return self.update_item(project_id, item_id, actor, forecasts=item.forecasts + (record,))

    def assess_release_readiness(self, project_id: str, item_id: str) -> dict[str, object]:
        item = self._require_item(project_id, item_id)
        conditions = {
            "product_selected": bool(item.product),
            "approved_submittal_linked": bool(item.related_submittal_ids),
            "not_stale": item.stale_status == "current",
            "dependencies_satisfied": all(
                x.status in {"satisfied", "waived"} and x.human_confirmed for x in item.dependencies
            ),
        }
        status = (
            "ready"
            if all(conditions.values())
            else "ready_with_conditions"
            if conditions["product_selected"] and conditions["approved_submittal_linked"]
            else "not_ready"
        )
        return {
            "status": status,
            "conditions": conditions,
            "authorization_recorded": any(
                x.status == "authorized" for x in item.release_authorizations
            ),
            "human_authorization_required": True,
        }

    def authorize_release(
        self, project_id: str, item_id: str, authorized_by: str, reference: str
    ) -> ProcurementItem:
        item = self._require_item(project_id, item_id)
        auth = ReleaseAuthorization(
            id="auth_" + uuid4().hex,
            status="authorized",
            authorized_by=authorized_by,
            reference=reference,
            created_at=datetime.now(UTC),
        )
        updated = self.update_item(
            project_id,
            item_id,
            authorized_by,
            release_authorizations=item.release_authorizations + (auth,),
        )
        self._audit(project_id, "release_authorized", item_id, authorized_by)
        return updated

    def transition(
        self,
        project_id: str,
        item_id: str,
        status: ProcurementStatus,
        actor: str,
        *,
        reason: str | None = None,
    ) -> ProcurementItem:
        item = self._require_item(project_id, item_id)
        if status not in self.TRANSITIONS.get(item.status, set()):
            raise ValueError(f"Invalid procurement transition: {item.status} -> {status}")
        if status == ProcurementStatus.RELEASED and not any(
            x.status == "authorized" for x in item.release_authorizations
        ):
            raise ValueError("Human release authorization is required")
        if (
            status
            in {
                ProcurementStatus.ON_HOLD,
                ProcurementStatus.CANCELLED,
                ProcurementStatus.SUPERSEDED,
            }
            and not reason
        ):
            raise ValueError("A reason is required")
        updated = self.update_item(project_id, item_id, actor, status=status)
        self._audit(
            project_id,
            "status_transitioned",
            item_id,
            actor,
            {"old": item.status, "new": status, "reason": reason or ""},
        )
        return updated

    def record_delivery(
        self,
        project_id: str,
        item_id: str,
        delivery_date: date,
        status: str,
        actor: str,
        *,
        quantity: float | None = None,
        partial: bool = False,
        damage_noted: bool = False,
        accepted: bool = False,
    ) -> ProcurementItem:
        item = self._require_item(project_id, item_id)
        delivery = DeliveryRecord(
            id="delivery_" + uuid4().hex,
            status=status,
            delivery_date=delivery_date,
            quantity_delivered=quantity,
            partial=partial,
            damage_noted=damage_noted,
            accepted=accepted,
            recorded_by=actor,
            created_at=datetime.now(UTC),
        )
        updated = self.update_item(
            project_id,
            item_id,
            actor,
            deliveries=item.deliveries + (delivery,),
            status=ProcurementStatus.ACCEPTED if accepted else ProcurementStatus.DELIVERED,
        )
        self._notify(
            project_id,
            "item_delivered",
            item_id,
            "Procurement delivery recorded; acceptance remains separate.",
        )
        return updated

    def record_acceptance(
        self, project_id: str, item_id: str, accepted_by: str, reference: str
    ) -> ProcurementItem:
        item = self._require_item(project_id, item_id)
        if not item.deliveries:
            raise ValueError("Delivery must be recorded before acceptance")
        delivery = item.deliveries[-1].model_copy(update={"accepted": True})
        updated = self.update_item(
            project_id,
            item_id,
            accepted_by,
            deliveries=item.deliveries[:-1] + (delivery,),
            status=ProcurementStatus.ACCEPTED,
            notes=item.notes + (f"Acceptance reference: {reference}",),
        )
        self._audit(project_id, "acceptance_recorded", item_id, accepted_by)
        return updated

    def assess_exposure(self, project_id: str, item_id: str) -> ExposureAssessment:
        item = self._require_item(project_id, item_id)
        reasons = []
        types = []
        plan = item.date_plans[-1] if item.date_plans else None
        forecast = item.forecasts[-1] if item.forecasts else None
        if not item.required_on_site:
            reasons.append("Required-on-site date is missing")
            types.append("incomplete_information")
        if not item.active_lead_time_id:
            reasons.append("Active lead time is missing")
            types.append("incomplete_information")
        if plan and plan.current_float_days is not None and plan.current_float_days < 0:
            reasons.append("Derived latest release date has passed")
            types.append("release_delay")
        if (
            forecast
            and item.required_on_site
            and forecast.forecast_delivery_date
            and forecast.forecast_delivery_date > item.required_on_site.value
        ):
            reasons.append("Human forecast is after required-on-site date")
            types.append("delivery_variance")
        if any(x.status in {"open", "blocked", "unknown"} for x in item.dependencies):
            reasons.append("Open dependency blocks or may block progress")
            types.append("incomplete_information")
        if item.stale_status != "current":
            reasons.append("Source relationship requires re-review")
            types.append("stale_approval")
        level = (
            ExposureLevel.HIGH
            if any(x in types for x in ("release_delay", "delivery_variance"))
            else ExposureLevel.MEDIUM
            if reasons
            else ExposureLevel.INFORMATIONAL
        )
        assessment = ExposureAssessment(
            id="exposure_" + uuid4().hex,
            level=level,
            exposure_types=tuple(dict.fromkeys(types)),
            reasons=tuple(reasons) or ("No deterministic exposure signal found.",),
            evidence_strength="moderate" if reasons else "insufficient",
            forecast_confidence=forecast.confidence if forecast else "insufficient",
            assessed_at=datetime.now(UTC),
        )
        self.update_item(
            project_id,
            item_id,
            "system",
            exposure_assessments=item.exposure_assessments + (assessment,),
        )
        return assessment

    def mark_stale(self, project_id: str, item_id: str, reason: str, actor: str) -> ProcurementItem:
        item = self._require_item(project_id, item_id)
        updated = self.update_item(
            project_id,
            item_id,
            actor,
            stale_status="re_review_required",
            staleness_reasons=item.staleness_reasons + (reason,),
        )
        self._notify(
            project_id,
            "procurement_item_stale",
            item_id,
            "Procurement source changed; human reconciliation required.",
        )
        return updated

    def snapshot(
        self, project_id: str, actor: str, notes: str | None = None
    ) -> ProcurementPlanRevision:
        items = self.list_items(project_id)
        snapshots = {x.id: x.model_dump(mode="json") for x in items}
        raw = json.dumps(snapshots, sort_keys=True, default=str)
        plan = ProcurementPlanRevision(
            id="procplan_" + uuid4().hex,
            project_id=project_id,
            item_versions={x.id: x.version for x in items},
            item_snapshots=snapshots,
            content_hash=sha256(raw.encode()).hexdigest(),
            created_by=actor,
            created_at=datetime.now(UTC),
            notes=notes,
        )
        self.repository.save("plans", plan.id, plan, immutable=True)
        self._audit(project_id, "plan_snapshot_created", plan.id, actor)
        return plan

    def compare_plans(self, project_id: str, old_id: str, new_id: str) -> ProcurementPlanComparison:
        old = self.repository.get("plans", old_id, project_id)
        new = self.repository.get("plans", new_id, project_id)
        if not isinstance(old, ProcurementPlanRevision) or not isinstance(
            new, ProcurementPlanRevision
        ):
            raise ValueError("Plan revision not found")
        changes = []
        fields = (
            "product",
            "manufacturer",
            "model_number",
            "quantity",
            "status",
            "required_on_site",
            "active_lead_time_id",
            "dependencies",
            "forecasts",
            "stale_status",
        )
        for item_id in sorted(set(old.item_snapshots) | set(new.item_snapshots)):
            a = old.item_snapshots.get(item_id)
            b = new.item_snapshots.get(item_id)
            number = (b or a or {}).get("procurement_number", item_id)
            if a is None:
                changes.append(
                    ProcurementItemChange(
                        item_id=item_id, procurement_number=number, change_type="item_added"
                    )
                )
                continue
            if b is None:
                changes.append(
                    ProcurementItemChange(
                        item_id=item_id, procurement_number=number, change_type="item_removed"
                    )
                )
                continue
            for field in fields:
                if a.get(field) != b.get(field):
                    changes.append(
                        ProcurementItemChange(
                            item_id=item_id,
                            procurement_number=number,
                            change_type="field_changed",
                            field=field,
                            old_value=a.get(field),
                            new_value=b.get(field),
                        )
                    )
        result = ProcurementPlanComparison(
            id="proccompare_" + uuid4().hex,
            project_id=project_id,
            old_plan_id=old_id,
            new_plan_id=new_id,
            changes=tuple(changes),
            created_at=datetime.now(UTC),
        )
        self.repository.save("comparisons", result.id, result, immutable=True)
        return result

    def dashboard(self, project_id: str) -> ProcurementDashboard:
        items = tuple(
            x
            for x in self.list_items(project_id)
            if x.status
            not in {
                ProcurementStatus.CLOSED,
                ProcurementStatus.CANCELLED,
                ProcurementStatus.SUPERSEDED,
            }
        )
        status = {}
        exposure = {}
        overdue = 0
        for item in items:
            status[item.status.value] = status.get(item.status.value, 0) + 1
            level = (
                item.exposure_assessments[-1].level.value
                if item.exposure_assessments
                else "unknown"
            )
            exposure[level] = exposure.get(level, 0) + 1
            overdue += sum(
                1
                for m in item.milestones
                if not m.actual_date
                and (m.forecast_date or m.planned_date)
                and (m.forecast_date or m.planned_date) < date.today()
            )
        return ProcurementDashboard(
            project_id=project_id,
            total_active=len(items),
            status_counts=status,
            exposure_counts=exposure,
            critical_items=sum(x.criticality == "critical" for x in items),
            missing_lead_times=sum(not x.active_lead_time_id for x in items),
            missing_required_on_site=sum(not x.required_on_site for x in items),
            pending_authorization=sum(
                x.status == ProcurementStatus.RELEASE_PENDING_AUTHORIZATION for x in items
            ),
            overdue_milestones=overdue,
        )

    def _candidate_title(self, text: str) -> str:
        clean = re.sub(r"\s+", " ", text).strip()
        return clean[:80].rstrip(" .") or "Procurement requirement"

    def _category(self, text: str) -> ProcurementCategory:
        low = text.casefold()
        for word, cat in (
            ("switchgear", ProcurementCategory.SWITCHGEAR),
            ("generator", ProcurementCategory.GENERATORS),
            ("transformer", ProcurementCategory.TRANSFORMERS),
            ("ups", ProcurementCategory.UPS),
            ("chiller", ProcurementCategory.MECHANICAL_EQUIPMENT),
            ("control", ProcurementCategory.CONTROLS),
            ("steel", ProcurementCategory.STRUCTURAL_STEEL),
            ("elevator", ProcurementCategory.ELEVATORS),
        ):
            if word in low:
                return cat
        return ProcurementCategory.OTHER

    def _candidate(self, p, c):
        value = self.repository.get("candidates", c, p)
        if not isinstance(value, ProcurementCandidate):
            raise ValueError("Procurement candidate not found")
        return value

    def _item(self, p, i):
        return self.repository.get("items", i, p) if i else None

    def _require_item(self, p, i):
        value = self._item(p, i)
        if not isinstance(value, ProcurementItem):
            raise ValueError("Procurement item not found")
        return value

    def _audit(self, p, event, subject, actor, metadata=None):
        record = AuditEvent(
            id="paudit_" + uuid4().hex,
            project_id=p,
            event_type=event,
            subject_id=subject,
            actor=actor,
            created_at=datetime.now(UTC),
            metadata=metadata or {},
        )
        self.repository.save("audit", record.id, record, immutable=True)

    def _notify(self, p, event, subject, summary):
        record = NotificationRequest(
            id="pnotify_" + uuid4().hex,
            project_id=p,
            event_type=event,
            subject_id=subject,
            summary=summary,
            created_at=datetime.now(UTC),
        )
        self.repository.save("outbox", record.id, record, immutable=True)
