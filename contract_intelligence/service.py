from datetime import date, timedelta
from hashlib import sha256
from uuid import uuid4
from .models import (
    AuditEvent,
    ChronologyEntry,
    Clause,
    ConflictFinding,
    ContractDashboard,
    ContractDocument,
    ContractEvent,
    ContractRelationship,
    ContractRequirement,
    Correspondence,
    DeadlineCalculation,
    DefinedTerm,
    Evidence,
    HierarchyEdge,
    NoticeCandidate,
    NoticeDraft,
    NoticeDraftRevision,
    NotificationRequest,
    Obligation,
    ReviewStatus,
)
from .repository import JsonContractRepository


class ContractIntelligenceService:
    def __init__(self, repository: JsonContractRepository):
        self.repository = repository

    def _id(self, prefix: str, *parts: str) -> str:
        return f"{prefix}_{sha256('|'.join(parts).encode()).hexdigest()[:16]}"

    def _get(self, category: str, project: str, identifier: str):
        value = self.repository.get(category, identifier, project)
        if value is None:
            raise ValueError(f"{category.rstrip('s').title()} not found in requested project")
        return value

    def _audit(self, project: str, event: str, subject: str, actor: str = "brunel") -> None:
        value = AuditEvent(
            id=f"audit_{uuid4().hex[:16]}",
            project_id=project,
            event_type=event,
            subject_id=subject,
            actor=actor,
        )
        self.repository.save("audit", value.id, value)

    def _notify(self, project: str, event: str, subject: str, summary: str) -> None:
        value = NotificationRequest(
            id=f"out_{uuid4().hex[:16]}",
            project_id=project,
            event_type=event,
            subject_id=subject,
            summary=summary,
        )
        self.repository.save("outbox", value.id, value)

    def ingest_contract(
        self,
        project_id: str,
        source_revision_id: str,
        document_type: str,
        title: str,
        evidence: tuple[Evidence, ...],
        *,
        relationship_id: str | None = None,
        supersedes_id: str | None = None,
    ) -> ContractDocument:
        revision = 1
        prior = None
        if supersedes_id:
            prior = self._get("documents", project_id, supersedes_id)
            revision = prior.revision + 1
        did = self._id("contract", project_id, source_revision_id)
        value = ContractDocument(
            id=did,
            project_id=project_id,
            source_document_revision_id=source_revision_id,
            contract_relationship_id=relationship_id,
            document_type=document_type,
            title=title,
            revision=revision,
            supersedes_id=supersedes_id,
            evidence=evidence,
        )
        self.repository.save("documents", did, value, immutable=True)
        self._audit(project_id, "contract_ingested", did)
        if prior:
            self._notify(
                project_id,
                "contract_document_superseded",
                prior.id,
                "Contract revision requires human review",
            )
        return value

    def create_relationship(
        self,
        project_id: str,
        parties: tuple[str, ...],
        roles: dict[str, str],
        evidence: tuple[Evidence, ...],
    ) -> ContractRelationship:
        rid = self._id("relationship", project_id, *parties)
        value = ContractRelationship(
            id=rid, project_id=project_id, parties=parties, roles_as_stated=roles, evidence=evidence
        )
        self.repository.save("relationships", rid, value)
        self._audit(project_id, "contract_relationship_created", rid)
        return value

    def link_hierarchy(
        self,
        project_id: str,
        source_id: str,
        target_id: str,
        relationship: str,
        language: str,
        citation: Evidence,
        confidence: float = 0.8,
    ) -> HierarchyEdge:
        self._get("documents", project_id, source_id)
        self._get("documents", project_id, target_id)
        eid = self._id("edge", project_id, source_id, target_id, relationship)
        value = HierarchyEdge(
            id=eid,
            project_id=project_id,
            source_document_id=source_id,
            target_document_id=target_id,
            relationship=relationship,
            source_language=language,
            citation=citation,
            confidence=confidence,
            uncertainty=("Precedence and legal effect are not determined.",),
        )
        self.repository.save("hierarchy", eid, value)
        self._audit(project_id, "hierarchy_link_created", eid)
        return value

    def extract_clauses(
        self, project_id: str, document_id: str, evidence: tuple[Evidence, ...]
    ) -> tuple[Clause, ...]:
        document = self._get("documents", project_id, document_id)
        result = []
        categories = {
            "notice": "notices",
            "payment": "payment",
            "schedule": "schedule",
            "delay": "delay",
            "warranty": "warranties",
            "closeout": "closeout",
            "insurance": "insurance",
            "change": "changes",
            "commission": "commissioning",
            "termination": "termination",
        }
        for index, source in enumerate(evidence, 1):
            text = source.exact_text.strip()
            first, *rest = text.split(maxsplit=1)
            number = first.rstrip(".:") if any(c.isdigit() for c in first) else str(index)
            category = next(
                (value for key, value in categories.items() if key in text.casefold()), "unknown"
            )
            cid = self._id("clause", document_id, str(document.revision), number, source.record_id)
            value = Clause(
                id=cid,
                project_id=project_id,
                document_id=document_id,
                document_revision=document.revision,
                clause_number=number,
                full_source_text=text,
                normalized_summary=(rest[0] if rest else text)[:500],
                category=category,
                citation=source,
                confidence=0.8,
                uncertainty=("Normalized summary is non-controlling and requires human review.",),
            )
            self.repository.save("clauses", cid, value, immutable=True)
            self._audit(project_id, "clause_extracted", cid)
            result.append(value)
        return tuple(result)

    def add_defined_term(
        self, project_id: str, clause_id: str, term: str, definition: str, citation: Evidence
    ) -> DefinedTerm:
        clause = self._get("clauses", project_id, clause_id)
        tid = self._id("term", project_id, clause.document_id, term)
        conflicts = tuple(
            x.id
            for x in self.repository.list("terms", project_id)
            if x.term.casefold() == term.casefold()
            and x.definition.casefold() != definition.casefold()
        )
        value = DefinedTerm(
            id=tid,
            project_id=project_id,
            term=term,
            definition=definition,
            document_id=clause.document_id,
            clause_id=clause_id,
            citation=citation,
            conflicting_definition_ids=conflicts,
        )
        self.repository.save("terms", tid, value)
        self._audit(project_id, "defined_term_recorded", tid)
        return value

    def create_requirement(
        self,
        project_id: str,
        clause_id: str,
        title: str,
        description: str,
        *,
        time_limit: int | None = None,
        calendar_basis: str | None = None,
        recipient: str | None = None,
        delivery_method: str | None = None,
        trigger: str | None = None,
        workflow_links: tuple[dict[str, str], ...] = (),
    ) -> ContractRequirement:
        clause = self._get("clauses", project_id, clause_id)
        rid = self._id("req", project_id, clause_id, title)
        value = ContractRequirement(
            id=rid,
            project_id=project_id,
            title=title,
            description=description,
            triggering_event=trigger,
            required_recipient=recipient,
            delivery_method=delivery_method,
            time_limit=time_limit,
            calendar_basis=calendar_basis,
            clause_id=clause_id,
            citation=clause.citation,
            confidence=0.75,
            uncertainty=("Potential contractual requirement; qualified human review required.",),
            workflow_links=workflow_links,
        )
        self.repository.save("requirements", rid, value)
        self._audit(project_id, "requirement_created", rid)
        return value

    def review_requirement(
        self, project_id: str, requirement_id: str, actor: str, accept: bool
    ) -> ContractRequirement:
        value = self._get("requirements", project_id, requirement_id)
        updated = value.model_copy(
            update={
                "status": ReviewStatus.CONFIRMED_FOR_TRACKING if accept else ReviewStatus.REJECTED
            }
        )
        self.repository.save("requirements", value.id, updated)
        self._audit(project_id, "requirement_review", value.id, actor)
        return updated

    def calculate_deadline(
        self,
        project_id: str,
        requirement_id: str,
        trigger_date: date | None,
        *,
        holidays: tuple[date, ...] = (),
        direction: str = "after",
    ) -> DeadlineCalculation:
        requirement = self._get("requirements", project_id, requirement_id)
        basis = requirement.calendar_basis
        period = requirement.time_limit
        ambiguous = (
            trigger_date is None
            or period is None
            or basis not in {"calendar_days", "business_days", "working_days"}
        )
        included = []
        excluded = []
        calculated = None
        if not ambiguous:
            step = 1 if direction == "after" else -1
            current = trigger_date
            remaining = period
            while remaining:
                current += timedelta(days=step)
                include = basis == "calendar_days" or (
                    current.weekday() < 5 and current not in holidays
                )
                (included if include else excluded).append(current)
                if include:
                    remaining -= 1
            calculated = current
        did = f"deadline_{uuid4().hex[:16]}"
        value = DeadlineCalculation(
            id=did,
            project_id=project_id,
            requirement_id=requirement_id,
            trigger_date=trigger_date,
            calendar_basis=basis,
            direction=direction,
            period_days=period,
            included_dates=tuple(included),
            excluded_dates=tuple(excluded),
            calculated_date=calculated,
            explanation="Calculation withheld: trigger, period, or calendar basis is ambiguous."
            if ambiguous
            else f"Counted {period} {basis.replace('_', ' ')} {direction} {trigger_date}.",
            uncertainty=("Candidate date is not legal advice and requires human confirmation.",),
            review_required=True,
        )
        self.repository.save("deadlines", did, value, immutable=True)
        self._audit(project_id, "deadline_calculated", did)
        return value

    def generate_notice_candidate(
        self,
        project_id: str,
        requirement_id: str,
        event_record_id: str,
        event_evidence: tuple[Evidence, ...],
        *,
        trigger_date: date | None = None,
        notice_type: str = "unknown",
    ) -> NoticeCandidate:
        requirement = self._get("requirements", project_id, requirement_id)
        deadline = (
            self.calculate_deadline(project_id, requirement_id, trigger_date)
            if trigger_date or requirement.time_limit
            else None
        )
        cid = self._id("notice", project_id, requirement_id, event_record_id)
        existing = self.repository.get("candidates", cid, project_id)
        if existing:
            return existing
        value = NoticeCandidate(
            id=cid,
            project_id=project_id,
            requirement_id=requirement_id,
            event_record_id=event_record_id,
            notice_type=notice_type,
            recipient_as_stated=requirement.required_recipient,
            delivery_method_as_stated=requirement.delivery_method,
            candidate_deadline_id=deadline.id if deadline else None,
            evidence=(requirement.citation,) + event_evidence,
            uncertainty=(
                "Clause appears potentially relevant; this is not a legal conclusion or determination of notice sufficiency.",
            ),
        )
        self.repository.save("candidates", cid, value)
        self._audit(project_id, "notice_candidate_generated", cid)
        self._notify(
            project_id,
            "potential_notice_requirement",
            cid,
            "Notice candidate requires human review",
        )
        return value

    def draft_notice(
        self,
        project_id: str,
        candidate_id: str,
        sender: str,
        recipient: str,
        subject: str,
        chronology: tuple[str, ...],
        actor: str,
    ) -> NoticeDraft:
        candidate = self._get("candidates", project_id, candidate_id)
        requirement = self._get("requirements", project_id, candidate.requirement_id)
        revision = NoticeDraftRevision(
            revision=1,
            subject=subject,
            factual_chronology=chronology,
            contract_evidence=(requirement.citation,),
            project_evidence=tuple(candidate.evidence[1:]),
            created_by=actor,
        )
        did = f"draft_{uuid4().hex[:16]}"
        value = NoticeDraft(
            id=did,
            project_id=project_id,
            candidate_id=candidate_id,
            sender=sender,
            recipient=recipient,
            revisions=(revision,),
            external_delivery_performed=False,
        )
        self.repository.save("drafts", did, value)
        self._audit(project_id, "notice_drafted", did, actor)
        return value

    def normalize_obligation(
        self,
        project_id: str,
        requirement_id: str,
        source_type: str,
        source_id: str,
        title: str,
        *,
        owner: str | None = None,
        due_date: date | None = None,
    ) -> Obligation:
        self._get("requirements", project_id, requirement_id)
        oid = self._id("obligation", project_id, requirement_id, source_type, source_id)
        value = Obligation(
            id=oid,
            project_id=project_id,
            requirement_id=requirement_id,
            source_record_type=source_type,
            source_record_id=source_id,
            title=title,
            owner=owner,
            due_date=due_date,
            uncertainty=(
                "Normalized view references, but does not duplicate, the canonical source workflow.",
            ),
        )
        self.repository.save("obligations", oid, value)
        self._audit(project_id, "obligation_created", oid)
        return value

    def confirm_obligation(
        self, project_id: str, obligation_id: str, evidence: tuple[Evidence, ...], actor: str
    ) -> Obligation:
        value = self._get("obligations", project_id, obligation_id)
        if not evidence:
            raise ValueError("Human-confirmed obligation completion requires evidence")
        updated = value.model_copy(
            update={"status": "satisfied_as_confirmed", "completion_evidence": evidence}
        )
        self.repository.save("obligations", value.id, updated)
        self._audit(project_id, "obligation_completion", value.id, actor)
        return updated

    def create_event(
        self,
        project_id: str,
        event_type: str,
        description: str,
        evidence: tuple[Evidence, ...],
        *,
        start: date | None = None,
        end: date | None = None,
        links: tuple[str, ...] = (),
        conflicts: tuple[Evidence, ...] = (),
    ) -> ContractEvent:
        eid = f"event_{uuid4().hex[:16]}"
        value = ContractEvent(
            id=eid,
            project_id=project_id,
            event_type=event_type,
            description=description,
            source_reported_start=start,
            source_reported_end=end,
            linked_record_ids=links,
            evidence=evidence,
            conflicting_evidence=conflicts,
            legal_conclusion=False,
        )
        self.repository.save("events", eid, value)
        self._audit(project_id, f"{event_type}_event_created", eid)
        return value

    def add_correspondence(
        self,
        project_id: str,
        sender: str,
        recipients: tuple[str, ...],
        subject: str,
        on: date,
        evidence: tuple[Evidence, ...],
        links: tuple[str, ...] = (),
    ) -> Correspondence:
        cid = f"correspondence_{uuid4().hex[:16]}"
        value = Correspondence(
            id=cid,
            project_id=project_id,
            sender=sender,
            recipients=recipients,
            subject=subject,
            correspondence_date=on,
            related_record_ids=links,
            evidence=evidence,
            external_delivery_performed=False,
        )
        self.repository.save("correspondence", cid, value)
        self._audit(project_id, "correspondence_linked", cid)
        return value

    def detect_conflicts(self, project_id: str) -> tuple[ConflictFinding, ...]:
        requirements = self.repository.list("requirements", project_id)
        result = []
        for i, left in enumerate(requirements):
            for right in requirements[i + 1 :]:
                same = left.title.casefold() == right.title.casefold()
                differs = (left.time_limit, left.required_recipient, left.delivery_method) != (
                    right.time_limit,
                    right.required_recipient,
                    right.delivery_method,
                )
                if same and differs:
                    fid = self._id("conflict", project_id, left.id, right.id)
                    finding = ConflictFinding(
                        id=fid,
                        project_id=project_id,
                        category="contract_requirement_conflict",
                        record_ids=(left.id, right.id),
                        conflicting_language=(left.description, right.description),
                        citations=(left.citation, right.citation),
                        confidence=0.9,
                        uncertainty=("Conflict and precedence are not resolved automatically.",),
                    )
                    self.repository.save("conflicts", fid, finding)
                    self._audit(project_id, "conflict_finding", fid)
                    result.append(finding)
        return tuple(result)

    def chronology(self, project_id: str) -> tuple[ChronologyEntry, ...]:
        result = []
        for event in self.repository.list("events", project_id):
            dates = [x for x in (event.source_reported_start, event.source_reported_end) if x]
            for index, event_date in enumerate(dates or [date.today()]):
                entry = ChronologyEntry(
                    id=self._id("chrono", event.id, str(index)),
                    project_id=project_id,
                    event_date=event_date,
                    source_date=event.evidence[0].source_date if event.evidence else None,
                    record_type=event.event_type,
                    record_id=event.id,
                    description=event.description,
                    citations=event.evidence,
                    uncertainty=(
                        "Multiple date types are preserved; causation and legal effect are not inferred.",
                    ),
                )
                self.repository.save("chronology", entry.id, entry, immutable=True)
                result.append(entry)
        self._audit(project_id, "chronology_generated", project_id)
        return tuple(sorted(result, key=lambda x: x.event_date))

    def dashboard(self, project_id: str) -> ContractDashboard:
        clauses = self.repository.list("clauses", project_id)
        obligations = self.repository.list("obligations", project_id)
        today = date.today()
        return ContractDashboard(
            project_id=project_id,
            documents=len(self.repository.list("documents", project_id)),
            clauses_awaiting_review=sum(x.review_status == ReviewStatus.PROPOSED for x in clauses),
            notice_candidates=len(self.repository.list("candidates", project_id)),
            obligations_active=sum(x.status == "appears_pending" for x in obligations),
            obligations_overdue=sum(
                x.due_date is not None
                and x.due_date < today
                and x.status != "satisfied_as_confirmed"
                for x in obligations
            ),
            obligations_without_owner=sum(
                x.owner is None and x.status != "satisfied_as_confirmed" for x in obligations
            ),
            conflicts=len(self.repository.list("conflicts", project_id)),
            events_awaiting_review=sum(
                x.reviewer_disposition is None for x in self.repository.list("events", project_id)
            ),
        )

    def search(self, project_id: str, query: str) -> tuple[object, ...]:
        q = query.casefold()
        result = []
        for category in (
            "documents",
            "clauses",
            "terms",
            "requirements",
            "candidates",
            "obligations",
            "events",
            "correspondence",
            "conflicts",
        ):
            result.extend(
                x
                for x in self.repository.list(category, project_id)
                if q in x.model_dump_json().casefold()
            )
        return tuple(result)
