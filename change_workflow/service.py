"""Controlled operational workflow services; all mutations are audited."""

from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any
from hashlib import sha256
from uuid import uuid4

from revision_intelligence.models import ChangeSeverity, DocumentChange, DocumentComparison

from .admission import ChangeAdmissionService
from .errors import ChangeNotFoundError, InvalidTransitionError
from .models import (
    ActorReference,
    AuditEvent,
    AuditEventType,
    ChangeAssignment,
    ChangeDisposition,
    ChangeEvidenceReference,
    ChangeNote,
    ChangeOrigin,
    ChangePriority,
    ChangeStatus,
    ChangeWorkflowLink,
    DispositionRecord,
    ImpactCertainty,
    NoteType,
    ProjectChange,
    RegisterGenerationResult,
    RelatedItem,
    RelatedItemStatus,
    RelationshipType,
    ReviewerReference,
    WorkflowType,
)
from .repository import JsonChangeWorkflowRepository

TRANSITIONS: dict[ChangeStatus, set[ChangeStatus]] = {
    ChangeStatus.NEW: {ChangeStatus.UNREVIEWED, ChangeStatus.ASSIGNED, ChangeStatus.CANCELLED},
    ChangeStatus.UNREVIEWED: {ChangeStatus.ASSIGNED, ChangeStatus.CANCELLED},
    ChangeStatus.ASSIGNED: {ChangeStatus.UNDER_REVIEW, ChangeStatus.UNREVIEWED},
    ChangeStatus.UNDER_REVIEW: {
        ChangeStatus.NEEDS_INFORMATION,
        ChangeStatus.ACTION_REQUIRED,
        ChangeStatus.ACCEPTED,
        ChangeStatus.REJECTED,
    },
    ChangeStatus.NEEDS_INFORMATION: {ChangeStatus.UNDER_REVIEW, ChangeStatus.CANCELLED},
    ChangeStatus.ACTION_REQUIRED: {ChangeStatus.RESOLVED, ChangeStatus.NEEDS_INFORMATION},
    ChangeStatus.ACCEPTED: {ChangeStatus.ACTION_REQUIRED, ChangeStatus.RESOLVED},
    ChangeStatus.REJECTED: {ChangeStatus.CLOSED, ChangeStatus.UNDER_REVIEW},
    ChangeStatus.RESOLVED: {ChangeStatus.CLOSED, ChangeStatus.UNDER_REVIEW},
    ChangeStatus.CLOSED: {ChangeStatus.UNDER_REVIEW},
    ChangeStatus.SUPERSEDED: set(),
    ChangeStatus.CANCELLED: set(),
}


class ProjectChangeService:
    def __init__(
        self,
        repository: JsonChangeWorkflowRepository,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.clock = clock or (lambda: datetime.now(UTC))

    def generate_register(
        self, comparison: DocumentComparison, actor: ActorReference
    ) -> RegisterGenerationResult:
        admission = ChangeAdmissionService()
        decisions = tuple(admission.evaluate(item) for item in comparison.changes)
        existing = {
            item.evidence.finding_id: item
            for item in self.repository.list_changes(comparison.project_id)
            if item.evidence.comparison_id == comparison.id
        }
        ids: list[str] = []
        reused = 0
        for finding, decision in zip(comparison.changes, decisions, strict=True):
            if not decision.admitted:
                continue
            if finding.id in existing:
                ids.append(existing[finding.id].id)
                reused += 1
                continue
            change = self._from_finding(comparison, finding)
            self.repository.save_change(change)
            self._audit(
                change,
                actor,
                AuditEventType.CHANGE_CREATED,
                None,
                change.status.value,
                ", ".join(decision.reasons),
            )
            ids.append(change.id)
        return RegisterGenerationResult(
            comparison_id=comparison.id,
            evaluated=len(decisions),
            admitted=sum(item.admitted for item in decisions),
            excluded=sum(not item.admitted for item in decisions),
            reused=reused,
            change_ids=tuple(ids),
            decisions=decisions,
        )

    def get(self, project_id: str, change_id: str) -> ProjectChange:
        item = self.repository.get_change(project_id, change_id)
        if item is None:
            raise ChangeNotFoundError("Project change not found")
        return item

    def assign(
        self,
        project_id: str,
        change_id: str,
        reviewer: ReviewerReference,
        actor: ActorReference,
        *,
        due_date: date | None = None,
        note: str | None = None,
    ) -> ProjectChange:
        item = self.get(project_id, change_id)
        now = self.clock()
        assignments = tuple(
            a.model_copy(update={"active": False})
            for a in item.assignments
            if a.primary and a.active
        ) + tuple(a for a in item.assignments if not (a.primary and a.active))
        assignment = ChangeAssignment(
            assignee=reviewer, assigned_by=actor, assigned_at=now, due_date=due_date, note=note
        )
        status = (
            ChangeStatus.ASSIGNED
            if item.status in {ChangeStatus.NEW, ChangeStatus.UNREVIEWED}
            else item.status
        )
        updated = self._save(item, assignments=assignments + (assignment,), status=status)
        self._audit(updated, actor, AuditEventType.ASSIGNMENT_CHANGED, None, reviewer.id, note)
        return updated

    def unassign(
        self,
        project_id: str,
        change_id: str,
        actor: ActorReference,
        *,
        reason: str | None = None,
    ) -> ProjectChange:
        item = self.get(project_id, change_id)
        if not any(assignment.active for assignment in item.assignments):
            return item
        assignments = tuple(
            assignment.model_copy(update={"active": False}) if assignment.active else assignment
            for assignment in item.assignments
        )
        status = ChangeStatus.UNREVIEWED if item.status == ChangeStatus.ASSIGNED else item.status
        updated = self._save(item, assignments=assignments, status=status)
        self._audit(
            updated,
            actor,
            AuditEventType.ASSIGNMENT_CHANGED,
            "assigned",
            "unassigned",
            reason,
        )
        return updated

    def transition(
        self,
        project_id: str,
        change_id: str,
        status: ChangeStatus,
        actor: ActorReference,
        *,
        reason: str | None = None,
        resolution: str | None = None,
        stale_acknowledged: bool = False,
    ) -> ProjectChange:
        item = self.get(project_id, change_id)
        if status not in TRANSITIONS[item.status]:
            raise InvalidTransitionError(f"Cannot transition {item.status.value} to {status.value}")
        if status == ChangeStatus.UNDER_REVIEW and not any(a.active for a in item.assignments):
            raise InvalidTransitionError("An active assignment is required")
        if (
            status
            in {
                ChangeStatus.REJECTED,
                ChangeStatus.NEEDS_INFORMATION,
                ChangeStatus.CANCELLED,
                ChangeStatus.SUPERSEDED,
            }
            and not reason
        ):
            raise InvalidTransitionError("A reason is required")
        if status in {ChangeStatus.RESOLVED, ChangeStatus.CLOSED} and not (
            resolution or item.resolution_summary
        ):
            raise InvalidTransitionError("A resolution summary is required")
        if status == ChangeStatus.CLOSED and item.disposition == ChangeDisposition.UNRESOLVED:
            raise InvalidTransitionError("A disposition is required before closure")
        if (
            status == ChangeStatus.CLOSED
            and item.source_stale
            and not (stale_acknowledged or item.stale_acknowledged)
        ):
            raise InvalidTransitionError("Stale source must be acknowledged before closure")
        now = self.clock()
        values: dict[str, Any] = {
            "status": status,
            "resolution_summary": resolution or item.resolution_summary,
            "stale_acknowledged": stale_acknowledged or item.stale_acknowledged,
        }
        if status == ChangeStatus.RESOLVED:
            values["resolved_at"] = now
        if status == ChangeStatus.CLOSED:
            values["closed_at"] = now
        updated = self._save(item, **values)
        self._audit(
            updated,
            actor,
            AuditEventType.STATUS_TRANSITION,
            item.status.value,
            status.value,
            reason,
        )
        return updated

    def add_note(
        self,
        project_id: str,
        change_id: str,
        text: str,
        actor: ActorReference,
        note_type: NoteType = NoteType.GENERAL,
    ) -> ProjectChange:
        item = self.get(project_id, change_id)
        now = self.clock()
        note = ChangeNote(
            id=f"note_{sha256(f'{change_id}{now.isoformat()}{text}'.encode()).hexdigest()[:16]}",
            author=actor,
            created_at=now,
            text=text,
            note_type=note_type,
        )
        updated = self._save(item, notes=item.notes + (note,))
        self._audit(updated, actor, AuditEventType.NOTE_ADDED, None, note.id, note_type.value)
        return updated

    def disposition(
        self,
        project_id: str,
        change_id: str,
        disposition: ChangeDisposition,
        actor: ActorReference,
        explanation: str,
        *,
        cost: ImpactCertainty = ImpactCertainty.UNKNOWN,
        schedule: ImpactCertainty = ImpactCertainty.UNKNOWN,
        scope: ImpactCertainty = ImpactCertainty.UNKNOWN,
    ) -> ProjectChange:
        item = self.get(project_id, change_id)
        now = self.clock()
        record = DispositionRecord(
            id=f"disp_{uuid4().hex[:16]}",
            disposition=disposition,
            reviewer=actor,
            created_at=now,
            explanation=explanation,
            cost_impact=cost,
            schedule_impact=schedule,
            scope_impact=scope,
        )
        updated = self._save(
            item, disposition=disposition, dispositions=item.dispositions + (record,)
        )
        self._audit(
            updated,
            actor,
            AuditEventType.DISPOSITION_CHANGED,
            item.disposition.value,
            disposition.value,
            explanation,
        )
        return updated

    def add_link(
        self,
        project_id: str,
        change_id: str,
        workflow_type: WorkflowType,
        reference: str,
        relationship: RelationshipType,
        actor: ActorReference,
        *,
        url: str | None = None,
    ) -> ProjectChange:
        item = self.get(project_id, change_id)
        if any(
            link.workflow_type == workflow_type and link.reference == reference
            for link in item.links
        ):
            return item
        link = ChangeWorkflowLink(
            id=f"link_{sha256(f'{change_id}{workflow_type}{reference}'.encode()).hexdigest()[:16]}",
            workflow_type=workflow_type,
            reference=reference,
            display_label=reference,
            relationship=relationship,
            created_by=actor,
            created_at=self.clock(),
            url=url,
        )
        updated = self._save(item, links=item.links + (link,))
        self._audit(updated, actor, AuditEventType.LINK_CREATED, None, link.id, reference)
        return updated

    def remove_link(
        self,
        project_id: str,
        change_id: str,
        link_id: str,
        actor: ActorReference,
        *,
        reason: str | None = None,
    ) -> ProjectChange:
        item = self.get(project_id, change_id)
        if not any(link.id == link_id for link in item.links):
            raise ChangeNotFoundError("Workflow link not found")
        updated = self._save(item, links=tuple(link for link in item.links if link.id != link_id))
        self._audit(
            updated,
            actor,
            AuditEventType.LINK_REMOVED,
            link_id,
            None,
            reason,
        )
        return updated

    def create_related_item(
        self, project_id: str, change_id: str, workflow_type: WorkflowType, actor: ActorReference
    ) -> RelatedItem:
        item = self.get(project_id, change_id)
        existing = next(
            (record for record in item.related_items if record.workflow_type == workflow_type), None
        )
        if existing:
            return existing
        now = self.clock()
        related = RelatedItem(
            id=f"item_{sha256(f'{change_id}{workflow_type}'.encode()).hexdigest()[:16]}",
            project_id=project_id,
            project_change_id=change_id,
            workflow_type=workflow_type,
            title=f"Draft {workflow_type.value}: {item.title}",
            description=item.description,
            status=RelatedItemStatus.DRAFT,
            evidence=item.evidence,
            created_at=now,
            updated_at=now,
        )
        link = ChangeWorkflowLink(
            id=f"link_{sha256(related.id.encode()).hexdigest()[:16]}",
            workflow_type=workflow_type,
            reference=related.id,
            display_label=related.title,
            relationship=RelationshipType.REQUIRES,
            created_by=actor,
            created_at=now,
        )
        updated = self._save(
            item, related_items=item.related_items + (related,), links=item.links + (link,)
        )
        self._audit(
            updated,
            actor,
            AuditEventType.RELATED_ITEM_CREATED,
            None,
            related.id,
            workflow_type.value,
        )
        return related

    def mark_stale(self, project_id: str, comparison_id: str, actor: ActorReference) -> int:
        count = 0
        for item in self.repository.list_changes(project_id):
            if item.evidence.comparison_id == comparison_id and not item.source_stale:
                updated = self._save(item, source_stale=True)
                self._audit(
                    updated,
                    actor,
                    AuditEventType.COMPARISON_STALE,
                    "current",
                    "stale",
                    comparison_id,
                )
                count += 1
        return count

    def _from_finding(
        self, comparison: DocumentComparison, finding: DocumentChange
    ) -> ProjectChange:
        now = self.clock()
        digest = sha256(
            f"{comparison.project_id}\0{comparison.id}\0{finding.id}".encode()
        ).hexdigest()[:20]
        evidence = ChangeEvidenceReference(
            comparison_id=comparison.id,
            finding_id=finding.id,
            old_document_id=comparison.old_document.document_id,
            new_document_id=comparison.new_document.document_id,
            old_citation=finding.evidence.old_citation,
            new_citation=finding.evidence.new_citation,
            evidence_hash=sha256(finding.evidence.model_dump_json().encode()).hexdigest(),
        )
        priority = {
            ChangeSeverity.CRITICAL: ChangePriority.CRITICAL,
            ChangeSeverity.HIGH: ChangePriority.HIGH,
            ChangeSeverity.MEDIUM: ChangePriority.MEDIUM,
            ChangeSeverity.LOW: ChangePriority.LOW,
        }.get(finding.severity, ChangePriority.INFORMATIONAL)
        return ProjectChange(
            id=f"pchg_{digest}",
            project_id=comparison.project_id,
            origin=ChangeOrigin.REVISION_FINDING,
            title=finding.title,
            description=finding.explanation,
            priority=priority,
            evidence=evidence,
            affected_disciplines=finding.potentially_affected_disciplines,
            affected_workflows=finding.potentially_affected_workflows,
            created_at=now,
            updated_at=now,
            evidence_strength=finding.evidence_strength,
            potential_significance=finding.severity,
        )

    def _save(self, item: ProjectChange, **values: object) -> ProjectChange:
        updated = item.model_copy(
            update={**values, "version": item.version + 1, "updated_at": self.clock()}
        )
        self.repository.save_change(updated, expected_version=item.version)
        return updated

    def _audit(
        self,
        item: ProjectChange,
        actor: ActorReference,
        event_type: AuditEventType,
        previous: str | None,
        new: str | None,
        reason: str | None,
    ) -> None:
        now = self.clock()
        event = AuditEvent(
            id=f"audit_{uuid4().hex}",
            project_id=item.project_id,
            entity_type="project_change",
            entity_id=item.id,
            actor=actor,
            timestamp=now,
            event_type=event_type,
            previous_state=previous,
            new_state=new,
            reason=reason,
            correlation_id=uuid4().hex,
        )
        self.repository.append_audit(event)
