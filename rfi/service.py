"""RFI lifecycle, project-change integration, response analysis, and audit."""

from collections.abc import Callable
from datetime import UTC, date, datetime
from hashlib import sha256
from typing import Any
from uuid import uuid4

from change_workflow.models import (
    ActorReference,
    ChangeDisposition,
    ChangeStatus,
    ImpactCertainty,
    NotificationRequest,
    NotificationType,
    RelationshipType,
    ReviewerReference,
    WorkflowType,
)
from change_workflow.notifications import NotificationOutboxService
from change_workflow.repository import JsonChangeWorkflowRepository
from change_workflow.service import ProjectChangeService
from .drafting import (
    DeterministicRFIDrafter,
    DocumentEvidenceReader,
    RFIDraftProvider,
    RFIDuplicateDetector,
    RFIQualityValidator,
)
from .errors import RFIDraftingError, RFINotFoundError, RFITransitionError
from .models import (
    RFI,
    RFIAuditEvent,
    RFIDraftResult,
    RFIEvidenceReference,
    RFIImpactType,
    RFIImpactAssessment,
    RFIResponse,
    RFIResponseAnalysis,
    RFIResponseType,
    RFIReview,
    RFIReviewDecision,
    RFIRevision,
    RFIStatus,
    RFIStatusHistory,
)
from .numbering import ProjectRFINumberingService, RFINumberingService
from .repository import JsonRFIRepository

TRANSITIONS = {
    RFIStatus.DRAFT: {RFIStatus.PENDING_INTERNAL_REVIEW, RFIStatus.VOID, RFIStatus.SUPERSEDED},
    RFIStatus.PENDING_INTERNAL_REVIEW: {RFIStatus.REVISIONS_REQUIRED, RFIStatus.APPROVED_FOR_ISSUE},
    RFIStatus.REVISIONS_REQUIRED: {RFIStatus.PENDING_INTERNAL_REVIEW, RFIStatus.VOID},
    RFIStatus.APPROVED_FOR_ISSUE: {RFIStatus.ISSUED},
    RFIStatus.ISSUED: {
        RFIStatus.ACKNOWLEDGED,
        RFIStatus.UNDER_REVIEW,
        RFIStatus.RESPONSE_RECEIVED,
        RFIStatus.SUPERSEDED,
    },
    RFIStatus.ACKNOWLEDGED: {RFIStatus.UNDER_REVIEW, RFIStatus.RESPONSE_RECEIVED},
    RFIStatus.UNDER_REVIEW: {RFIStatus.RESPONSE_RECEIVED},
    RFIStatus.RESPONSE_RECEIVED: {RFIStatus.CLARIFICATION_REQUIRED, RFIStatus.ANSWERED},
    RFIStatus.CLARIFICATION_REQUIRED: {RFIStatus.UNDER_REVIEW, RFIStatus.RESPONSE_RECEIVED},
    RFIStatus.ANSWERED: {RFIStatus.RESOLVED, RFIStatus.CLOSED},
    RFIStatus.RESOLVED: {RFIStatus.CLOSED, RFIStatus.UNDER_REVIEW},
    RFIStatus.CLOSED: {RFIStatus.UNDER_REVIEW},
    RFIStatus.VOID: set(),
    RFIStatus.SUPERSEDED: set(),
}


class RFIService:
    def __init__(
        self,
        repository: JsonRFIRepository,
        changes: JsonChangeWorkflowRepository | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
        provider: RFIDraftProvider | None = None,
        numbering: RFINumberingService | None = None,
        duplicate_threshold: float = 0.72,
        assign_number_at_creation: bool = True,
        documents: DocumentEvidenceReader | None = None,
    ) -> None:
        self.repository = repository
        self.changes = changes
        self.clock = clock or (lambda: datetime.now(UTC))
        self.provider = provider
        self.numbering = numbering or ProjectRFINumberingService(repository)
        self.assign_number_at_creation = assign_number_at_creation
        self.drafter = DeterministicRFIDrafter(documents)
        self.quality = RFIQualityValidator()
        self.duplicates = RFIDuplicateDetector(duplicate_threshold)

    def create(
        self,
        *,
        project_id: str,
        subject: str,
        question: str,
        actor: ActorReference,
        background: str = "",
        evidence: tuple[RFIEvidenceReference, ...] = (),
        responsible_party: str | None = None,
        required_date: date | None = None,
        related_change_ids: tuple[str, ...] = (),
        legacy_related_item_id: str | None = None,
    ) -> RFI:
        now = self.clock()
        number = self.numbering.next_number(project_id) if self.assign_number_at_creation else None
        identity = (
            sha256(f"{project_id}{number}".encode()).hexdigest()[:20]
            if number
            else uuid4().hex[:20]
        )
        rfi = RFI(
            id=f"rfi_{identity}",
            project_id=project_id,
            number=number or f"UNASSIGNED-{identity[:8]}",
            subject=subject,
            question=question,
            background=background,
            evidence=evidence,
            created_by=actor,
            responsible_party=responsible_party,
            required_date=required_date,
            related_project_change_ids=related_change_ids,
            created_at=now,
            updated_at=now,
            legacy_related_item_id=legacy_related_item_id,
        )
        rfi = self._revision(rfi, actor, "Initial draft")
        self.repository.save(rfi)
        self._audit(rfi, actor, "rfi_created", None, rfi.status.value)
        return rfi

    def override_number(
        self,
        project_id: str,
        rfi_id: str,
        number: str,
        actor: ActorReference,
        *,
        reason: str,
    ) -> RFI:
        """Administrative draft-only override; issued numbering is immutable."""
        item = self.get(project_id, rfi_id)
        if item.status != RFIStatus.DRAFT:
            raise RFITransitionError("RFI number is stable after internal review begins")
        if not reason.strip():
            raise RFITransitionError("Administrative override reason is required")
        if any(
            other.number == number and other.id != item.id
            for other in self.repository.list(project_id)
        ):
            raise RFITransitionError("RFI number is already in use for this project")
        updated = self._save(item, number=number)
        self._audit(updated, actor, "number_overridden", item.number, number, reason)
        return updated

    def draft_from_change(
        self,
        project_id: str,
        change_id: str,
        actor: ActorReference,
        *,
        instructions: str | None = None,
        responsible_party: str | None = None,
        required_date: date | None = None,
        use_model: bool = False,
        selected_evidence: tuple[RFIEvidenceReference, ...] = (),
    ) -> RFIDraftResult:
        if self.changes is None:
            raise RFIDraftingError("Project change repository is required")
        change = ProjectChangeService(self.changes).get(project_id, change_id)
        fields = self.drafter.draft_fields(change, instructions, selected_evidence)
        if not fields[3]:
            raise RFIDraftingError("Selected project change has insufficient cited evidence")
        rfi = self.create(
            project_id=project_id,
            subject=fields[0],
            question=fields[1],
            background=fields[2],
            evidence=fields[3],
            actor=actor,
            responsible_party=responsible_party,
            required_date=required_date,
            related_change_ids=(change_id,),
            legacy_related_item_id=next(
                (x.id for x in change.related_items if x.workflow_type.value == "rfi"), None
            ),
        )
        self._audit(rfi, actor, "rfi_drafted_from_evidence", change_id, rfi.id)
        warnings = []
        provider = "deterministic"
        if use_model:
            if self.provider is None:
                warnings.append(
                    "Model drafting requested but no provider configured; deterministic draft retained."
                )
            else:
                try:
                    rfi = self.provider.improve(rfi)
                    provider = self.provider.name
                except Exception as exc:
                    warnings.append(
                        f"Model drafting failed safely ({type(exc).__name__}); deterministic draft retained."
                    )
        quality = self.quality.assess(rfi)
        duplicates = self.duplicates.assess(
            rfi, tuple(x for x in self.repository.list(project_id) if x.id != rfi.id)
        )
        change_service = ProjectChangeService(self.changes)
        change_service.disposition(
            project_id,
            change_id,
            ChangeDisposition.REQUIRES_RFI,
            actor,
            "RFI draft created from project change",
        )
        change_service.add_link(
            project_id,
            change_id,
            WorkflowType.RFI,
            rfi.id,
            RelationshipType.REQUIRES,
            actor,
        )
        self._audit(rfi, actor, "related_record_linked", change_id, rfi.id)
        return RFIDraftResult(
            rfi=rfi,
            quality=quality,
            duplicates=duplicates,
            provider=provider,
            warnings=tuple(warnings),
        )

    def get(self, project_id: str, rfi_id: str) -> RFI:
        item = self.repository.get(project_id, rfi_id)
        if item is None:
            raise RFINotFoundError("RFI not found")
        return item

    def assign_reviewer(
        self, project_id: str, rfi_id: str, reviewer: ReviewerReference, actor: ActorReference
    ) -> RFI:
        item = self.get(project_id, rfi_id)
        updated = self._save(item, assigned_reviewer=reviewer)
        self._audit(updated, actor, "reviewer_assigned", None, reviewer.id)
        self._notify(updated, reviewer, NotificationType.ASSIGNMENT_CREATED, "RFI review assigned")
        return updated

    def transition(
        self,
        project_id: str,
        rfi_id: str,
        status: RFIStatus,
        actor: ActorReference,
        *,
        reason: str | None = None,
        resolution: str | None = None,
    ) -> RFI:
        item = self.get(project_id, rfi_id)
        if status not in TRANSITIONS[item.status]:
            raise RFITransitionError(f"Cannot transition {item.status.value} to {status.value}")
        if status == RFIStatus.PENDING_INTERNAL_REVIEW and not item.assigned_reviewer:
            raise RFITransitionError("Reviewer is required")
        if status == RFIStatus.RESPONSE_RECEIVED and not item.responses:
            raise RFITransitionError("Response received requires recorded response evidence")
        if status == RFIStatus.ISSUED:
            quality = self.quality.assess(item)
            if not quality.valid or not item.responsible_party or not item.required_date:
                raise RFITransitionError(
                    "Issuing requires valid question, evidence, responsible party, and required date"
                )
        if (
            status in {RFIStatus.REVISIONS_REQUIRED, RFIStatus.VOID, RFIStatus.SUPERSEDED}
            and not reason
        ):
            raise RFITransitionError("Reason is required")
        if status in {RFIStatus.RESOLVED, RFIStatus.CLOSED} and not (
            resolution or item.resolution_summary
        ):
            raise RFITransitionError("Resolution summary is required")
        if item.status == RFIStatus.CLOSED and status == RFIStatus.UNDER_REVIEW and not reason:
            raise RFITransitionError("Reopening a closed RFI requires a reason")
        if status == RFIStatus.CLOSED and self.changes is not None:
            unresolved = [
                change_id
                for change_id in item.related_project_change_ids
                if ProjectChangeService(self.changes).get(project_id, change_id).status
                not in {ChangeStatus.RESOLVED, ChangeStatus.CLOSED}
            ]
            if unresolved:
                raise RFITransitionError(
                    "Related project changes must be resolved or closed before RFI closure: "
                    + ", ".join(unresolved)
                )
        now = self.clock()
        history = RFIStatusHistory(
            id=f"hist_{uuid4().hex}",
            previous_status=item.status,
            new_status=status,
            actor=actor,
            timestamp=now,
            reason=reason,
        )
        values: dict[str, Any] = {
            "status": status,
            "status_history": item.status_history + (history,),
            "resolution_summary": resolution or item.resolution_summary,
        }
        if status == RFIStatus.ISSUED:
            values["issued_at"] = now
            if item.number.startswith("UNASSIGNED-"):
                values["number"] = self.numbering.next_number(project_id)
        if status == RFIStatus.ANSWERED:
            values["answered_at"] = now
        if status == RFIStatus.RESOLVED:
            values["resolved_at"] = now
        if status == RFIStatus.CLOSED:
            values["closed_at"] = now
        updated = self._save(item, **values)
        self._audit(updated, actor, "status_transition", item.status.value, status.value, reason)
        if status == RFIStatus.ISSUED and updated.number != item.number:
            self._audit(updated, actor, "number_assigned", item.number, updated.number)
        if updated.assigned_reviewer is not None:
            self._notify(
                updated,
                updated.assigned_reviewer,
                NotificationType.STATUS_CHANGED,
                "RFI status changed",
            )
        return updated

    def review(
        self,
        project_id: str,
        rfi_id: str,
        decision: RFIReviewDecision,
        reviewer: ReviewerReference,
        actor: ActorReference,
        comments: str | None = None,
    ) -> RFI:
        item = self.get(project_id, rfi_id)
        if item.status != RFIStatus.PENDING_INTERNAL_REVIEW:
            raise RFITransitionError("RFI is not pending review")
        if decision != RFIReviewDecision.APPROVED and not comments:
            raise RFITransitionError("Reviewer comments are required")
        review = RFIReview(
            id=f"review_{uuid4().hex}",
            reviewer=reviewer,
            decision=decision,
            comments=comments,
            created_at=self.clock(),
            revision_number=item.revisions[-1].number,
        )
        target = (
            RFIStatus.APPROVED_FOR_ISSUE
            if decision == RFIReviewDecision.APPROVED
            else RFIStatus.REVISIONS_REQUIRED
        )
        revisions = item.revisions
        if decision == RFIReviewDecision.APPROVED:
            revisions = revisions[:-1] + (revisions[-1].model_copy(update={"approved": True}),)
        history = RFIStatusHistory(
            id=f"hist_{uuid4().hex}",
            previous_status=item.status,
            new_status=target,
            actor=actor,
            timestamp=self.clock(),
            reason=comments,
        )
        updated = self._save(
            item,
            reviews=item.reviews + (review,),
            revisions=revisions,
            status=target,
            status_history=item.status_history + (history,),
        )
        self._audit(updated, actor, "review_decision", item.status.value, target.value, comments)
        return updated

    def revise(
        self,
        project_id: str,
        rfi_id: str,
        actor: ActorReference,
        *,
        subject: str | None = None,
        question: str | None = None,
        background: str | None = None,
        summary: str,
    ) -> RFI:
        item = self.get(project_id, rfi_id)
        updated = item.model_copy(
            update={
                "subject": subject or item.subject,
                "question": question or item.question,
                "background": background or item.background,
                "status": RFIStatus.DRAFT,
            }
        )
        updated = self._revision(updated, actor, summary)
        updated = self._save(
            item,
            subject=updated.subject,
            question=updated.question,
            background=updated.background,
            status=updated.status,
            revisions=updated.revisions,
        )
        self._audit(
            updated,
            actor,
            "revision_created",
            str(item.revisions[-1].number),
            str(updated.revisions[-1].number),
            summary,
        )
        return updated

    def record_response(
        self,
        project_id: str,
        rfi_id: str,
        actor: ActorReference,
        *,
        text: str,
        responding_party: str,
        response_type: RFIResponseType = RFIResponseType.OFFICIAL,
        citations: tuple[RFIEvidenceReference, ...] = (),
    ) -> RFI:
        item = self.get(project_id, rfi_id)
        if item.status not in {
            RFIStatus.ISSUED,
            RFIStatus.ACKNOWLEDGED,
            RFIStatus.UNDER_REVIEW,
            RFIStatus.CLARIFICATION_REQUIRED,
            RFIStatus.RESPONSE_RECEIVED,
        }:
            raise RFITransitionError("Responses may only be recorded after issue")
        now = self.clock()
        response = RFIResponse(
            id=f"resp_{uuid4().hex}",
            response_type=response_type,
            responding_party=responding_party,
            response_date=now.date(),
            text=text,
            citations=citations,
            created_by=actor,
            created_at=now,
        )
        status = (
            RFIStatus.RESPONSE_RECEIVED
            if response_type == RFIResponseType.OFFICIAL
            else item.status
        )
        history = item.status_history
        if status != item.status:
            history += (
                RFIStatusHistory(
                    id=f"hist_{uuid4().hex}",
                    previous_status=item.status,
                    new_status=status,
                    actor=actor,
                    timestamp=now,
                    reason="Official response recorded",
                ),
            )
        updated = self._save(
            item,
            responses=item.responses + (response,),
            status=status,
            status_history=history,
        )
        self._audit(updated, actor, "response_recorded", None, response.id, response_type.value)
        if response_type == RFIResponseType.OFFICIAL and updated.assigned_reviewer is not None:
            self._notify(
                updated,
                updated.assigned_reviewer,
                NotificationType.INFORMATION_REQUESTED,
                "Official RFI response recorded",
            )
        return updated

    def add_impact(
        self,
        project_id: str,
        rfi_id: str,
        actor: ActorReference,
        *,
        impact_type: RFIImpactType,
        certainty: ImpactCertainty,
        description: str,
        evidence: tuple[RFIEvidenceReference, ...] = (),
    ) -> RFI:
        """Record an explicitly human-assessed potential or confirmed impact."""
        item = self.get(project_id, rfi_id)
        impact = RFIImpactAssessment(
            impact_type=impact_type,
            certainty=certainty,
            description=description,
            identified_by=actor,
            created_at=self.clock(),
            evidence=evidence,
        )
        updated = self._save(item, impacts=item.impacts + (impact,))
        self._audit(updated, actor, "impact_recorded", None, impact_type.value, description)
        return updated

    def analyze_response(
        self, project_id: str, rfi_id: str, actor: ActorReference | None = None
    ) -> RFIResponseAnalysis:
        item = self.get(project_id, rfi_id)
        official = next(
            (x for x in reversed(item.responses) if x.response_type == RFIResponseType.OFFICIAL),
            None,
        )
        if official is None:
            result = RFIResponseAnalysis(
                complete=False,
                addressed_question=False,
                explanation="No official response is recorded.",
            )
            self._audit(
                item,
                actor or ActorReference(id="brunel", display_name="Brunel"),
                "response_analyzed",
                None,
                "insufficient",
            )
            return result
        text = official.text.casefold()
        impacts = tuple(
            kind
            for kind, terms in (
                (RFIImpactType.PROCUREMENT, ("procurement", "lead time")),
                (RFIImpactType.SCHEDULE, ("schedule", "delay")),
                (RFIImpactType.COST, ("cost", "price")),
            )
            if any(term in text for term in terms)
        )
        result = RFIResponseAnalysis(
            complete=len(official.text.split()) >= 3,
            addressed_question=True,
            potential_impacts=impacts,
            may_resolve_project_change=True,
            explanation="Official response is present; potential impacts are keyword inferences requiring human review.",
        )
        self._audit(
            item,
            actor or ActorReference(id="brunel", display_name="Brunel"),
            "response_analyzed",
            None,
            "complete" if result.complete else "partial",
            result.explanation,
        )
        return result

    def record_export(
        self, project_id: str, rfi_id: str, actor: ActorReference, format_name: str
    ) -> RFI:
        item = self.get(project_id, rfi_id)
        self._audit(item, actor, "export_generated", None, format_name)
        return item

    def link_submittal(
        self,
        project_id: str,
        rfi_id: str,
        submittal_id: str,
        actor: ActorReference,
    ) -> RFI:
        """Add a canonical submittal backlink without changing RFI resolution state."""
        item = self.get(project_id, rfi_id)
        if submittal_id in item.related_submittal_ids:
            return item
        updated = self._save(
            item,
            related_submittal_ids=item.related_submittal_ids + (submittal_id,),
        )
        self._audit(updated, actor, "submittal_linked", None, submittal_id)
        return updated

    def _revision(self, rfi: RFI, actor: ActorReference, summary: str) -> RFI:
        number = len(rfi.revisions) + 1
        content = (
            f"{rfi.subject}\0{rfi.question}\0{rfi.background}\0{rfi.suggested_resolution or ''}"
        )
        revision = RFIRevision(
            number=number,
            subject=rfi.subject,
            question=rfi.question,
            background=rfi.background,
            suggested_resolution=rfi.suggested_resolution,
            evidence=rfi.evidence,
            created_by=actor,
            created_at=self.clock(),
            change_summary=summary,
            content_hash=sha256(content.encode()).hexdigest(),
        )
        return rfi.model_copy(update={"revisions": rfi.revisions + (revision,)})

    def _save(self, item: RFI, **values: Any) -> RFI:
        updated = item.model_copy(
            update={**values, "version": item.version + 1, "updated_at": self.clock()}
        )
        self.repository.save(updated, expected_version=item.version)
        return updated

    def _audit(
        self,
        item: RFI,
        actor: ActorReference,
        event_type: str,
        previous: str | None,
        new: str | None,
        reason: str | None = None,
    ) -> None:
        self.repository.append_audit(
            RFIAuditEvent(
                id=f"rfiaudit_{uuid4().hex}",
                project_id=item.project_id,
                rfi_id=item.id,
                event_type=event_type,
                actor=actor,
                timestamp=self.clock(),
                previous_state=previous,
                new_state=new,
                reason=reason,
            )
        )

    def _notify(
        self,
        item: RFI,
        recipient: ReviewerReference,
        notification_type: NotificationType,
        title: str,
    ) -> None:
        if self.changes is None:
            return
        event_id = f"{item.id}:{item.version}:{notification_type.value}"
        NotificationOutboxService(self.changes).queue(
            NotificationRequest(
                id="pending",
                project_id=item.project_id,
                change_id=item.related_project_change_ids[0]
                if item.related_project_change_ids
                else item.id,
                event_id=event_id,
                recipient=recipient,
                notification_type=notification_type,
                created_at=self.clock(),
                payload={
                    "title": title,
                    "status": item.status.value,
                    "due_date": item.required_date.isoformat() if item.required_date else "",
                },
            )
        )
