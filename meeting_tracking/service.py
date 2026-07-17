"""Application services for deterministic meeting operations and human review."""

from datetime import UTC, date, datetime, timedelta
from difflib import SequenceMatcher
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from document_processing import DocumentIngestionService, DocumentType
from storage import JsonDocumentRepository

from .extraction import parse_agenda, parse_candidates, parse_metadata
from .models import (
    ActionDashboard,
    ActionStatus,
    AuditEvent,
    DecisionConflict,
    DecisionStatus,
    ExtractedMeetingItem,
    Meeting,
    MeetingAnalysis,
    MeetingItemChange,
    MeetingItemType,
    MeetingCommitment,
    MeetingDependency,
    MeetingRecordComparison,
    MeetingRecordRevision,
    MeetingSeries,
    MeetingStatus,
    MeetingType,
    MinutesRevision,
    MinutesStatus,
    NotificationRequest,
    ProjectAction,
    ProjectDecision,
    RecordType,
    ReviewStatus,
    WorkflowLink,
)
from .repository import JsonMeetingRepository


class MeetingTrackingService:
    TRANSITIONS = {
        ActionStatus.NEW: {ActionStatus.UNASSIGNED, ActionStatus.ASSIGNED, ActionStatus.CANCELLED},
        ActionStatus.UNASSIGNED: {ActionStatus.ASSIGNED, ActionStatus.CANCELLED},
        ActionStatus.ASSIGNED: {
            ActionStatus.IN_PROGRESS,
            ActionStatus.WAITING,
            ActionStatus.BLOCKED,
            ActionStatus.COMPLETED,
        },
        ActionStatus.IN_PROGRESS: {
            ActionStatus.WAITING,
            ActionStatus.BLOCKED,
            ActionStatus.COMPLETED,
        },
        ActionStatus.WAITING: {
            ActionStatus.IN_PROGRESS,
            ActionStatus.BLOCKED,
            ActionStatus.COMPLETED,
        },
        ActionStatus.BLOCKED: {ActionStatus.IN_PROGRESS, ActionStatus.COMPLETED},
        ActionStatus.OVERDUE: {
            ActionStatus.IN_PROGRESS,
            ActionStatus.BLOCKED,
            ActionStatus.COMPLETED,
        },
        ActionStatus.COMPLETED: {ActionStatus.IN_PROGRESS},
        ActionStatus.DEFERRED: {ActionStatus.IN_PROGRESS, ActionStatus.CANCELLED},
    }

    def __init__(
        self, documents: JsonDocumentRepository, repository: JsonMeetingRepository
    ) -> None:
        self.documents = documents
        self.repository = repository

    def create_series(
        self,
        project_id: str,
        name: str,
        meeting_type: MeetingType,
        *,
        recurrence: str | None = None,
    ) -> MeetingSeries:
        now = datetime.now(UTC)
        item = MeetingSeries(
            id=f"mseries_{sha256((project_id + name).encode()).hexdigest()[:20]}",
            project_id=project_id,
            name=name,
            meeting_type=meeting_type,
            recurrence_description=recurrence,
            created_at=now,
            updated_at=now,
        )
        self.repository.save("series", item.id, item)
        self._event(project_id, "meeting_series_created", item.id, "system", name)
        return item

    def create_meeting(
        self,
        project_id: str,
        title: str,
        meeting_date: date,
        *,
        meeting_type: MeetingType = MeetingType.OTHER,
        meeting_number: str | None = None,
        series_id: str | None = None,
        previous_meeting_id: str | None = None,
    ) -> Meeting:
        now = datetime.now(UTC)
        identity = (
            f"{project_id}\0{series_id or ''}\0{meeting_number or ''}\0{meeting_date}\0{title}"
        )
        item = Meeting(
            id=f"meeting_{sha256(identity.encode()).hexdigest()[:20]}",
            project_id=project_id,
            title=title,
            meeting_type=meeting_type,
            meeting_series_id=series_id,
            meeting_number=meeting_number,
            meeting_date=meeting_date,
            previous_meeting_id=previous_meeting_id,
            status=MeetingStatus.OCCURRED,
            created_at=now,
            updated_at=now,
        )
        existing = self.repository.get("meetings", item.id, project_id)
        if isinstance(existing, Meeting):
            return existing
        self.repository.save("meetings", item.id, item)
        self._event(project_id, "meeting_created", item.id, "system", title)
        return item

    def ingest_record(
        self,
        project_id: str,
        meeting_id: str,
        file_path: Path,
        record_type: RecordType,
        *,
        revision_number: int | None = None,
        predecessor_revision_id: str | None = None,
        created_by: str = "system",
    ) -> MeetingRecordRevision:
        meeting = self._meeting(project_id, meeting_id)
        result = DocumentIngestionService(self.documents).ingest(
            project_id=project_id,
            file_path=file_path,
            document_type=DocumentType.MEETING_MINUTES,
            document_family_id=f"meeting_{meeting_id}",
            revision_sequence=revision_number,
            parent_document_id=predecessor_revision_id,
        )
        existing_records = self.repository.list("records", project_id)
        number = revision_number or 1 + max(
            (
                item.revision_number
                for item in existing_records
                if isinstance(item, MeetingRecordRevision) and item.meeting_id == meeting_id
            ),
            default=0,
        )
        record_id = f"mrec_{result.document.document_id[4:]}"
        record = MeetingRecordRevision(
            id=record_id,
            meeting_id=meeting_id,
            project_id=project_id,
            source_document_id=result.document.document_id,
            revision_number=number,
            content_hash=result.document.content_hash,
            record_type=record_type,
            created_by=created_by,
            created_at=datetime.now(UTC),
            supersedes_revision_id=predecessor_revision_id,
        )
        self.repository.save("records", record.id, record, immutable=True)
        updated = meeting.model_copy(
            update={
                "source_document_ids": tuple(
                    dict.fromkeys((*meeting.source_document_ids, result.document.document_id))
                ),
                "current_record_revision_id": record.id,
                "updated_at": datetime.now(UTC),
            }
        )
        self.repository.save("meetings", meeting.id, updated)
        self._event(
            project_id,
            "meeting_record_ingested",
            record.id,
            created_by,
            f"Record revision {number} ingested",
        )
        return record

    def analyze(self, project_id: str, record_revision_id: str) -> MeetingAnalysis:
        record = self._record(project_id, record_revision_id)
        source = self.documents.get(record.source_document_id)
        if source is None or source.document.project_id != project_id:
            raise ValueError("Canonical source document not found in requested project")
        meeting = self._meeting(project_id, record.meeting_id)
        metadata, attendees, organizations = parse_metadata(source)
        analysis = MeetingAnalysis(
            record_revision_id=record.id,
            agenda=parse_agenda(source),
            candidates=parse_candidates(source, meeting.id, record.id, meeting.meeting_date),
            metadata_candidates=metadata,
            attendees=attendees,
            organizations=organizations,
            analyzed_at=datetime.now(UTC),
        )
        self.repository.save("analyses", record.id, analysis, immutable=True)
        for candidate in analysis.candidates:
            self.repository.save("candidates", candidate.id, candidate, immutable=True)
        self._event(
            project_id,
            "meeting_record_analyzed",
            record.id,
            "system",
            f"Extracted {len(analysis.candidates)} proposals",
        )
        return analysis

    def review_candidate(
        self,
        project_id: str,
        candidate_id: str,
        status: ReviewStatus,
        reviewer_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        owner_name: str | None = None,
        due_date: date | None = None,
    ) -> tuple[ExtractedMeetingItem, ProjectAction | ProjectDecision | None]:
        candidate = self.repository.find_candidate(project_id, candidate_id)
        if candidate is None:
            raise ValueError("Candidate not found in requested project")
        reviewed = candidate.model_copy(
            update={
                "review_status": status,
                "title": title or candidate.title,
                "description": description or candidate.description,
            }
        )
        self.repository.save("candidates", candidate.id, reviewed)
        created = None
        now = datetime.now(UTC)
        if status in {ReviewStatus.CONFIRMED, ReviewStatus.MODIFIED}:
            if candidate.item_type in {
                MeetingItemType.DECISION,
                MeetingItemType.OWNER_DECISION_REQUEST,
            }:
                created = ProjectDecision(
                    id=f"decision_{sha256(candidate.id.encode()).hexdigest()[:20]}",
                    project_id=project_id,
                    meeting_id=candidate.meeting_id,
                    record_revision_id=candidate.record_revision_id,
                    source_candidate_id=candidate.id,
                    decision_text=reviewed.description,
                    status=DecisionStatus.PENDING_CONFIRMATION,
                    citations=candidate.citations,
                    reviewer_id=reviewer_id,
                    created_at=now,
                    updated_at=now,
                )
                self.repository.save("decisions", created.id, created)
            elif candidate.item_type in {
                MeetingItemType.ACTION_ITEM,
                MeetingItemType.COMMITMENT,
                MeetingItemType.SUBMITTAL_ACTION,
                MeetingItemType.PROCUREMENT_ACTION,
                MeetingItemType.SCHEDULE_ACTION,
                MeetingItemType.COMMISSIONING_ACTION,
            }:
                proposed_due = (
                    candidate.due_date_candidate.parsed_date
                    if candidate.due_date_candidate and not candidate.due_date_candidate.ambiguous
                    else None
                )
                owner = owner_name or candidate.owner_candidate
                created = ProjectAction(
                    id=f"action_{sha256(candidate.id.encode()).hexdigest()[:20]}",
                    project_id=project_id,
                    source_meeting_id=candidate.meeting_id,
                    source_record_revision_id=candidate.record_revision_id,
                    source_candidate_id=candidate.id,
                    title=reviewed.title,
                    description=reviewed.description,
                    owner_name=owner,
                    due_date=due_date or proposed_due,
                    original_due_date_text=candidate.due_date_candidate.original_text
                    if candidate.due_date_candidate
                    else None,
                    status=ActionStatus.ASSIGNED if owner else ActionStatus.UNASSIGNED,
                    citations=candidate.citations,
                    created_at=now,
                    updated_at=now,
                    last_mentioned_meeting_id=candidate.meeting_id,
                )
                self.repository.save("actions", created.id, created)
                if any(word in candidate.description.casefold() for word in (" will ", " shall ")):
                    commitment = MeetingCommitment(
                        id=f"commitment_{sha256(candidate.id.encode()).hexdigest()[:20]}",
                        project_id=project_id,
                        meeting_id=candidate.meeting_id,
                        committing_party=owner,
                        description=reviewed.description,
                        due_date=created.due_date,
                        related_action_id=created.id,
                        citation=candidate.citations[0],
                        confirmation_status=status,
                    )
                    self.repository.save("commitments", commitment.id, commitment)
            elif candidate.item_type == MeetingItemType.DEPENDENCY:
                created = MeetingDependency(
                    id=f"dependency_{sha256(candidate.id.encode()).hexdigest()[:20]}",
                    project_id=project_id,
                    meeting_id=candidate.meeting_id,
                    source_item_id=candidate.id,
                    target_reference=candidate.related_identifiers[0]
                    if candidate.related_identifiers
                    else None,
                    citation=candidate.citations[0],
                    evidence_strength=candidate.extraction_strength,
                    human_confirmed=True,
                )
                self.repository.save("dependencies", created.id, created)
        self._event(
            project_id,
            f"candidate_{status.value}",
            candidate.id,
            reviewer_id,
            f"Candidate {status.value}",
        )
        return reviewed, created

    def split_candidate(
        self, project_id: str, candidate_id: str, descriptions: tuple[str, ...], reviewer_id: str
    ) -> tuple[ExtractedMeetingItem, ...]:
        candidate = self.repository.find_candidate(project_id, candidate_id)
        if (
            candidate is None
            or len(descriptions) < 2
            or any(not value.strip() for value in descriptions)
        ):
            raise ValueError("Split requires an existing candidate and at least two descriptions")
        parent = candidate.model_copy(update={"review_status": ReviewStatus.SPLIT})
        self.repository.save("candidates", parent.id, parent)
        children = tuple(
            candidate.model_copy(
                update={
                    "id": f"mcand_{sha256((candidate.id + str(index) + description).encode()).hexdigest()[:20]}",
                    "title": description[:120],
                    "description": description,
                    "review_status": ReviewStatus.UNREVIEWED,
                    "original_candidate_id": candidate.id,
                }
            )
            for index, description in enumerate(descriptions, start=1)
        )
        for child in children:
            self.repository.save("candidates", child.id, child, immutable=True)
        self._event(
            project_id,
            "candidate_split",
            candidate.id,
            reviewer_id,
            f"Split into {len(children)} proposals",
        )
        return children

    def merge_candidates(
        self, project_id: str, candidate_ids: tuple[str, ...], description: str, reviewer_id: str
    ) -> ExtractedMeetingItem:
        items = tuple(
            self.repository.find_candidate(project_id, identifier) for identifier in candidate_ids
        )
        if len(items) < 2 or any(item is None for item in items) or not description.strip():
            raise ValueError(
                "Merge requires at least two project-scoped candidates and a description"
            )
        typed = tuple(item for item in items if item is not None)
        if len({item.meeting_id for item in typed}) != 1:
            raise ValueError("Candidates from different meetings cannot be merged")
        for item in typed:
            self.repository.save(
                "candidates",
                item.id,
                item.model_copy(update={"review_status": ReviewStatus.MERGED}),
            )
        first = typed[0]
        merged = first.model_copy(
            update={
                "id": f"mcand_{sha256((''.join(candidate_ids) + description).encode()).hexdigest()[:20]}",
                "title": description[:120],
                "description": description,
                "citations": tuple(dict.fromkeys(c for item in typed for c in item.citations)),
                "original_candidate_id": first.id,
                "review_status": ReviewStatus.UNREVIEWED,
            }
        )
        self.repository.save("candidates", merged.id, merged, immutable=True)
        self._event(
            project_id,
            "candidates_merged",
            merged.id,
            reviewer_id,
            f"Merged {len(typed)} proposals",
        )
        return merged

    def assign_action(
        self, project_id: str, action_id: str, owner_id: str, owner_name: str, actor_id: str
    ) -> ProjectAction:
        action = self._action(project_id, action_id)
        updated = action.model_copy(
            update={
                "owner_id": owner_id,
                "owner_name": owner_name,
                "status": ActionStatus.ASSIGNED
                if action.status in {ActionStatus.NEW, ActionStatus.UNASSIGNED}
                else action.status,
                "updated_at": datetime.now(UTC),
                "version": action.version + 1,
            }
        )
        self.repository.save("actions", action.id, updated)
        self._event(project_id, "action_assigned", action.id, actor_id, f"Assigned to {owner_name}")
        return updated

    def transition_action(
        self,
        project_id: str,
        action_id: str,
        status: ActionStatus,
        actor_id: str,
        *,
        reason: str | None = None,
        resolution: str | None = None,
        completion_evidence: str | None = None,
    ) -> ProjectAction:
        action = self._action(project_id, action_id)
        if status not in self.TRANSITIONS.get(action.status, set()):
            raise ValueError(f"Invalid action transition: {action.status} -> {status}")
        if status == ActionStatus.COMPLETED and not (resolution or completion_evidence):
            raise ValueError("Completion requires a resolution note or completion evidence")
        if (
            status in {ActionStatus.BLOCKED, ActionStatus.CANCELLED, ActionStatus.SUPERSEDED}
            and not reason
        ):
            raise ValueError(f"{status} requires an explanation")
        if (
            action.status == ActionStatus.COMPLETED
            and status == ActionStatus.IN_PROGRESS
            and not reason
        ):
            raise ValueError("Reopening a completed action requires a reason")
        now = datetime.now(UTC)
        updated = action.model_copy(
            update={
                "status": status,
                "resolution_note": resolution or action.resolution_note,
                "completion_evidence": completion_evidence or action.completion_evidence,
                "completed_at": now if status == ActionStatus.COMPLETED else None,
                "cancelled_at": now if status == ActionStatus.CANCELLED else action.cancelled_at,
                "updated_at": now,
                "version": action.version + 1,
            }
        )
        self.repository.save("actions", action.id, updated)
        self._event(
            project_id, "action_status_changed", action.id, actor_id, f"{action.status} -> {status}"
        )
        return updated

    def add_link(
        self,
        project_id: str,
        action_id: str,
        workflow_type: str,
        reference: str,
        relationship: str,
        actor_id: str,
    ) -> ProjectAction:
        action = self._action(project_id, action_id)
        if any(
            item.workflow_type == workflow_type and item.reference == reference
            for item in action.links
        ):
            return action
        link = WorkflowLink(
            id=f"mlink_{uuid4().hex}",
            workflow_type=workflow_type,
            reference=reference,
            relationship=relationship,
            created_at=datetime.now(UTC),
            created_by=actor_id,
        )
        updated = action.model_copy(
            update={
                "links": (*action.links, link),
                "updated_at": datetime.now(UTC),
                "version": action.version + 1,
            }
        )
        self.repository.save("actions", action.id, updated)
        self._event(
            project_id,
            "workflow_link_created",
            action.id,
            actor_id,
            f"Linked {workflow_type} {reference}",
        )
        return updated

    def confirm_decision(
        self, project_id: str, decision_id: str, reviewer_id: str
    ) -> ProjectDecision:
        decision = self._decision(project_id, decision_id)
        updated = decision.model_copy(
            update={
                "status": DecisionStatus.CONFIRMED,
                "reviewer_id": reviewer_id,
                "updated_at": datetime.now(UTC),
            }
        )
        self.repository.save("decisions", decision.id, updated)
        self._event(
            project_id,
            "decision_confirmed",
            decision.id,
            reviewer_id,
            "Decision confirmed by human reviewer",
        )
        self._detect_conflicts(updated)
        return updated

    def supersede_decision(
        self, project_id: str, old_id: str, new_id: str, reviewer_id: str
    ) -> tuple[ProjectDecision, ProjectDecision]:
        old, new = self._decision(project_id, old_id), self._decision(project_id, new_id)
        old = old.model_copy(
            update={
                "status": DecisionStatus.SUPERSEDED,
                "superseded_by_decision_id": new.id,
                "updated_at": datetime.now(UTC),
            }
        )
        new = new.model_copy(
            update={
                "supersedes_decision_id": old.id,
                "reviewer_id": reviewer_id,
                "updated_at": datetime.now(UTC),
            }
        )
        self.repository.save("decisions", old.id, old)
        self.repository.save("decisions", new.id, new)
        self._event(
            project_id, "decision_superseded", old.id, reviewer_id, f"Superseded by {new.id}"
        )
        return old, new

    def carry_forward(
        self, project_id: str, previous_meeting_id: str, current_meeting_id: str, current_text: str
    ) -> tuple[ProjectAction, ...]:
        results = []
        for item in self.repository.list("actions", project_id):
            if (
                not isinstance(item, ProjectAction)
                or item.source_meeting_id != previous_meeting_id
                or item.status
                in {ActionStatus.COMPLETED, ActionStatus.CANCELLED, ActionStatus.SUPERSEDED}
            ):
                continue
            similarity = SequenceMatcher(
                None, item.description.casefold(), current_text.casefold()
            ).ratio()
            mentioned = (
                item.id.casefold() in current_text.casefold()
                or any(tag.casefold() in current_text.casefold() for tag in item.tags)
                or similarity > 0.35
            )
            updated = item.model_copy(
                update={
                    "carry_forward_count": item.carry_forward_count + (1 if mentioned else 0),
                    "last_mentioned_meeting_id": current_meeting_id
                    if mentioned
                    else item.last_mentioned_meeting_id,
                    "updated_at": datetime.now(UTC),
                    "version": item.version + 1,
                }
            )
            self.repository.save("actions", item.id, updated)
            results.append(updated)
            self._event(
                project_id,
                "action_carried_forward" if mentioned else "action_not_mentioned",
                item.id,
                "system",
                "Open action preserved; omission does not imply completion",
            )
        return tuple(results)

    def draft_minutes(
        self, project_id: str, meeting_id: str, actor_id: str, *, include_unconfirmed: bool = False
    ) -> MinutesRevision:
        meeting = self._meeting(project_id, meeting_id)
        actions = [
            item
            for item in self.repository.list("actions", project_id)
            if isinstance(item, ProjectAction) and item.source_meeting_id == meeting_id
        ]
        decisions = [
            item
            for item in self.repository.list("decisions", project_id)
            if isinstance(item, ProjectDecision)
            and item.meeting_id == meeting_id
            and (include_unconfirmed or item.status == DecisionStatus.CONFIRMED)
        ]
        candidates = [
            item
            for item in self.repository.list("candidates", project_id)
            if isinstance(item, ExtractedMeetingItem)
            and item.meeting_id == meeting_id
            and item.review_status != ReviewStatus.REJECTED
        ]
        lines = [
            f"# {meeting.title}",
            "",
            "**DRAFT — NOT ISSUED**",
            "",
            f"- Date: {meeting.meeting_date or 'unknown'}",
            f"- Meeting number: {meeting.meeting_number or 'unknown'}",
            "",
            "## Confirmed decisions",
            "",
        ]
        lines.extend(f"- `{item.id}` {item.decision_text}" for item in decisions)
        lines.extend(["", "## Action items", ""])
        lines.extend(
            f"- `{item.id}` {item.description} — Owner: {item.owner_name or 'unassigned'}; Due: {item.due_date or item.original_due_date_text or 'not stated'}"
            for item in actions
        )
        if include_unconfirmed:
            lines.extend(["", "## Unconfirmed proposals", ""])
            lines.extend(
                f"- [UNCONFIRMED] {item.description}"
                for item in candidates
                if item.review_status == ReviewStatus.UNREVIEWED
            )
        lines.extend(
            [
                "",
                "## Source and review status",
                "",
                "This draft contains human-confirmed register items by default. It has not been distributed externally.",
            ]
        )
        markdown = "\n".join(lines)
        existing = [
            item
            for item in self.repository.list("minutes", project_id)
            if isinstance(item, MinutesRevision) and item.meeting_id == meeting_id
        ]
        item = MinutesRevision(
            id=f"minutes_{uuid4().hex}",
            project_id=project_id,
            meeting_id=meeting_id,
            revision_number=len(existing) + 1,
            status=MinutesStatus.DRAFT,
            markdown=markdown,
            content_hash=sha256(markdown.encode()).hexdigest(),
            created_at=datetime.now(UTC),
            created_by=actor_id,
            supersedes_revision_id=existing[-1].id if existing else None,
        )
        self.repository.save("minutes", item.id, item, immutable=True)
        self._event(project_id, "minutes_drafted", item.id, actor_id, "Draft minutes generated")
        return item

    def transition_minutes(
        self, project_id: str, minutes_id: str, status: MinutesStatus, actor_id: str
    ) -> MinutesRevision:
        value = self.repository.get("minutes", minutes_id, project_id)
        if not isinstance(value, MinutesRevision):
            raise ValueError("Minutes revision not found")
        allowed = {
            MinutesStatus.DRAFT: {MinutesStatus.PENDING_REVIEW},
            MinutesStatus.PENDING_REVIEW: {
                MinutesStatus.REVISIONS_REQUIRED,
                MinutesStatus.APPROVED,
            },
            MinutesStatus.REVISIONS_REQUIRED: {MinutesStatus.PENDING_REVIEW},
            MinutesStatus.APPROVED: {MinutesStatus.ISSUED},
        }
        if status not in allowed.get(value.status, set()):
            raise ValueError("Invalid minutes transition")
        now = datetime.now(UTC)
        updated = value.model_copy(
            update={
                "status": status,
                "approved_at": now if status == MinutesStatus.APPROVED else value.approved_at,
                "issued_at": now if status == MinutesStatus.ISSUED else value.issued_at,
            }
        )
        self.repository.save("minutes", value.id, updated)
        self._event(
            project_id, f"minutes_{status.value}", value.id, actor_id, f"Minutes {status.value}"
        )
        return updated

    def compare_records(self, project_id: str, old_id: str, new_id: str) -> MeetingRecordComparison:
        old, new = self._record(project_id, old_id), self._record(project_id, new_id)
        old_doc = self.documents.get(old.source_document_id)
        new_doc = self.documents.get(new.source_document_id)
        if not old_doc or not new_doc:
            raise ValueError("Source document missing")
        old_lines = {
            " ".join(x.split()): x
            for p in old_doc.pages
            for x in p.content.splitlines()
            if x.strip()
        }
        new_lines = {
            " ".join(x.split()): x
            for p in new_doc.pages
            for x in p.content.splitlines()
            if x.strip()
        }
        changes = []
        from .extraction import evidence

        for normalized, line in old_lines.items():
            if normalized not in new_lines:
                changes.append(
                    MeetingItemChange(
                        change_type="removed", summary=line, old_citation=evidence(old_doc, 1, line)
                    )
                )
        for normalized, line in new_lines.items():
            if normalized not in old_lines:
                changes.append(
                    MeetingItemChange(
                        change_type="added", summary=line, new_citation=evidence(new_doc, 1, line)
                    )
                )
        item = MeetingRecordComparison(
            id=f"mcomp_{uuid4().hex}",
            project_id=project_id,
            old_record_revision_id=old.id,
            new_record_revision_id=new.id,
            changes=tuple(changes),
            created_at=datetime.now(UTC),
        )
        self.repository.save("comparisons", item.id, item, immutable=True)
        self._event(
            project_id,
            "meeting_records_compared",
            item.id,
            "system",
            f"{len(changes)} text changes",
        )
        return item

    def dashboard(self, project_id: str, today: date | None = None) -> ActionDashboard:
        current = today or date.today()
        actions = tuple(
            item
            for item in self.repository.list("actions", project_id)
            if isinstance(item, ProjectAction)
        )
        open_items = tuple(
            item
            for item in actions
            if item.status
            not in {ActionStatus.COMPLETED, ActionStatus.CANCELLED, ActionStatus.SUPERSEDED}
        )
        decisions = tuple(
            item
            for item in self.repository.list("decisions", project_id)
            if isinstance(item, ProjectDecision)
        )
        conflicts = self.repository.list("conflicts", project_id)
        return ActionDashboard(
            total_open=len(open_items),
            unassigned=sum(not x.owner_name for x in open_items),
            due_today=sum(x.due_date == current for x in open_items),
            due_soon=sum(
                bool(x.due_date and current < x.due_date <= current + timedelta(days=7))
                for x in open_items
            ),
            overdue=sum(bool(x.due_date and x.due_date < current) for x in open_items),
            blocked=sum(x.status == ActionStatus.BLOCKED for x in open_items),
            waiting=sum(x.status == ActionStatus.WAITING for x in open_items),
            repeatedly_carried=sum(x.carry_forward_count > 2 for x in open_items),
            decisions_awaiting_confirmation=sum(
                x.status == DecisionStatus.PENDING_CONFIRMATION for x in decisions
            ),
            conflicts=len(conflicts),
            actions=open_items,
        )

    def search(
        self, project_id: str, query: str
    ) -> tuple[Meeting | ExtractedMeetingItem | ProjectAction | ProjectDecision, ...]:
        needle = query.casefold()
        results = []
        for category in ("meetings", "candidates", "actions", "decisions"):
            for item in self.repository.list(category, project_id):
                if needle in item.model_dump_json().casefold():
                    results.append(item)
        return tuple(results)

    def _detect_conflicts(self, decision: ProjectDecision) -> None:
        for other in self.repository.list("decisions", decision.project_id):
            if (
                not isinstance(other, ProjectDecision)
                or other.id == decision.id
                or other.status != DecisionStatus.CONFIRMED
            ):
                continue
            score = SequenceMatcher(
                None, decision.decision_text.casefold(), other.decision_text.casefold()
            ).ratio()
            if score > 0.45 and decision.decision_text.casefold() != other.decision_text.casefold():
                conflict = DecisionConflict(
                    id=f"dconf_{sha256((other.id + decision.id).encode()).hexdigest()[:20]}",
                    project_id=decision.project_id,
                    decision_ids=(other.id, decision.id),
                    explanation="Potentially different decisions address similar meeting language; Brunel does not determine precedence.",
                )
                self.repository.save("conflicts", conflict.id, conflict)
                self._event(
                    decision.project_id,
                    "decision_conflict_identified",
                    conflict.id,
                    "system",
                    conflict.explanation,
                )

    def _meeting(self, p, i):
        v = self.repository.get("meetings", i, p)
        if not isinstance(v, Meeting):
            raise ValueError("Meeting not found in requested project")
        return v

    def _record(self, p, i):
        v = self.repository.get("records", i, p)
        if not isinstance(v, MeetingRecordRevision):
            raise ValueError("Meeting record not found in requested project")
        return v

    def _action(self, p, i):
        v = self.repository.find_action(p, i)
        if not v:
            raise ValueError("Action not found in requested project")
        return v

    def _decision(self, p, i):
        v = self.repository.find_decision(p, i)
        if not v:
            raise ValueError("Decision not found in requested project")
        return v

    def _event(self, project_id, event_type, subject_id, actor_id, summary):
        now = datetime.now(UTC)
        audit = AuditEvent(
            id=f"maudit_{uuid4().hex}",
            project_id=project_id,
            event_type=event_type,
            subject_id=subject_id,
            actor_id=actor_id,
            created_at=now,
        )
        note = NotificationRequest(
            id=f"mnotify_{uuid4().hex}",
            project_id=project_id,
            event_type=event_type,
            subject_id=subject_id,
            summary=summary[:250],
            created_at=now,
        )
        self.repository.save("audit", audit.id, audit, immutable=True)
        self.repository.save("outbox", note.id, note, immutable=True)
