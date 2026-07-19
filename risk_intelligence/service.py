"""Deterministic candidate generation and human-only risk workflow."""

from datetime import UTC, date, datetime
from hashlib import sha256
from uuid import uuid4
from .models import (
    AuditEvent,
    CommitmentView,
    Correlation,
    DependencyEdge,
    Evidence,
    LinkStrength,
    Mitigation,
    NotificationRequest,
    RiskCandidate,
    RiskDashboard,
    RiskLevel,
    RiskScore,
    RiskStatus,
)
from .repository import JsonRiskRepository


class RiskIntelligenceService:
    def __init__(self, repository: JsonRiskRepository):
        self.repository = repository

    def _id(self, prefix: str, *parts: str) -> str:
        return f"{prefix}_{sha256('|'.join(parts).encode()).hexdigest()[:16]}"

    def _now(self) -> datetime:
        return datetime.now(UTC)

    def _audit(self, project_id: str, event: str, subject: str, actor: str = "brunel") -> None:
        item = AuditEvent(
            id=f"audit_{uuid4().hex[:16]}",
            project_id=project_id,
            event_type=event,
            subject_id=subject,
            actor=actor,
        )
        self.repository.save("audit", item.id, item)

    def _risk(self, project_id: str, risk_id: str) -> RiskCandidate:
        value = self.repository.get("risks", risk_id, project_id)
        if not value:
            raise ValueError("Risk candidate not found in requested project")
        return value

    def score(self, evidence: tuple[Evidence, ...], factors: tuple[str, ...]) -> RiskScore:
        text = " ".join(e.excerpt.casefold() for e in evidence)
        repeated = len(evidence) > 1
        urgent = any(
            x in text
            for x in ("overdue", "late", "unresolved", "blocked", "constraint", "conflict")
        )
        level = (
            RiskLevel.HIGH
            if urgent and repeated
            else RiskLevel.MODERATE
            if urgent or repeated
            else RiskLevel.LOW
        )
        return RiskScore(
            severity=level,
            likelihood=level,
            factors=factors,
            confidence=0.8 if repeated else 0.6,
            uncertainty=(
                "Proposal is evidence-backed but requires human review; no delay, fault, compliance, or entitlement conclusion is made.",
            ),
        )

    def correlate(self, project_id: str, records: tuple[Evidence, ...]) -> tuple[Correlation, ...]:
        output = []
        for i, left in enumerate(records):
            for right in records[i + 1 :]:
                same_location = left.location and left.location == right.location
                same_system = left.system and left.system == right.system
                strength = (
                    LinkStrength.STRONG
                    if same_location or same_system
                    else LinkStrength.WEAK_CANDIDATE
                )
                signals = (
                    ("shared canonical location" if same_location else "shared canonical system")
                    if strength == LinkStrength.STRONG
                    else "similarity requires human review",
                )
                output.append(
                    Correlation(
                        id=self._id("corr", left.record_id, right.record_id),
                        project_id=project_id,
                        left_record_id=left.record_id,
                        right_record_id=right.record_id,
                        signals=signals,
                        strength=strength,
                        confidence=0.85 if strength == LinkStrength.STRONG else 0.4,
                        evidence=(left, right),
                        uncertainty=()
                        if strength == LinkStrength.STRONG
                        else ("Weak correlation is not authoritative linkage.",),
                    )
                )
        return tuple(output)

    def generate(
        self, project_id: str, evidence: tuple[Evidence, ...], category: str = "unknown"
    ) -> tuple[RiskCandidate, ...]:
        groups: dict[str, list[Evidence]] = {}
        for item in evidence:
            text = item.excerpt.casefold()
            if any(
                word in text
                for word in (
                    "unresolved",
                    "overdue",
                    "late",
                    "blocked",
                    "constraint",
                    "conflict",
                    "missing",
                    "damaged",
                )
            ):
                groups.setdefault(
                    category if category != "unknown" else item.record_type, []
                ).append(item)
        result = []
        for name, items in groups.items():
            ev = tuple(items)
            rid = self._id("risk", project_id, name, *sorted(x.record_id for x in ev))
            existing = self.repository.get("risks", rid, project_id)
            if existing:
                result.append(existing)
                continue
            factors = (
                "deterministic unresolved/constraint language",
                "repeated evidence" if len(ev) > 1 else "single evidence source",
            )
            risk = RiskCandidate(
                id=rid,
                project_id=project_id,
                title=f"Review {name} exposure",
                description="; ".join(x.excerpt for x in ev),
                original_source_wording=ev[0].excerpt,
                category=name,
                score=self.score(ev, factors),
                evidence=ev,
                correlations=self.correlate(project_id, ev),
                linked_record_ids=tuple(x.record_id for x in ev),
            )
            self.repository.save("risks", rid, risk)
            self._audit(project_id, "candidate_generated", rid)
            self.repository.save(
                "outbox",
                f"out_{rid}",
                NotificationRequest(
                    id=f"out_{rid}",
                    project_id=project_id,
                    event_type="risk_candidate_awaiting_review",
                    subject_id=rid,
                    summary=risk.title,
                ),
            )
            result.append(risk)
        return tuple(result)

    def review(
        self,
        project_id: str,
        risk_id: str,
        decision: str,
        actor: str,
        rationale: str = "",
        owner: str | None = None,
    ) -> RiskCandidate:
        risk = self._risk(project_id, risk_id)
        mapping = {
            "confirm": RiskStatus.CONFIRMED_FOR_MONITORING,
            "reject": RiskStatus.REJECTED,
            "mitigate": RiskStatus.MITIGATED,
            "close": RiskStatus.CLOSED,
            "reopen": RiskStatus.REOPENED,
        }
        if decision not in mapping:
            raise ValueError("Unsupported risk review decision")
        if decision == "close" and not rationale:
            raise ValueError("Closing a risk requires human rationale and evidence review")
        updated = risk.model_copy(
            update={
                "status": mapping[decision],
                "reviewer": actor,
                "reviewer_disposition": rationale or decision,
                "owner": owner or risk.owner,
                "updated_at": self._now(),
                "version": risk.version + 1,
            }
        )
        self.repository.save("risks", risk_id, updated)
        self._audit(project_id, f"risk_{decision}", risk_id, actor)
        return updated

    def add_mitigation(
        self,
        project_id: str,
        risk_id: str,
        description: str,
        actor: str,
        owner: str | None = None,
        due_date: date | None = None,
    ) -> Mitigation:
        risk = self._risk(project_id, risk_id)
        mid = f"mit_{uuid4().hex[:16]}"
        item = Mitigation(
            id=mid,
            project_id=project_id,
            risk_id=risk_id,
            description=description,
            owner=owner,
            due_date=due_date,
            reviewer=actor,
        )
        self.repository.save("mitigations", mid, item)
        self.repository.save(
            "risks",
            risk_id,
            risk.model_copy(
                update={
                    "mitigation_ids": risk.mitigation_ids + (mid,),
                    "updated_at": self._now(),
                    "version": risk.version + 1,
                }
            ),
        )
        self._audit(project_id, "mitigation_created", mid, actor)
        return item

    def normalize_commitment(
        self,
        project_id: str,
        source_type: str,
        source_id: str,
        title: str,
        evidence: tuple[Evidence, ...],
        owner: str | None = None,
        due_date: date | None = None,
        dependencies: tuple[str, ...] = (),
    ) -> CommitmentView:
        cid = self._id("commit", project_id, source_type, source_id)
        value = CommitmentView(
            id=cid,
            project_id=project_id,
            source_record_type=source_type,
            source_record_id=source_id,
            title=title,
            owner=owner,
            due_date=due_date,
            dependencies=dependencies,
            citations=evidence,
        )
        self.repository.save("commitments", cid, value)
        self._audit(project_id, "commitment_normalized", cid)
        return value

    def confirm_completion(
        self, project_id: str, commitment_id: str, evidence: tuple[Evidence, ...], actor: str
    ) -> CommitmentView:
        item = self.repository.get("commitments", commitment_id, project_id)
        if not item:
            raise ValueError("Commitment not found in requested project")
        if not evidence:
            raise ValueError("Completion confirmation requires evidence")
        updated = item.model_copy(
            update={
                "status": "completed",
                "completion_evidence": evidence,
                "completion_confirmed": True,
            }
        )
        self.repository.save("commitments", commitment_id, updated)
        self._audit(project_id, "commitment_completion_confirmed", commitment_id, actor)
        return updated

    def add_dependency(
        self,
        project_id: str,
        source_id: str,
        target_id: str,
        relationship: str,
        evidence: tuple[Evidence, ...],
    ) -> DependencyEdge:
        edge = DependencyEdge(
            id=self._id("edge", project_id, source_id, target_id, relationship),
            project_id=project_id,
            source_id=source_id,
            target_id=target_id,
            relationship=relationship,
            evidence=evidence,
        )
        self.repository.save("edges", edge.id, edge)
        self._audit(project_id, "dependency_recorded", edge.id)
        return edge

    def blockers(self, project_id: str, record_id: str) -> tuple[DependencyEdge, ...]:
        return tuple(
            x
            for x in self.repository.list("edges", project_id)
            if x.target_id == record_id and not x.resolved
        )

    def downstream(self, project_id: str, record_id: str) -> tuple[DependencyEdge, ...]:
        return tuple(
            x
            for x in self.repository.list("edges", project_id)
            if x.source_id == record_id and not x.resolved
        )

    def dashboard(self, project_id: str) -> RiskDashboard:
        risks = self.repository.list("risks", project_id)
        commitments = self.repository.list("commitments", project_id)
        today = date.today()
        return RiskDashboard(
            project_id=project_id,
            proposed=sum(r.status == RiskStatus.PROPOSED for r in risks),
            confirmed=sum(r.status == RiskStatus.CONFIRMED_FOR_MONITORING for r in risks),
            high_priority_review=sum(
                r.score.severity in (RiskLevel.HIGH, RiskLevel.CRITICAL_REVIEW_REQUIRED)
                and r.status == RiskStatus.PROPOSED
                for r in risks
            ),
            overdue_commitments=sum(
                c.due_date is not None and c.due_date < today and c.status != "completed"
                for c in commitments
            ),
            commitments_without_owner=sum(
                c.owner is None and c.status != "completed" for c in commitments
            ),
            unresolved_dependencies=len(
                [x for x in self.repository.list("edges", project_id) if not x.resolved]
            ),
            stale_risks=sum(
                r.status in (RiskStatus.PROPOSED, RiskStatus.UNDER_REVIEW) for r in risks
            ),
        )

    def search(self, project_id: str, query: str) -> tuple[RiskCandidate, ...]:
        q = query.casefold()
        return tuple(
            r
            for r in self.repository.list("risks", project_id)
            if q in f"{r.title} {r.description} {r.category}".casefold()
        )
