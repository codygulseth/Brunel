"""Submittal register, package, review, response, resubmittal, and integration workflows."""

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from typing import Any
from uuid import uuid4

from change_workflow.models import (
    ActorReference,
    ChangeDisposition,
    NotificationRequest,
    NotificationType,
    RelationshipType,
    ReviewerReference,
    WorkflowType,
)
from change_workflow.notifications import NotificationOutboxService
from change_workflow.repository import JsonChangeWorkflowRepository
from change_workflow.service import ProjectChangeService
from rfi.repository import JsonRFIRepository
from rfi.service import RFIService

from .errors import SubmittalNotFoundError, SubmittalTransitionError, SubmittalValidationError
from .models import (
    AttachmentMetadata,
    CandidateStatus,
    CompletenessIssue,
    CompletenessSeverity,
    CompletenessStatus,
    ComplianceMatrixEntry,
    InternalReviewDecision,
    MatrixStatus,
    OfficialDisposition,
    PackageReviewStatus,
    ProcurementDependency,
    ProcurementExposureStatus,
    RequirementAdmissionResult,
    RequirementReview,
    RequirementReviewDecision,
    StalenessStatus,
    SubmittalAuditEvent,
    SubmittalCompletenessAssessment,
    SubmittalEvidenceReference,
    SubmittalInternalReview,
    SubmittalManufacturer,
    SubmittalPackage,
    SubmittalPackageRevision,
    SubmittalProduct,
    SubmittalRegisterItem,
    SubmittalRequirement,
    SubmittalRequirementCandidate,
    SubmittalResponse,
    SubmittalResponseAnalysis,
    SubmittalStalenessAssessment,
    SubmittalStatus,
    SubmittalType,
    SubstitutionRequest,
)
from .numbering import ProjectSubmittalNumberingService, SubmittalNumberingService
from .repository import JsonSubmittalRepository


TRANSITIONS: dict[SubmittalStatus, set[SubmittalStatus]] = {
    SubmittalStatus.CANDIDATE: {SubmittalStatus.PLANNED, SubmittalStatus.VOID},
    SubmittalStatus.PLANNED: {
        SubmittalStatus.NOT_STARTED,
        SubmittalStatus.IN_PREPARATION,
        SubmittalStatus.PENDING_SUBCONTRACTOR,
        SubmittalStatus.VOID,
        SubmittalStatus.SUPERSEDED,
    },
    SubmittalStatus.NOT_STARTED: {
        SubmittalStatus.IN_PREPARATION,
        SubmittalStatus.PENDING_SUBCONTRACTOR,
        SubmittalStatus.VOID,
    },
    SubmittalStatus.PENDING_SUBCONTRACTOR: {SubmittalStatus.IN_PREPARATION},
    SubmittalStatus.IN_PREPARATION: {SubmittalStatus.PENDING_INTERNAL_REVIEW},
    SubmittalStatus.PENDING_INTERNAL_REVIEW: {
        SubmittalStatus.REVISIONS_REQUIRED_INTERNAL,
        SubmittalStatus.READY_TO_SUBMIT,
    },
    SubmittalStatus.REVISIONS_REQUIRED_INTERNAL: {SubmittalStatus.IN_PREPARATION},
    SubmittalStatus.READY_TO_SUBMIT: {SubmittalStatus.SUBMITTED},
    SubmittalStatus.SUBMITTED: {SubmittalStatus.UNDER_DESIGN_REVIEW},
    SubmittalStatus.UNDER_DESIGN_REVIEW: {
        SubmittalStatus.APPROVED,
        SubmittalStatus.APPROVED_AS_NOTED,
        SubmittalStatus.REVISE_AND_RESUBMIT,
        SubmittalStatus.REJECTED,
        SubmittalStatus.INFORMATIONAL_RECEIVED,
    },
    SubmittalStatus.APPROVED: {
        SubmittalStatus.PROCUREMENT_RELEASED,
        SubmittalStatus.CLOSED,
        SubmittalStatus.IN_PREPARATION,
        SubmittalStatus.SUPERSEDED,
    },
    SubmittalStatus.APPROVED_AS_NOTED: {
        SubmittalStatus.PROCUREMENT_RELEASED,
        SubmittalStatus.CLOSED,
        SubmittalStatus.IN_PREPARATION,
        SubmittalStatus.SUPERSEDED,
    },
    SubmittalStatus.REVISE_AND_RESUBMIT: {SubmittalStatus.IN_PREPARATION},
    SubmittalStatus.REJECTED: {SubmittalStatus.IN_PREPARATION, SubmittalStatus.VOID},
    SubmittalStatus.INFORMATIONAL_RECEIVED: {SubmittalStatus.CLOSED},
    SubmittalStatus.PROCUREMENT_RELEASED: {SubmittalStatus.CLOSED, SubmittalStatus.IN_PREPARATION},
    SubmittalStatus.CLOSED: {SubmittalStatus.IN_PREPARATION},
    SubmittalStatus.SUPERSEDED: set(),
    SubmittalStatus.VOID: set(),
}


DISPOSITION_STATUS = {
    OfficialDisposition.APPROVED: SubmittalStatus.APPROVED,
    OfficialDisposition.NO_EXCEPTION_TAKEN: SubmittalStatus.APPROVED,
    OfficialDisposition.APPROVED_AS_NOTED: SubmittalStatus.APPROVED_AS_NOTED,
    OfficialDisposition.MAKE_CORRECTIONS_NOTED: SubmittalStatus.APPROVED_AS_NOTED,
    OfficialDisposition.REVISE_AND_RESUBMIT: SubmittalStatus.REVISE_AND_RESUBMIT,
    OfficialDisposition.REJECTED: SubmittalStatus.REJECTED,
    OfficialDisposition.INFORMATIONAL_ONLY: SubmittalStatus.INFORMATIONAL_RECEIVED,
    OfficialDisposition.REVIEWED: SubmittalStatus.INFORMATIONAL_RECEIVED,
    OfficialDisposition.NOT_REVIEWED: SubmittalStatus.REJECTED,
    OfficialDisposition.VOID: SubmittalStatus.VOID,
}


class SubmittalService:
    def __init__(
        self,
        repository: JsonSubmittalRepository,
        changes: JsonChangeWorkflowRepository | None = None,
        rfis: JsonRFIRepository | None = None,
        *,
        numbering: SubmittalNumberingService | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.changes = changes
        self.rfis = rfis
        self.numbering = numbering or ProjectSubmittalNumberingService(repository)
        self.clock = clock or (lambda: datetime.now(UTC))

    def get_candidate(self, project_id: str, candidate_id: str) -> SubmittalRequirementCandidate:
        candidate = self.repository.get_candidate(project_id, candidate_id)
        if candidate is None:
            raise SubmittalNotFoundError("Submittal requirement candidate not found")
        return candidate

    def review_candidate(
        self,
        project_id: str,
        candidate_id: str,
        decision: RequirementReviewDecision,
        actor: ActorReference,
        *,
        explanation: str,
        description: str | None = None,
        discipline: str | None = None,
        responsible_subcontractor: str | None = None,
    ) -> RequirementAdmissionResult:
        candidate = self.get_candidate(project_id, candidate_id)
        if candidate.status != CandidateStatus.PENDING_REVIEW:
            existing = next(
                (
                    item
                    for item in self.repository.list_register(project_id)
                    if any(req.candidate_id == candidate.id for req in item.requirements)
                ),
                None,
            )
            return RequirementAdmissionResult(
                candidate_id=candidate.id,
                decision=decision,
                register_item_id=existing.id if existing else None,
            )
        target = {
            RequirementReviewDecision.ACCEPT: CandidateStatus.ACCEPTED,
            RequirementReviewDecision.REJECT: CandidateStatus.REJECTED,
            RequirementReviewDecision.NOT_APPLICABLE: CandidateStatus.NOT_APPLICABLE,
            RequirementReviewDecision.DEFER: CandidateStatus.DEFERRED,
        }[decision]
        edited = candidate.model_copy(
            update={
                "description": description or candidate.description,
                "discipline": discipline or candidate.discipline,
                "status": target,
                "version": candidate.version + 1,
                "updated_at": self.clock(),
            }
        )
        self.repository.save_candidate(edited, expected_version=candidate.version)
        register: SubmittalRegisterItem | None = None
        duplicate: SubmittalRegisterItem | None = None
        if decision == RequirementReviewDecision.ACCEPT:
            duplicate = self._find_duplicate(project_id, edited)
            if duplicate is None:
                register = self._register_from_candidate(
                    edited, actor, responsible_subcontractor=responsible_subcontractor
                )
        review = RequirementReview(
            id=f"subreview_{uuid4().hex}",
            candidate_id=candidate.id,
            decision=decision,
            reviewer=actor,
            explanation=explanation,
            created_at=self.clock(),
            resulting_register_item_id=register.id
            if register
            else duplicate.id
            if duplicate
            else None,
        )
        self.repository.append_review(project_id, review)
        self._audit(
            project_id,
            "requirement_candidate",
            candidate.id,
            actor,
            "candidate_reviewed",
            candidate.status.value,
            target.value,
            explanation,
        )
        return RequirementAdmissionResult(
            candidate_id=candidate.id,
            decision=decision,
            register_item_id=register.id if register else None,
            duplicate_register_item_id=duplicate.id if duplicate else None,
        )

    def merge_candidates(
        self,
        project_id: str,
        candidate_ids: tuple[str, ...],
        actor: ActorReference,
        *,
        description: str,
    ) -> SubmittalRegisterItem:
        if len(candidate_ids) < 2:
            raise SubmittalValidationError("At least two candidates are required to merge")
        candidates = tuple(self.get_candidate(project_id, item_id) for item_id in candidate_ids)
        first = candidates[0]
        register = self.create_register(
            project_id=project_id,
            specification_section=first.specification_section,
            description=description,
            actor=actor,
            requirements=tuple(self._requirement(candidate) for candidate in candidates),
            discipline=first.discipline,
        )
        for candidate in candidates:
            updated = candidate.model_copy(
                update={
                    "status": CandidateStatus.MERGED,
                    "version": candidate.version + 1,
                    "updated_at": self.clock(),
                }
            )
            self.repository.save_candidate(updated, expected_version=candidate.version)
            self._audit(
                project_id,
                "requirement_candidate",
                candidate.id,
                actor,
                "candidate_merged",
                candidate.status.value,
                register.id,
            )
        return register

    def split_candidate(
        self,
        project_id: str,
        candidate_id: str,
        actor: ActorReference,
        parts: tuple[tuple[SubmittalType, str], ...],
    ) -> tuple[SubmittalRequirementCandidate, ...]:
        candidate = self.get_candidate(project_id, candidate_id)
        if len(parts) < 2:
            raise SubmittalValidationError("Split requires at least two resulting requirements")
        created = []
        for submittal_type, description in parts:
            identity = sha256(
                f"{candidate.id}\0{submittal_type}\0{description}".encode()
            ).hexdigest()[:24]
            child = candidate.model_copy(
                update={
                    "id": f"subreq_{identity}",
                    "version": 1,
                    "submittal_type": submittal_type,
                    "description": description,
                    "required_documentation": (submittal_type.value,),
                    "status": CandidateStatus.PENDING_REVIEW,
                    "created_at": self.clock(),
                    "updated_at": self.clock(),
                }
            )
            self.repository.save_candidate(child)
            created.append(child)
        updated = candidate.model_copy(
            update={
                "status": CandidateStatus.SPLIT,
                "version": candidate.version + 1,
                "updated_at": self.clock(),
            }
        )
        self.repository.save_candidate(updated, expected_version=candidate.version)
        self._audit(
            project_id,
            "requirement_candidate",
            candidate.id,
            actor,
            "candidate_split",
            candidate.status.value,
            ",".join(item.id for item in created),
        )
        return tuple(created)

    def create_register(
        self,
        *,
        project_id: str,
        specification_section: str,
        description: str,
        actor: ActorReference,
        requirements: tuple[SubmittalRequirement, ...] = (),
        discipline: str | None = None,
        responsible_subcontractor: str | None = None,
        related_project_change_ids: tuple[str, ...] = (),
        related_rfi_ids: tuple[str, ...] = (),
        required_on_site_date: date | None = None,
        lead_time_days: int | None = None,
        legacy_related_item_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> SubmittalRegisterItem:
        if idempotency_key:
            existing = next(
                (
                    item
                    for item in self.repository.list_register(project_id)
                    if item.idempotency_key == idempotency_key
                ),
                None,
            )
            if existing:
                return existing
        number = self.numbering.next_register_number(project_id, specification_section)
        identity = sha256(f"{project_id}\0{number}".encode()).hexdigest()[:20]
        now = self.clock()
        item = SubmittalRegisterItem(
            id=f"sub_{identity}",
            project_id=project_id,
            register_number=number,
            specification_section=specification_section,
            description=description,
            requirements=requirements,
            discipline=discipline,
            responsible_subcontractor=responsible_subcontractor,
            required_on_site_date=required_on_site_date,
            lead_time_days=lead_time_days,
            related_project_change_ids=related_project_change_ids,
            related_rfi_ids=related_rfi_ids,
            created_by=actor,
            created_at=now,
            updated_at=now,
            legacy_related_item_id=legacy_related_item_id,
            idempotency_key=idempotency_key,
        )
        if required_on_site_date and lead_time_days is not None:
            item = item.model_copy(
                update={
                    "procurement": self._derive_procurement(
                        required_on_site_date=required_on_site_date,
                        fabrication_days=lead_time_days,
                    )
                }
            )
        self.repository.save_register(item)
        self._audit(
            project_id, "register_item", item.id, actor, "register_item_created", None, number
        )
        self._link_related(item, actor)
        return item

    def get_register(self, project_id: str, item_id: str) -> SubmittalRegisterItem:
        item = self.repository.get_register(project_id, item_id)
        if item is None:
            raise SubmittalNotFoundError("Submittal register item not found")
        return item

    def override_number(
        self,
        project_id: str,
        item_id: str,
        number: str,
        actor: ActorReference,
        *,
        reason: str,
    ) -> SubmittalRegisterItem:
        item = self.get_register(project_id, item_id)
        if item.status not in {SubmittalStatus.PLANNED, SubmittalStatus.NOT_STARTED}:
            raise SubmittalTransitionError("Register number is stable after preparation begins")
        if not reason.strip():
            raise SubmittalValidationError("Number override reason is required")
        if any(
            other.register_number == number and other.id != item.id
            for other in self.repository.list_register(project_id)
        ):
            raise SubmittalValidationError("Register number already exists in this project")
        updated = self._save_register(item, register_number=number)
        self._audit(
            project_id,
            "register_item",
            item.id,
            actor,
            "number_overridden",
            item.register_number,
            number,
            reason,
        )
        return updated

    def assign(
        self,
        project_id: str,
        item_id: str,
        actor: ActorReference,
        *,
        reviewer: ReviewerReference | None = None,
        subcontractor: str | None = None,
        planned_submit_date: date | None = None,
        required_response_date: date | None = None,
    ) -> SubmittalRegisterItem:
        item = self.get_register(project_id, item_id)
        updated = self._save_register(
            item,
            internal_reviewer=reviewer or item.internal_reviewer,
            responsible_subcontractor=subcontractor or item.responsible_subcontractor,
            planned_submit_date=planned_submit_date or item.planned_submit_date,
            required_response_date=required_response_date or item.required_response_date,
        )
        self._audit(
            project_id,
            "register_item",
            item.id,
            actor,
            "assignment_changed",
            None,
            reviewer.id if reviewer else subcontractor,
        )
        if reviewer:
            self._notify(
                updated, reviewer, NotificationType.ASSIGNMENT_CREATED, "Submittal review assigned"
            )
        return updated

    def update_procurement(
        self,
        project_id: str,
        item_id: str,
        actor: ActorReference,
        *,
        required_on_site_date: date,
        fabrication_days: int,
        shipping_days: int = 0,
        processing_days: int = 0,
        review_days: int = 0,
        resubmittal_days: int = 0,
        buffer_days: int = 0,
    ) -> SubmittalRegisterItem:
        item = self.get_register(project_id, item_id)
        dependency = self._derive_procurement(
            required_on_site_date=required_on_site_date,
            fabrication_days=fabrication_days,
            shipping_days=shipping_days,
            processing_days=processing_days,
            review_days=review_days,
            resubmittal_days=resubmittal_days,
            buffer_days=buffer_days,
        )
        updated = self._save_register(
            item,
            required_on_site_date=required_on_site_date,
            lead_time_days=fabrication_days,
            procurement=dependency,
        )
        self._audit(
            project_id,
            "register_item",
            item.id,
            actor,
            "procurement_exposure_changed",
            item.procurement.exposure_status.value,
            dependency.exposure_status.value,
        )
        return updated

    def transition(
        self,
        project_id: str,
        item_id: str,
        status: SubmittalStatus,
        actor: ActorReference,
        *,
        reason: str | None = None,
    ) -> SubmittalRegisterItem:
        item = self.get_register(project_id, item_id)
        if status not in TRANSITIONS[item.status]:
            raise SubmittalTransitionError(
                f"Cannot transition {item.status.value} to {status.value}"
            )
        if status == SubmittalStatus.PENDING_INTERNAL_REVIEW and not item.internal_reviewer:
            raise SubmittalTransitionError("Internal review requires an assigned reviewer")
        if (
            status in {SubmittalStatus.SUBMITTED, SubmittalStatus.UNDER_DESIGN_REVIEW}
            and not item.package_ids
        ):
            raise SubmittalTransitionError("Submission requires a package revision")
        if status in {SubmittalStatus.VOID, SubmittalStatus.SUPERSEDED} and not reason:
            raise SubmittalTransitionError("Void and superseded transitions require a reason")
        if (
            item.status == SubmittalStatus.CLOSED
            and status == SubmittalStatus.IN_PREPARATION
            and not reason
        ):
            raise SubmittalTransitionError("Reopening a closed submittal requires a reason")
        if status == SubmittalStatus.CLOSED:
            self._validate_closure(item)
        updated = self._save_register(
            item,
            status=status,
            actual_submit_date=self.clock().date()
            if status == SubmittalStatus.SUBMITTED
            else item.actual_submit_date,
            closed_at=self.clock() if status == SubmittalStatus.CLOSED else item.closed_at,
        )
        self._audit(
            project_id,
            "register_item",
            item.id,
            actor,
            "status_transition",
            item.status.value,
            status.value,
            reason,
        )
        if updated.internal_reviewer:
            self._notify(
                updated,
                updated.internal_reviewer,
                NotificationType.STATUS_CHANGED,
                "Submittal status changed",
            )
        return updated

    def link_rfi(
        self, project_id: str, item_id: str, rfi_id: str, actor: ActorReference
    ) -> SubmittalRegisterItem:
        """Create a bidirectional project-scoped RFI relationship."""
        item = self.get_register(project_id, item_id)
        if self.rfis is None:
            raise SubmittalValidationError("RFI repository is required")
        rfi = RFIService(self.rfis).get(project_id, rfi_id)
        if rfi_id in item.related_rfi_ids:
            return item
        updated = self._save_register(item, related_rfi_ids=item.related_rfi_ids + (rfi_id,))
        RFIService(self.rfis).link_submittal(project_id, rfi.id, item.id, actor)
        self._audit(project_id, "register_item", item.id, actor, "rfi_linked", None, rfi.id)
        return updated

    def create_package(
        self,
        project_id: str,
        primary_item_id: str,
        actor: ActorReference,
        *,
        register_item_ids: tuple[str, ...] = (),
        title: str | None = None,
        description: str = "",
        submitter: str,
        manufacturer: SubmittalManufacturer | None = None,
        product: SubmittalProduct | None = None,
        included_types: tuple[SubmittalType, ...] = (),
        attachments: tuple[AttachmentMetadata, ...] = (),
        deviations: tuple[str, ...] = (),
        related_rfi_ids: tuple[str, ...] = (),
        related_project_change_ids: tuple[str, ...] = (),
    ) -> SubmittalPackage:
        ids = tuple(dict.fromkeys((primary_item_id,) + register_item_ids))
        items = tuple(self.get_register(project_id, item_id) for item_id in ids)
        primary = items[0]
        if manufacturer and manufacturer.project_id != project_id:
            raise SubmittalValidationError("Manufacturer belongs to another project")
        if product:
            if product.project_id and product.project_id != project_id:
                raise SubmittalValidationError("Product belongs to another project")
            product = product.model_copy(
                update={
                    "project_id": project_id,
                    "related_specification_sections": tuple(
                        dict.fromkeys(
                            product.related_specification_sections
                            + tuple(item.specification_section for item in items)
                        )
                    ),
                    "related_submittal_ids": tuple(
                        dict.fromkeys(product.related_submittal_ids + ids)
                    ),
                }
            )
        package_number = f"{primary.register_number}-P01"
        identity = sha256(f"{project_id}\0{package_number}".encode()).hexdigest()[:20]
        existing_package = self.repository.get_package(project_id, f"subpkg_{identity}")
        if existing_package:
            return existing_package
        evidence = tuple(
            evidence
            for item in items
            for requirement in item.requirements
            for evidence in requirement.evidence
        )
        now = self.clock()
        revision = self._package_revision(
            revision=1,
            title=title or primary.description,
            description=description or self._cover_description(primary, included_types),
            submitter=submitter,
            subcontractor=primary.responsible_subcontractor,
            manufacturer=manufacturer,
            product=product,
            included_types=included_types,
            attachments=attachments,
            deviations=deviations,
            drawing_references=primary.drawing_references,
            related_rfi_ids=tuple(dict.fromkeys(primary.related_rfi_ids + related_rfi_ids)),
            related_project_change_ids=tuple(
                dict.fromkeys(primary.related_project_change_ids + related_project_change_ids)
            ),
            evidence=evidence,
            actor=actor,
            summary="Initial package",
        )
        package = SubmittalPackage(
            id=f"subpkg_{identity}",
            project_id=project_id,
            package_number=package_number,
            register_item_ids=ids,
            revisions=(revision,),
            created_at=now,
            updated_at=now,
        )
        self.repository.save_package(package)
        for item in items:
            updated = self._save_register(
                item,
                package_ids=tuple(dict.fromkeys(item.package_ids + (package.id,))),
                status=SubmittalStatus.IN_PREPARATION,
            )
            self._audit(
                project_id, "register_item", updated.id, actor, "package_linked", None, package.id
            )
        self._audit(
            project_id, "package", package.id, actor, "package_created", None, package_number
        )
        return package

    def get_package(self, project_id: str, package_id: str) -> SubmittalPackage:
        package = self.repository.get_package(project_id, package_id)
        if package is None:
            raise SubmittalNotFoundError("Submittal package not found")
        return package

    def revise_package(
        self,
        project_id: str,
        package_id: str,
        actor: ActorReference,
        *,
        change_summary: str,
        included_types: tuple[SubmittalType, ...] | None = None,
        attachments: tuple[AttachmentMetadata, ...] | None = None,
        deviations: tuple[str, ...] | None = None,
        manufacturer: SubmittalManufacturer | None = None,
        product: SubmittalProduct | None = None,
        correction_checklist: tuple[str, ...] = (),
    ) -> SubmittalPackage:
        package = self.get_package(project_id, package_id)
        current = package.revisions[-1]
        description = current.description
        if included_types is not None and current.description.startswith(
            "Submitted for review against Specification Section"
        ):
            description = self._cover_description(
                self.get_register(project_id, package.register_item_ids[0]), included_types
            )
        revision = self._package_revision(
            revision=current.revision + 1,
            title=current.title,
            description=description,
            submitter=current.submitter,
            subcontractor=current.responsible_subcontractor,
            manufacturer=manufacturer or current.manufacturer,
            product=product or current.product,
            included_types=included_types if included_types is not None else current.included_types,
            attachments=attachments if attachments is not None else current.attachments,
            deviations=deviations if deviations is not None else current.deviations,
            drawing_references=current.drawing_references,
            related_rfi_ids=current.related_rfi_ids,
            related_project_change_ids=current.related_project_change_ids,
            evidence=current.evidence,
            actor=actor,
            summary=change_summary,
            correction_checklist=correction_checklist,
        )
        updated = self._save_package(
            package,
            current_revision=revision.revision,
            revisions=package.revisions + (revision,),
            internal_review_status=PackageReviewStatus.DRAFT,
        )
        self._set_register_statuses(updated, SubmittalStatus.IN_PREPARATION, actor)
        self._audit(
            project_id,
            "package",
            package.id,
            actor,
            "package_revision_created",
            str(current.revision),
            str(revision.revision),
            change_summary,
        )
        return updated

    def review_completeness(
        self, project_id: str, package_id: str, actor: ActorReference
    ) -> SubmittalCompletenessAssessment:
        package = self.get_package(project_id, package_id)
        revision = package.revisions[-1]
        requirements = self._requirements(project_id, package.register_item_ids)
        issues: list[CompletenessIssue] = []
        for requirement in requirements:
            citation = requirement.evidence[0] if requirement.evidence else None
            if requirement.submittal_type not in revision.included_types:
                issues.append(
                    CompletenessIssue(
                        code=f"missing_{requirement.submittal_type.value}",
                        severity=CompletenessSeverity.BLOCKING,
                        message=f"Required {requirement.submittal_type.value.replace('_', ' ')} is not listed in the package.",
                        requirement_id=requirement.id,
                        citation=citation,
                        blocks_routing=True,
                        recommended_action="Add the required document and create a new package revision.",
                    )
                )
            elif not any(
                attachment.document_type == requirement.submittal_type
                for attachment in revision.attachments
            ):
                issues.append(
                    CompletenessIssue(
                        code=f"missing_attachment_{requirement.submittal_type.value}",
                        severity=CompletenessSeverity.BLOCKING,
                        message="The package lists this document type but has no attachment metadata.",
                        requirement_id=requirement.id,
                        citation=citation,
                        blocks_routing=True,
                        recommended_action="Add attachment metadata; domain records do not store binaries.",
                    )
                )
        if not requirements or any(not requirement.evidence for requirement in requirements):
            issues.append(
                CompletenessIssue(
                    code="missing_requirement_evidence",
                    severity=CompletenessSeverity.BLOCKING,
                    message="The package lacks a cited specification requirement.",
                    blocks_routing=True,
                    recommended_action="Link the package to a reviewed specification requirement.",
                )
            )
        if SubmittalType.PRODUCT_DATA in revision.included_types and not revision.manufacturer:
            issues.append(
                CompletenessIssue(
                    code="missing_manufacturer",
                    severity=CompletenessSeverity.WARNING,
                    message="Product data is included but the manufacturer is not identified.",
                    blocks_routing=False,
                    recommended_action="Confirm the manufacturer before routing.",
                )
            )
        claims = f"{revision.description} {' '.join(revision.deviations)}".casefold()
        if any(
            term in claims for term in ("fully compliant", "complies with all", "approved product")
        ):
            issues.append(
                CompletenessIssue(
                    code="unsupported_compliance_claim",
                    severity=CompletenessSeverity.WARNING,
                    message="The package contains an unsupported technical compliance claim.",
                    blocks_routing=False,
                    recommended_action="Replace with factual package-content language pending design review.",
                )
            )
        if not revision.deviations:
            issues.append(
                CompletenessIssue(
                    code="deviation_confirmation",
                    severity=CompletenessSeverity.INFORMATIONAL,
                    message="No deviations are disclosed; a reviewer should confirm whether that is intentional.",
                    blocks_routing=False,
                    recommended_action="Confirm deviations or explicitly record none.",
                )
            )
        status = (
            CompletenessStatus.BLOCKED
            if any(issue.blocks_routing for issue in issues)
            else CompletenessStatus.COMPLETE_WITH_WARNINGS
            if issues
            else CompletenessStatus.COMPLETE
        )
        assessment = SubmittalCompletenessAssessment(
            id=f"complete_{uuid4().hex}",
            package_id=package.id,
            package_revision=revision.revision,
            status=status,
            issues=tuple(issues),
            performed_by=actor,
            performed_at=self.clock(),
        )
        matrix = tuple(
            self._matrix_entry(requirement, revision)
            for requirement in requirements
            if requirement.evidence
        )
        self._save_package(
            package,
            completeness_assessments=package.completeness_assessments + (assessment,),
            compliance_matrix=matrix,
        )
        self._audit(
            project_id,
            "package",
            package.id,
            actor,
            "completeness_review_performed",
            None,
            status.value,
        )
        return assessment

    def override_matrix(
        self,
        project_id: str,
        package_id: str,
        requirement_id: str,
        status: MatrixStatus,
        actor: ActorReference,
        *,
        note: str,
    ) -> SubmittalPackage:
        package = self.get_package(project_id, package_id)
        entries = tuple(
            entry.model_copy(
                update={
                    "status": status,
                    "reviewer_note": note,
                    "confidence": "human_override",
                    "human_review_required": False,
                }
            )
            if entry.requirement_id == requirement_id
            else entry
            for entry in package.compliance_matrix
        )
        if entries == package.compliance_matrix:
            raise SubmittalNotFoundError("Compliance-matrix requirement not found")
        updated = self._save_package(package, compliance_matrix=entries)
        self._audit(
            project_id,
            "package",
            package.id,
            actor,
            "compliance_matrix_overridden",
            None,
            status.value,
            note,
        )
        return updated

    def submit_internal_review(
        self,
        project_id: str,
        package_id: str,
        reviewer: ReviewerReference,
        actor: ActorReference,
    ) -> SubmittalPackage:
        package = self.get_package(project_id, package_id)
        assessment = self._current_completeness(package)
        if assessment is None or assessment.status in {
            CompletenessStatus.BLOCKED,
            CompletenessStatus.INCOMPLETE,
        }:
            raise SubmittalTransitionError("A non-blocking completeness review is required")
        for item_id in package.register_item_ids:
            self.assign(project_id, item_id, actor, reviewer=reviewer)
            item = self.get_register(project_id, item_id)
            if item.status != SubmittalStatus.PENDING_INTERNAL_REVIEW:
                self._force_register_status(item, SubmittalStatus.PENDING_INTERNAL_REVIEW, actor)
        updated = self._save_package(
            package, internal_review_status=PackageReviewStatus.PENDING_INTERNAL_REVIEW
        )
        self._audit(
            project_id, "package", package.id, actor, "internal_review_submitted", None, reviewer.id
        )
        self._notify_for_package(
            updated,
            reviewer,
            NotificationType.ASSIGNMENT_CREATED,
            "Internal submittal review assigned",
        )
        return updated

    def internal_review(
        self,
        project_id: str,
        package_id: str,
        decision: InternalReviewDecision,
        reviewer: ReviewerReference,
        actor: ActorReference,
        *,
        comments: str | None = None,
        required_corrections: tuple[str, ...] = (),
    ) -> SubmittalPackage:
        package = self.get_package(project_id, package_id)
        if package.internal_review_status != PackageReviewStatus.PENDING_INTERNAL_REVIEW:
            raise SubmittalTransitionError("Package is not pending internal review")
        if decision != InternalReviewDecision.APPROVED_FOR_SUBMISSION and not comments:
            raise SubmittalValidationError("Non-approval decisions require comments")
        revision = package.revisions[-1]
        review = SubmittalInternalReview(
            id=f"intreview_{uuid4().hex}",
            package_revision=revision.revision,
            round_number=len(package.internal_reviews) + 1,
            reviewer=reviewer,
            decision=decision,
            comments=comments,
            required_corrections=required_corrections,
            reviewed_at=self.clock(),
            approved_content_hash=revision.content_hash
            if decision == InternalReviewDecision.APPROVED_FOR_SUBMISSION
            else None,
        )
        approved = decision == InternalReviewDecision.APPROVED_FOR_SUBMISSION
        revisions = package.revisions[:-1] + (
            revision.model_copy(update={"internally_approved": approved}),
        )
        target = (
            PackageReviewStatus.APPROVED_FOR_SUBMISSION
            if approved
            else PackageReviewStatus.REVISIONS_REQUIRED
        )
        register_target = (
            SubmittalStatus.READY_TO_SUBMIT
            if approved
            else SubmittalStatus.REVISIONS_REQUIRED_INTERNAL
        )
        updated = self._save_package(
            package,
            revisions=revisions,
            internal_reviews=package.internal_reviews + (review,),
            internal_review_status=target,
        )
        self._set_register_statuses(updated, register_target, actor)
        self._audit(
            project_id,
            "package",
            package.id,
            actor,
            "internal_review_decision",
            package.internal_review_status.value,
            target.value,
            comments,
        )
        return updated

    def issue_package(
        self, project_id: str, package_id: str, actor: ActorReference
    ) -> SubmittalPackage:
        package = self.get_package(project_id, package_id)
        revision = package.revisions[-1]
        if (
            package.internal_review_status != PackageReviewStatus.APPROVED_FOR_SUBMISSION
            or not revision.internally_approved
        ):
            raise SubmittalTransitionError(
                "Issue requires internal approval of the current revision"
            )
        issued = revision.model_copy(update={"issued_at": self.clock()})
        updated = self._save_package(
            package,
            revisions=package.revisions[:-1] + (issued,),
            internal_review_status=PackageReviewStatus.ISSUED,
        )
        self._set_register_statuses(
            updated, SubmittalStatus.UNDER_DESIGN_REVIEW, actor, submitted=True
        )
        self._audit(
            project_id, "package", package.id, actor, "package_issued", None, str(revision.revision)
        )
        return updated

    def record_response(
        self,
        project_id: str,
        package_id: str,
        actor: ActorReference,
        *,
        responding_organization: str,
        disposition: OfficialDisposition,
        original_disposition_text: str,
        review_comments: tuple[str, ...] = (),
        required_corrections: tuple[str, ...] = (),
        evidence: tuple[SubmittalEvidenceReference, ...] = (),
        responding_person: str | None = None,
        official: bool = True,
        supersedes_response_id: str | None = None,
    ) -> SubmittalPackage:
        package = self.get_package(project_id, package_id)
        if package.internal_review_status not in {
            PackageReviewStatus.ISSUED,
            PackageReviewStatus.RESPONSE_RECEIVED,
        }:
            raise SubmittalTransitionError("Responses may only be recorded after package issue")
        if disposition == OfficialDisposition.REVISE_AND_RESUBMIT and not required_corrections:
            raise SubmittalValidationError("Revise-and-resubmit requires corrections")
        response = SubmittalResponse(
            id=f"subresp_{uuid4().hex}",
            package_id=package.id,
            package_revision=package.current_revision,
            responding_organization=responding_organization,
            responding_person=responding_person,
            date_received=self.clock().date(),
            disposition=disposition,
            original_disposition_text=original_disposition_text,
            review_comments=review_comments,
            required_corrections=required_corrections,
            evidence=evidence,
            supersedes_response_id=supersedes_response_id,
            official=official,
            created_by=actor,
            created_at=self.clock(),
        )
        updated = self._save_package(
            package,
            official_responses=package.official_responses + (response,),
            official_review_status=disposition if official else package.official_review_status,
            internal_review_status=PackageReviewStatus.RESPONSE_RECEIVED
            if official
            else package.internal_review_status,
        )
        if official:
            target = DISPOSITION_STATUS[disposition]
            self._set_register_statuses(updated, target, actor, responded=True)
        self._audit(
            project_id,
            "package",
            package.id,
            actor,
            "official_response_recorded" if official else "informal_response_recorded",
            None,
            response.id,
            original_disposition_text,
        )
        reviewer = self._first_reviewer(project_id, package.register_item_ids)
        if official and reviewer:
            self._notify_for_package(
                updated,
                reviewer,
                NotificationType.STATUS_CHANGED,
                "Official submittal response recorded",
            )
        return updated

    def analyze_response(
        self, project_id: str, package_id: str, actor: ActorReference
    ) -> SubmittalResponseAnalysis:
        package = self.get_package(project_id, package_id)
        response = next(
            (item for item in reversed(package.official_responses) if item.official), None
        )
        if response is None:
            result = SubmittalResponseAnalysis()
        else:
            text = " ".join(
                (response.original_disposition_text,) + response.review_comments
            ).casefold()
            result = SubmittalResponseAnalysis(
                disposition=response.disposition,
                required_corrections=response.required_corrections,
                conditional_approval=response.disposition
                in {
                    OfficialDisposition.APPROVED_AS_NOTED,
                    OfficialDisposition.MAKE_CORRECTIONS_NOTED,
                },
                resubmittal_required=response.disposition
                == OfficialDisposition.REVISE_AND_RESUBMIT,
                procurement_release_eligible=response.disposition
                in {OfficialDisposition.APPROVED, OfficialDisposition.NO_EXCEPTION_TAKEN},
                potential_schedule_impact=any(
                    term in text for term in ("delay", "lead time", "schedule")
                ),
                related_rfi_need=any(term in text for term in ("clarify", "rfi")),
                field_use_restricted=any(
                    term in text for term in ("not for construction", "do not install")
                ),
                citations=response.evidence,
                official_response_id=response.id,
            )
        self._audit(
            project_id,
            "package",
            package.id,
            actor,
            "response_analyzed",
            None,
            result.disposition.value if result.disposition else "insufficient",
        )
        return result

    def resubmit(
        self, project_id: str, package_id: str, actor: ActorReference, *, change_summary: str
    ) -> SubmittalPackage:
        package = self.get_package(project_id, package_id)
        response = next(
            (item for item in reversed(package.official_responses) if item.official), None
        )
        if response is None or response.disposition not in {
            OfficialDisposition.REVISE_AND_RESUBMIT,
            OfficialDisposition.REJECTED,
            OfficialDisposition.NOT_REVIEWED,
        }:
            raise SubmittalTransitionError("Latest official response does not require resubmittal")
        updated = self.revise_package(
            project_id,
            package_id,
            actor,
            change_summary=change_summary,
            correction_checklist=response.required_corrections or response.review_comments,
        )
        self._audit(
            project_id,
            "package",
            package.id,
            actor,
            "resubmittal_created",
            str(package.current_revision),
            str(updated.current_revision),
            change_summary,
        )
        return updated

    def confirm_procurement_release(
        self,
        project_id: str,
        item_id: str,
        actor: ActorReference,
        *,
        corrections_incorporated: bool,
    ) -> SubmittalRegisterItem:
        item = self.get_register(project_id, item_id)
        if item.status not in {SubmittalStatus.APPROVED, SubmittalStatus.APPROVED_AS_NOTED}:
            raise SubmittalTransitionError("Procurement release requires an approved disposition")
        if item.status == SubmittalStatus.APPROVED_AS_NOTED and not corrections_incorporated:
            raise SubmittalTransitionError(
                "Approved-as-noted corrections require human confirmation before release"
            )
        procurement = item.procurement.model_copy(
            update={
                "procurement_release_date": self.clock().date(),
                "exposure_status": ProcurementExposureStatus.ON_TRACK,
            }
        )
        updated = self._save_register(
            item, status=SubmittalStatus.PROCUREMENT_RELEASED, procurement=procurement
        )
        self._audit(
            project_id,
            "register_item",
            item.id,
            actor,
            "procurement_release_confirmed",
            item.status.value,
            updated.status.value,
        )
        return updated

    def mark_stale(
        self,
        project_id: str,
        package_id: str,
        actor: ActorReference,
        *,
        reasons: tuple[str, ...],
        source_references: tuple[str, ...] = (),
        status: StalenessStatus = StalenessStatus.POTENTIALLY_STALE,
    ) -> SubmittalPackage:
        if not reasons:
            raise SubmittalValidationError("Staleness reasons are required")
        package = self.get_package(project_id, package_id)
        assessment = SubmittalStalenessAssessment(
            id=f"stale_{uuid4().hex}",
            status=status,
            reasons=reasons,
            source_references=source_references,
            assessed_by=actor,
            assessed_at=self.clock(),
        )
        updated = self._save_package(
            package, staleness_assessments=package.staleness_assessments + (assessment,)
        )
        if status != StalenessStatus.CURRENT:
            self._set_register_statuses(updated, SubmittalStatus.IN_PREPARATION, actor)
        self._audit(
            project_id,
            "package",
            package.id,
            actor,
            "package_marked_stale",
            None,
            status.value,
            "; ".join(reasons),
        )
        return updated

    def create_substitution(
        self,
        project_id: str,
        package_id: str,
        actor: ActorReference,
        substitution: SubstitutionRequest,
    ) -> SubmittalPackage:
        package = self.get_package(project_id, package_id)
        updated = self._save_package(package, substitution_request=substitution)
        self._audit(
            project_id,
            "package",
            package.id,
            actor,
            "substitution_requested",
            None,
            substitution.id,
            substitution.reason,
        )
        return updated

    def record_export(
        self, project_id: str, item_id: str, actor: ActorReference, format_name: str
    ) -> SubmittalRegisterItem:
        item = self.get_register(project_id, item_id)
        self._audit(
            project_id, "register_item", item.id, actor, "export_generated", None, format_name
        )
        return item

    def _register_from_candidate(
        self,
        candidate: SubmittalRequirementCandidate,
        actor: ActorReference,
        *,
        responsible_subcontractor: str | None,
    ) -> SubmittalRegisterItem:
        legacy = None
        if self.changes:
            legacy = next(
                (
                    related.id
                    for change in self.changes.list_changes(candidate.project_id)
                    for related in change.related_items
                    if related.workflow_type == WorkflowType.SUBMITTAL
                    and related.evidence.new_document_id == candidate.document_id
                ),
                None,
            )
        return self.create_register(
            project_id=candidate.project_id,
            specification_section=candidate.specification_section,
            description=candidate.description,
            actor=actor,
            requirements=(self._requirement(candidate),),
            discipline=candidate.discipline,
            responsible_subcontractor=responsible_subcontractor,
            legacy_related_item_id=legacy,
        )

    @staticmethod
    def _requirement(candidate: SubmittalRequirementCandidate) -> SubmittalRequirement:
        return SubmittalRequirement(
            id=f"req_{candidate.id.removeprefix('subreq_')}",
            candidate_id=candidate.id,
            specification_section=candidate.specification_section,
            paragraph_reference=candidate.paragraph_reference,
            submittal_type=candidate.submittal_type,
            category=candidate.category,
            description=candidate.description,
            required_documentation=candidate.required_documentation,
            evidence=(candidate.evidence,),
        )

    def _find_duplicate(
        self, project_id: str, candidate: SubmittalRequirementCandidate
    ) -> SubmittalRegisterItem | None:
        key = (
            candidate.specification_section.casefold(),
            (candidate.paragraph_reference or "").casefold(),
            candidate.submittal_type,
            (candidate.discipline or "").casefold(),
        )
        for item in self.repository.list_register(project_id):
            for requirement in item.requirements:
                other = (
                    requirement.specification_section.casefold(),
                    (requirement.paragraph_reference or "").casefold(),
                    requirement.submittal_type,
                    (item.discipline or "").casefold(),
                )
                if other == key:
                    return item
        return None

    def _link_related(self, item: SubmittalRegisterItem, actor: ActorReference) -> None:
        if self.changes:
            service = ProjectChangeService(self.changes)
            for change_id in item.related_project_change_ids:
                service.disposition(
                    item.project_id,
                    change_id,
                    ChangeDisposition.REQUIRES_SUBMITTAL,
                    actor,
                    "Canonical submittal register item created",
                )
                service.add_link(
                    item.project_id,
                    change_id,
                    WorkflowType.SUBMITTAL,
                    item.id,
                    RelationshipType.REQUIRES,
                    actor,
                )
                self._audit(
                    item.project_id,
                    "register_item",
                    item.id,
                    actor,
                    "project_change_linked",
                    None,
                    change_id,
                )
        if self.rfis:
            rfi_service = RFIService(self.rfis)
            for rfi_id in item.related_rfi_ids:
                rfi_service.link_submittal(item.project_id, rfi_id, item.id, actor)
                self._audit(
                    item.project_id, "register_item", item.id, actor, "rfi_linked", None, rfi_id
                )

    def _derive_procurement(
        self,
        *,
        required_on_site_date: date,
        fabrication_days: int,
        shipping_days: int = 0,
        processing_days: int = 0,
        review_days: int = 0,
        resubmittal_days: int = 0,
        buffer_days: int = 0,
    ) -> ProcurementDependency:
        latest_release = required_on_site_date - timedelta(
            days=fabrication_days + shipping_days + processing_days + buffer_days
        )
        latest_submit = latest_release - timedelta(days=review_days + resubmittal_days)
        today = self.clock().date()
        exposure = (
            ProcurementExposureStatus.OVERDUE
            if today > latest_submit
            else ProcurementExposureStatus.AT_RISK
            if today + timedelta(days=7) >= latest_submit
            else ProcurementExposureStatus.ON_TRACK
        )
        return ProcurementDependency(
            required_on_site_date=required_on_site_date,
            latest_acceptable_approval_date=latest_release,
            fabrication_lead_days=fabrication_days,
            shipping_days=shipping_days,
            procurement_processing_days=processing_days,
            review_duration_days=review_days,
            resubmittal_duration_days=resubmittal_days,
            buffer_days=buffer_days,
            derived_latest_release_date=latest_release,
            derived_latest_submit_date=latest_submit,
            long_lead=fabrication_days >= 84,
            exposure_status=exposure,
        )

    def _requirements(
        self, project_id: str, item_ids: tuple[str, ...]
    ) -> tuple[SubmittalRequirement, ...]:
        return tuple(
            requirement
            for item_id in item_ids
            for requirement in self.get_register(project_id, item_id).requirements
        )

    @staticmethod
    def _matrix_entry(
        requirement: SubmittalRequirement, revision: SubmittalPackageRevision
    ) -> ComplianceMatrixEntry:
        addressed = requirement.submittal_type in revision.included_types and any(
            item.document_type == requirement.submittal_type for item in revision.attachments
        )
        deviation = bool(revision.deviations)
        return ComplianceMatrixEntry(
            requirement_id=requirement.id,
            requirement_text=requirement.description,
            citation=requirement.evidence[0],
            submitted_evidence=tuple(
                item.filename
                for item in revision.attachments
                if item.document_type == requirement.submittal_type
            ),
            submitted_document_references=tuple(
                item.storage_reference for item in revision.attachments
            ),
            status=MatrixStatus.ADDRESSED
            if addressed
            else MatrixStatus.DEVIATION_DISCLOSED
            if deviation
            else MatrixStatus.NOT_ADDRESSED,
        )

    def _package_revision(
        self,
        *,
        revision: int,
        title: str,
        description: str,
        submitter: str,
        subcontractor: str | None,
        manufacturer: SubmittalManufacturer | None,
        product: SubmittalProduct | None,
        included_types: tuple[SubmittalType, ...],
        attachments: tuple[AttachmentMetadata, ...],
        deviations: tuple[str, ...],
        drawing_references: tuple[str, ...],
        related_rfi_ids: tuple[str, ...],
        related_project_change_ids: tuple[str, ...],
        evidence: tuple[SubmittalEvidenceReference, ...],
        actor: ActorReference,
        summary: str,
        correction_checklist: tuple[str, ...] = (),
    ) -> SubmittalPackageRevision:
        content = "\0".join(
            (
                title,
                description,
                submitter,
                ",".join(item.value for item in included_types),
                ",".join(item.id for item in attachments),
                ",".join(deviations),
                product.name if product else "",
                manufacturer.name if manufacturer else "",
            )
        )
        return SubmittalPackageRevision(
            revision=revision,
            title=title,
            description=description,
            submitter=submitter,
            responsible_subcontractor=subcontractor,
            manufacturer=manufacturer,
            product=product,
            included_types=included_types,
            attachments=attachments,
            deviations=deviations,
            drawing_references=drawing_references,
            related_rfi_ids=related_rfi_ids,
            related_project_change_ids=related_project_change_ids,
            evidence=evidence,
            correction_checklist=correction_checklist,
            content_hash=sha256(content.encode()).hexdigest(),
            created_by=actor,
            created_at=self.clock(),
            change_summary=summary,
        )

    @staticmethod
    def _cover_description(
        item: SubmittalRegisterItem, included_types: tuple[SubmittalType, ...]
    ) -> str:
        contents = (
            ", ".join(value.value.replace("_", " ") for value in included_types)
            or "no attachment types yet"
        )
        return (
            f"Submitted for review against Specification Section {item.specification_section}. "
            f"The package includes {contents}. Compliance has not yet been confirmed."
        )

    def _validate_closure(self, item: SubmittalRegisterItem) -> None:
        if not item.package_ids:
            raise SubmittalTransitionError("Closure requires a final package")
        package = self.get_package(item.project_id, item.package_ids[-1])
        if package.official_review_status not in {
            OfficialDisposition.APPROVED,
            OfficialDisposition.APPROVED_AS_NOTED,
            OfficialDisposition.NO_EXCEPTION_TAKEN,
            OfficialDisposition.MAKE_CORRECTIONS_NOTED,
            OfficialDisposition.INFORMATIONAL_ONLY,
            OfficialDisposition.REVIEWED,
        }:
            raise SubmittalTransitionError(
                "Closure requires an approved or accepted official disposition"
            )
        if package.staleness_assessments and package.staleness_assessments[-1].status in {
            StalenessStatus.POTENTIALLY_STALE,
            StalenessStatus.STALE,
            StalenessStatus.REVIEW_REQUIRED,
        }:
            raise SubmittalTransitionError(
                "Potentially stale packages require human review before closure"
            )

    def _set_register_statuses(
        self,
        package: SubmittalPackage,
        status: SubmittalStatus,
        actor: ActorReference,
        *,
        submitted: bool = False,
        responded: bool = False,
    ) -> None:
        for item_id in package.register_item_ids:
            item = self.get_register(package.project_id, item_id)
            updated = self._save_register(
                item,
                status=status,
                actual_submit_date=self.clock().date() if submitted else item.actual_submit_date,
                actual_response_date=self.clock().date()
                if responded
                else item.actual_response_date,
            )
            self._audit(
                package.project_id,
                "register_item",
                item.id,
                actor,
                "status_transition",
                item.status.value,
                updated.status.value,
            )
            if updated.internal_reviewer:
                self._notify(
                    updated,
                    updated.internal_reviewer,
                    NotificationType.STATUS_CHANGED,
                    f"Submittal status: {updated.status.value.replace('_', ' ')}",
                )

    def _force_register_status(
        self, item: SubmittalRegisterItem, status: SubmittalStatus, actor: ActorReference
    ) -> SubmittalRegisterItem:
        updated = self._save_register(item, status=status)
        self._audit(
            item.project_id,
            "register_item",
            item.id,
            actor,
            "status_transition",
            item.status.value,
            status.value,
        )
        return updated

    def _save_register(self, item: SubmittalRegisterItem, **values: Any) -> SubmittalRegisterItem:
        updated = item.model_copy(
            update={**values, "version": item.version + 1, "updated_at": self.clock()}
        )
        self.repository.save_register(updated, expected_version=item.version)
        return updated

    def _save_package(self, package: SubmittalPackage, **values: Any) -> SubmittalPackage:
        updated = package.model_copy(
            update={**values, "version": package.version + 1, "updated_at": self.clock()}
        )
        self.repository.save_package(updated, expected_version=package.version)
        return updated

    @staticmethod
    def _current_completeness(
        package: SubmittalPackage,
    ) -> SubmittalCompletenessAssessment | None:
        return next(
            (
                item
                for item in reversed(package.completeness_assessments)
                if item.package_revision == package.current_revision
            ),
            None,
        )

    def _first_reviewer(
        self, project_id: str, item_ids: tuple[str, ...]
    ) -> ReviewerReference | None:
        return next(
            (
                item.internal_reviewer
                for item_id in item_ids
                if (item := self.get_register(project_id, item_id)).internal_reviewer
            ),
            None,
        )

    def _notify(
        self,
        item: SubmittalRegisterItem,
        recipient: ReviewerReference,
        notification_type: NotificationType,
        title: str,
    ) -> None:
        if not self.changes:
            return
        NotificationOutboxService(self.changes).queue(
            NotificationRequest(
                id="pending",
                project_id=item.project_id,
                change_id=item.related_project_change_ids[0]
                if item.related_project_change_ids
                else item.id,
                event_id=f"{item.id}:{item.version}:{notification_type.value}",
                recipient=recipient,
                notification_type=notification_type,
                created_at=self.clock(),
                payload={
                    "title": title,
                    "status": item.status.value,
                    "due_date": item.required_response_date.isoformat()
                    if item.required_response_date
                    else "",
                },
            )
        )

    def _notify_for_package(
        self,
        package: SubmittalPackage,
        recipient: ReviewerReference,
        notification_type: NotificationType,
        title: str,
    ) -> None:
        self._notify(
            self.get_register(package.project_id, package.register_item_ids[0]),
            recipient,
            notification_type,
            title,
        )

    def _audit(
        self,
        project_id: str,
        entity_type: str,
        entity_id: str,
        actor: ActorReference,
        event_type: str,
        previous: str | None,
        new: str | None,
        reason: str | None = None,
    ) -> None:
        self.repository.append_audit(
            SubmittalAuditEvent(
                id=f"subaudit_{uuid4().hex}",
                project_id=project_id,
                entity_type=entity_type,
                entity_id=entity_id,
                event_type=event_type,
                actor=actor,
                timestamp=self.clock(),
                previous_state=previous,
                new_state=new,
                reason=reason,
            )
        )
