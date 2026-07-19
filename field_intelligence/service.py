from datetime import UTC, datetime, timedelta
from hashlib import sha256
import csv
import io
import json
import re
import shutil
from pathlib import Path
from uuid import uuid4
from pypdf import PdfReader
from .models import (
    AuditEvent,
    DailyReport,
    DailyReportComparison,
    DailyReportRevision,
    EvidenceReference,
    FieldDashboard,
    FieldObservation,
    ObservationType,
    ProgressProposal,
    PlannedWork,
    ProjectDay,
    ReportChange,
    ReportStatus,
    ScheduleLinkProposal,
    SourceType,
    WeeklyFieldSummary,
)


class FieldIntelligenceService:
    TRANSITIONS = {
        ReportStatus.DRAFT: {ReportStatus.UNDER_REVIEW},
        ReportStatus.UNDER_REVIEW: {
            ReportStatus.REVISIONS_REQUIRED,
            ReportStatus.APPROVED,
            ReportStatus.ACCEPTED,
        },
        ReportStatus.REVISIONS_REQUIRED: {ReportStatus.UNDER_REVIEW},
        ReportStatus.APPROVED: {ReportStatus.ISSUED_INTERNAL},
        ReportStatus.ACCEPTED: {ReportStatus.ISSUED_INTERNAL, ReportStatus.SUPERSEDED},
        ReportStatus.ISSUED_INTERNAL: {ReportStatus.CORRECTED},
    }

    def __init__(self, repository):
        self.repository = repository

    def create_day(
        self, project_id, day, shift="day", timezone="UTC", planned_schedule_revision_id=None
    ):
        now = datetime.now(UTC)
        identifier = "day_" + sha256(f"{project_id}|{day}|{shift}".encode()).hexdigest()[:20]
        existing = self.repository.get("days", identifier, project_id)
        if existing:
            return existing
        item = ProjectDay(
            id=identifier,
            project_id=project_id,
            day=day,
            shift=shift,
            timezone=timezone,
            planned_schedule_revision_id=planned_schedule_revision_id,
            created_at=now,
            updated_at=now,
        )
        self.repository.save("days", item.id, item)
        self._audit(project_id, "project_day_created", item.id, "system")
        return item

    def create_report(
        self,
        project_id,
        day,
        *,
        shift="day",
        prepared_by=None,
        text="",
        source_type=SourceType.MANUAL,
        predecessor_revision_id=None,
        source_filename=None,
    ):
        project_day = self.create_day(project_id, day, shift)
        now = datetime.now(UTC)
        report_id = "daily_" + sha256(f"{project_id}|{day}|{shift}".encode()).hexdigest()[:20]
        report = self.repository.get("reports", report_id, project_id)
        if not report:
            report = DailyReport(
                id=report_id,
                project_id=project_id,
                project_day_id=project_day.id,
                created_at=now,
                updated_at=now,
            )
        existing_revisions = tuple(
            x
            for x in self.repository.list("revisions", project_id)
            if x.daily_report_id == report_id
        )
        digest = sha256(text.encode()).hexdigest()
        existing = next((x for x in existing_revisions if x.content_hash == digest), None)
        if existing:
            return report, existing
        number = max([x.revision_number for x in existing_revisions] or [0]) + 1
        revision = DailyReportRevision(
            id="dailyrev_" + sha256(f"{report_id}|{digest}".encode()).hexdigest()[:24],
            daily_report_id=report_id,
            project_id=project_id,
            source_document_id="fielddoc_" + digest[:20],
            source_filename=source_filename,
            revision_number=number,
            content_hash=digest,
            source_type=source_type,
            day=day,
            shift=shift,
            prepared_by=prepared_by,
            created_at=now,
            supersedes_revision_id=predecessor_revision_id,
            original_text=text,
        )
        self.repository.save("revisions", revision.id, revision, immutable=True)
        report = report.model_copy(
            update={
                "current_revision_id": revision.id,
                "updated_at": now,
                "version": report.version + 1 if report.current_revision_id else report.version,
            }
        )
        self.repository.save("reports", report.id, report)
        project_day = project_day.model_copy(
            update={"current_report_revision_id": revision.id, "updated_at": now}
        )
        self.repository.save("days", project_day.id, project_day)
        self._audit(
            project_id, "daily_report_revision_created", revision.id, prepared_by or "local-user"
        )
        return report, revision

    def ingest(
        self,
        project_id,
        day,
        file_path,
        *,
        shift="day",
        prepared_by=None,
        predecessor_revision_id=None,
    ):
        source = Path(file_path).expanduser().resolve()
        allowed = {
            ".csv": SourceType.STRUCTURED,
            ".json": SourceType.STRUCTURED,
            ".pdf": SourceType.PDF,
            ".txt": SourceType.TEXT,
            ".md": SourceType.MARKDOWN,
        }
        if not source.is_file() or source.suffix.lower() not in allowed:
            raise ValueError("Supported daily report file required")
        if source.stat().st_size > 20_000_000:
            raise ValueError("Daily report exceeds local size limit")
        if source.suffix.lower() == ".pdf":
            text = "\n".join(page.extract_text() or "" for page in PdfReader(source).pages)
        else:
            text = source.read_text(encoding="utf-8-sig")
        report, revision = self.create_report(
            project_id,
            day,
            shift=shift,
            prepared_by=prepared_by,
            text=text,
            source_type=allowed[source.suffix.lower()],
            predecessor_revision_id=predecessor_revision_id,
            source_filename=source.name,
        )
        target = (
            self.repository.root
            / "source-files"
            / project_id
            / report.id
            / revision.id
            / source.name
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copyfile(source, target)
        observations = self.analyze(project_id, revision.id)
        return report, revision, observations

    def analyze(self, project_id, revision_id):
        revision = self._revision(project_id, revision_id)
        existing = tuple(
            x
            for x in self.repository.list("observations", project_id)
            if x.revision_id == revision_id
        )
        if existing:
            return existing
        rows = []
        if revision.source_filename and revision.source_filename.lower().endswith(".json"):
            try:
                data = json.loads(revision.original_text)
                rows = data if isinstance(data, list) else data.get("observations", [])
            except (ValueError, TypeError):
                rows = []
        elif revision.source_filename and revision.source_filename.lower().endswith(".csv"):
            rows = list(csv.DictReader(io.StringIO(revision.original_text)))
        else:
            rows = [
                {"description": line.strip()}
                for line in revision.original_text.splitlines()
                if line.strip()
            ]
        results = []
        for index, row in enumerate(rows, start=1):
            text = str(row.get("description", row.get("text", ""))).strip()
            kind = self._kind(str(row.get("type", "")), text)
            if not text and kind is None:
                continue
            kind = kind or ObservationType.WORK
            locator = (
                f"row {index}" if revision.source_type == SourceType.STRUCTURED else f"line {index}"
            )
            citation = EvidenceReference(
                revision_id=revision.id,
                source_document_id=revision.source_document_id,
                source_filename=revision.source_filename or "manual",
                source_type=revision.source_type,
                source_locator=locator,
                exact_excerpt=text[:500],
                record_key=str(index),
                imported_at=revision.created_at,
            )
            headcount = self._int(row.get("headcount")) or self._extract_count(text)
            percent = self._number(row.get("percent_complete"))
            quantity = self._number(row.get("quantity"))
            delivery_status = str(row.get("delivery_status", self._delivery_status(text))) or None
            inspection = str(row.get("inspection_result", self._inspection(text))) or None
            item = FieldObservation(
                id="obs_" + sha256(f"{revision.id}|{index}|{text}".encode()).hexdigest()[:24],
                project_id=project_id,
                report_id=revision.daily_report_id,
                revision_id=revision.id,
                observation_type=kind,
                title=str(row.get("title", kind.value.replace("_", " ").title())),
                description=text,
                company=row.get("company") or None,
                trade=row.get("trade") or None,
                headcount=headcount,
                area=row.get("area") or None,
                room=row.get("room") or None,
                system=row.get("system") or None,
                equipment_tag=row.get("equipment_tag") or None,
                quantity=quantity,
                unit=row.get("unit") or None,
                percent_complete=percent,
                delivery_status=delivery_status,
                accepted=str(row.get("accepted", "")).casefold() == "true",
                inspection_result=inspection,
                severity=row.get("severity") or None,
                impact_status=str(row.get("impact_status", "observation_only")),
                citation=citation,
            )
            self.repository.save("observations", item.id, item, immutable=True)
            results.append(item)
            self._audit(project_id, "observation_extracted", item.id, "system")
        return tuple(results)

    def review_observation(
        self, project_id, observation_id, decision, reviewer, *, description=None
    ):
        item = self._observation(project_id, observation_id)
        if decision not in {
            "confirm",
            "modify",
            "reject",
            "needs_information",
            "split",
            "merge",
            "reclassify",
        }:
            raise ValueError("Unsupported review decision")
        updated = item.model_copy(
            update={
                "status": decision,
                "human_confirmed": decision in {"confirm", "modify"},
                "reviewer": reviewer,
                "reviewed_at": datetime.now(UTC),
                "description": description or item.description,
                "original_proposal_id": item.original_proposal_id or item.id,
            }
        )
        self.repository.save("observations", updated.id, updated)
        self._audit(project_id, "observation_reviewed", item.id, reviewer, {"decision": decision})
        return updated

    def transition(self, project_id, report_id, status, actor):
        report = self._report(project_id, report_id)
        if report.status in {
            ReportStatus.ACCEPTED,
            ReportStatus.ISSUED_INTERNAL,
        } and status not in {
            ReportStatus.SUPERSEDED,
            ReportStatus.CORRECTED,
        }:
            raise ValueError("Accepted or issued reports are immutable")
        if status not in self.TRANSITIONS.get(report.status, set()):
            raise ValueError("Invalid daily report transition")
        if report.status == ReportStatus.ISSUED_INTERNAL:
            raise ValueError("Issued reports are immutable; create a correction revision")
        revision = self._revision(project_id, report.current_revision_id)
        now = datetime.now(UTC)
        changes = {"status": status, "updated_at": now}
        if status in {ReportStatus.APPROVED, ReportStatus.ACCEPTED}:
            revision = revision.model_copy(update={"reviewed_by": actor, "reviewed_at": now})
        if status == ReportStatus.ISSUED_INTERNAL:
            revision = revision.model_copy(update={"issued_by": actor, "issued_at": now})
        self.repository.save("revisions", revision.id, revision)
        updated = report.model_copy(update=changes)
        self.repository.save("reports", updated.id, updated)
        self._audit(project_id, "report_status_changed", report_id, actor, {"status": status})
        self._notify(
            project_id,
            f"report_{status.value}",
            report_id,
            f"Daily report status changed to {status.value}.",
        )
        return updated

    def void_report(self, project_id, report_id, actor, reason):
        if not reason:
            raise ValueError("Voiding requires a reason")
        report = self._report(project_id, report_id)
        updated = report.model_copy(
            update={"status": ReportStatus.VOIDED, "updated_at": datetime.now(UTC)}
        )
        self.repository.save("reports", updated.id, updated)
        self._audit(project_id, "report_voided", report_id, actor, {"reason": reason})
        return updated

    def supersede_report(self, project_id, report_id, replacement_revision_id, actor, reason):
        report = self._report(project_id, report_id)
        replacement = self._revision(project_id, replacement_revision_id)
        if replacement.daily_report_id != report.id or not reason:
            raise ValueError("A valid superseding revision and reason are required")
        updated = report.model_copy(
            update={
                "status": ReportStatus.SUPERSEDED,
                "current_revision_id": replacement.id,
                "updated_at": datetime.now(UTC),
            }
        )
        self.repository.save("reports", updated.id, updated)
        self._audit(project_id, "accepted_report_superseded", report_id, actor, {"reason": reason})
        return updated

    def add_planned_work(
        self, project_id, report_id, description, planned_start, source_system, **values
    ):
        self._report(project_id, report_id)
        item = PlannedWork(
            id="planned_" + uuid4().hex,
            project_id=project_id,
            report_id=report_id,
            description=description,
            planned_start=planned_start,
            source_system=source_system,
            **values,
        )
        self.repository.save("planned_work", item.id, item, immutable=True)
        return item

    def draft(self, project_id, report_id, include_unconfirmed=False):
        report = self._report(project_id, report_id)
        revision = self._revision(project_id, report.current_revision_id)
        items = [
            x
            for x in self.repository.list("observations", project_id)
            if x.report_id == report_id and (x.human_confirmed or include_unconfirmed)
        ]
        lines = [f"# Daily Report — {revision.day}", "", f"Status: {report.status.value}", ""]
        for kind in ObservationType:
            selected = [x for x in items if x.observation_type == kind]
            if selected:
                lines += (
                    [f"## {kind.value.replace('_', ' ').title()}", ""]
                    + [
                        f"- {x.description} ({'confirmed' if x.human_confirmed else 'unconfirmed'})"
                        for x in selected
                    ]
                    + [""]
                )
        lines += [
            "Reported observations are project records; contractual schedule impact, responsibility, and entitlement are not established."
        ]
        return "\n".join(lines) + "\n"

    def suggest_schedule_links(self, project_id, report_id, schedule_activities):
        observations = [
            x for x in self.repository.list("observations", project_id) if x.report_id == report_id
        ]
        proposals = []
        for obs in observations:
            for activity in schedule_activities:
                signals = []
                text = obs.description.casefold()
                if activity.source_activity_id.casefold() in text:
                    signals.append("exact_activity_id")
                if activity.equipment_tags and any(
                    tag.casefold() in text for tag in activity.equipment_tags
                ):
                    signals.append("equipment_tag")
                if activity.name.casefold() in text:
                    signals.append("exact_activity_name")
                if signals:
                    proposal = ScheduleLinkProposal(
                        id="fieldlink_"
                        + sha256(f"{obs.id}|{activity.id}".encode()).hexdigest()[:20],
                        project_id=project_id,
                        report_id=report_id,
                        observation_id=obs.id,
                        schedule_activity_id=activity.id,
                        signals=tuple(signals),
                        strength=min(1, 0.5 + 0.2 * len(signals)),
                        evidence=obs.citation,
                    )
                    self.repository.save("schedule_links", proposal.id, proposal)
                    proposals.append(proposal)
        return tuple(proposals)

    def review_schedule_link(self, project_id, proposal_id, decision, reviewer):
        return self._review_proposal("schedule_links", project_id, proposal_id, decision, reviewer)

    def create_progress_proposals(self, project_id, report_id):
        links = [
            x
            for x in self.repository.list("schedule_links", project_id)
            if x.report_id == report_id and x.review_status == "accept"
        ]
        proposals = []
        for link in links:
            obs = self._observation(project_id, link.observation_id)
            status = (
                "completed"
                if obs.status == "completed_reported"
                else "in_progress"
                if obs.status in {"started", "ongoing"}
                else None
            )
            proposal = ProgressProposal(
                id="progress_" + sha256(link.id.encode()).hexdigest()[:20],
                project_id=project_id,
                report_id=report_id,
                observation_id=obs.id,
                schedule_activity_id=link.schedule_activity_id,
                reported_status=obs.status,
                proposed_schedule_status=status,
                proposed_percent_complete=obs.percent_complete,
                evidence=obs.citation,
                conflicts=("Reported completion is not schedule confirmation.",),
            )
            self.repository.save("progress", proposal.id, proposal)
            proposals.append(proposal)
        return tuple(proposals)

    def review_progress(self, project_id, proposal_id, decision, reviewer):
        return self._review_proposal("progress", project_id, proposal_id, decision, reviewer)

    def planned_vs_reported(self, project_id, report_id, schedule_activities):
        observations = [
            x
            for x in self.repository.list("observations", project_id)
            if x.report_id == report_id and x.observation_type == ObservationType.WORK
        ]
        links = {
            x.schedule_activity_id
            for x in self.repository.list("schedule_links", project_id)
            if x.report_id == report_id
        }
        return {
            "planned_reported": tuple(x.id for x in schedule_activities if x.id in links),
            "planned_not_mentioned": tuple(x.id for x in schedule_activities if x.id not in links),
            "unplanned_reported": tuple(
                x.id
                for x in observations
                if not any(
                    link.observation_id == x.id
                    for link in self.repository.list("schedule_links", project_id)
                )
            ),
            "limitations": (
                "Not mentioned does not mean not performed.",
                "Reported completion does not update the schedule.",
            ),
        }

    def compare(self, project_id, old_revision_id, new_revision_id):
        old = {
            x.title.casefold(): x
            for x in self.repository.list("observations", project_id)
            if x.revision_id == old_revision_id
        }
        new = {
            x.title.casefold(): x
            for x in self.repository.list("observations", project_id)
            if x.revision_id == new_revision_id
        }
        changes = []
        for key in sorted(set(old) | set(new)):
            a = old.get(key)
            b = new.get(key)
            kind = (
                "added"
                if not a
                else "removed"
                if not b
                else "corrected"
                if a.description != b.description
                or a.model_dump(exclude={"citation", "reviewed_at", "reviewer"})
                != b.model_dump(exclude={"citation", "reviewed_at", "reviewer"})
                else None
            )
            if kind:
                changes.append(
                    ReportChange(
                        change_type=kind,
                        observation_type=(b or a).observation_type.value,
                        old_observation_id=a.id if a else None,
                        new_observation_id=b.id if b else None,
                        summary=f"{(b or a).title}: {kind}",
                        old_citation=a.citation if a else None,
                        new_citation=b.citation if b else None,
                    )
                )
        result = DailyReportComparison(
            id="fieldcompare_"
            + sha256(f"{old_revision_id}|{new_revision_id}".encode()).hexdigest()[:20],
            project_id=project_id,
            old_revision_id=old_revision_id,
            new_revision_id=new_revision_id,
            changes=tuple(changes),
            created_at=datetime.now(UTC),
        )
        self.repository.save("comparisons", result.id, result, immutable=True)
        return result

    def weekly_summary(self, project_id, week_start):
        reports = [
            x
            for x in self.repository.list("reports", project_id)
            if x.status == ReportStatus.ISSUED_INTERNAL
        ]
        revision_ids = {x.current_revision_id for x in reports}
        observations = [
            x
            for x in self.repository.list("observations", project_id)
            if x.revision_id in revision_ids and x.human_confirmed
        ]
        metrics = {
            kind.value: sum(x.observation_type == kind for x in observations)
            for kind in ObservationType
        }
        summary = WeeklyFieldSummary(
            id="week_" + sha256(f"{project_id}|{week_start}".encode()).hexdigest()[:20],
            project_id=project_id,
            week_start=week_start,
            week_end=week_start + timedelta(days=6),
            issued_report_ids=tuple(x.id for x in reports),
            metrics=metrics,
            confirmed_observations=tuple(x.id for x in observations),
            limitations=("Field summary is not a contractual delay or productivity analysis.",),
            created_at=datetime.now(UTC),
        )
        self.repository.save("weekly", summary.id, summary)
        return summary

    def dashboard(self, project_id):
        reports = self.repository.list("reports", project_id)
        obs = self.repository.list("observations", project_id)
        progress = self.repository.list("progress", project_id)
        return FieldDashboard(
            project_id=project_id,
            reports_issued=sum(x.status == ReportStatus.ISSUED_INTERNAL for x in reports),
            reports_awaiting_review=sum(x.status == ReportStatus.UNDER_REVIEW for x in reports),
            total_manpower=sum(
                x.headcount or 0 for x in obs if x.observation_type == ObservationType.MANPOWER
            ),
            deliveries=sum(x.observation_type == ObservationType.DELIVERY for x in obs),
            partial_or_damaged_deliveries=sum(
                x.observation_type == ObservationType.DELIVERY
                and x.delivery_status in {"partial", "damaged", "short"}
                for x in obs
            ),
            failed_inspections=sum(
                x.observation_type == ObservationType.INSPECTION and x.inspection_result == "failed"
                for x in obs
            ),
            open_safety=sum(
                x.observation_type == ObservationType.SAFETY
                and x.status not in {"closed", "rejected"}
                for x in obs
            ),
            open_quality=sum(
                x.observation_type == ObservationType.QUALITY
                and x.status not in {"closed", "verified"}
                for x in obs
            ),
            open_constraints=sum(
                x.observation_type in {ObservationType.CONSTRAINT, ObservationType.DISRUPTION}
                and x.impact_status != "resolved"
                for x in obs
            ),
            progress_proposals_pending=sum(x.review_status == "pending" for x in progress),
        )

    def search(self, project_id, query):
        needle = query.casefold()
        return tuple(
            x
            for x in self.repository.list("observations", project_id)
            if needle
            in " ".join(
                str(v or "")
                for v in (
                    x.title,
                    x.description,
                    x.company,
                    x.trade,
                    x.area,
                    x.room,
                    x.system,
                    x.equipment_tag,
                    x.delivery_status,
                    x.inspection_result,
                    x.workflow_links,
                )
            ).casefold()
        )

    def _kind(self, raw, text):
        low = f"{raw} {text}".casefold()
        rules = (
            (ObservationType.WEATHER, ("weather", "rain", "wind", "temperature")),
            (ObservationType.MANPOWER, ("manpower", "crew", "workers", "electricians")),
            (ObservationType.DELIVERY, ("delivery", "delivered", "received material")),
            (ObservationType.INSPECTION, ("inspection", "test passed", "test failed")),
            (ObservationType.SAFETY, ("safety", "hazard", "near miss")),
            (ObservationType.QUALITY, ("quality", "deficiency", "corrective")),
            (ObservationType.CONSTRAINT, ("blocked", "constraint", "delay", "access issue")),
            (ObservationType.EQUIPMENT, ("crane", "lift", "excavator", "equipment")),
            (ObservationType.VISITOR, ("visitor", "owner visit")),
            (ObservationType.PHOTO, ("photo", "image")),
        )
        return next(
            (kind for kind, terms in rules if any(term in low for term in terms)),
            ObservationType(raw) if raw in {x.value for x in ObservationType} else None,
        )

    def _delivery_status(self, text):
        return next(
            (
                x
                for x in (
                    "partial",
                    "damaged",
                    "short",
                    "rejected",
                    "accepted",
                    "stored",
                    "received",
                    "arrived",
                )
                if x in text.casefold()
            ),
            "",
        )

    def _inspection(self, text):
        return (
            "failed"
            if "failed" in text.casefold()
            else "passed"
            if "passed" in text.casefold()
            else ""
        )

    def _int(self, v):
        try:
            return int(v) if str(v).strip() else None
        except (ValueError, TypeError):
            return None

    def _number(self, v):
        try:
            return float(v) if str(v).strip() else None
        except (ValueError, TypeError):
            return None

    def _extract_count(self, text):
        match = re.search(
            r"\b(\d+)\s+(?:workers|electricians|carpenters|laborers|crew members)\b", text, re.I
        )
        return int(match.group(1)) if match else None

    def _report(self, p, i):
        value = self.repository.get("reports", i, p)
        if not isinstance(value, DailyReport):
            raise ValueError("Daily report not found")
        return value

    def _revision(self, p, i):
        value = self.repository.get("revisions", i, p)
        if not isinstance(value, DailyReportRevision):
            raise ValueError("Daily report revision not found")
        return value

    def _observation(self, p, i):
        value = self.repository.get("observations", i, p)
        if not isinstance(value, FieldObservation):
            raise ValueError("Observation not found")
        return value

    def _review_proposal(self, category, p, i, decision, reviewer):
        item = self.repository.get(category, i, p)
        if item is None or decision not in {"accept", "reject", "modify"}:
            raise ValueError("Proposal or decision invalid")
        updated = item.model_copy(
            update={
                "review_status": decision,
                "reviewer": reviewer,
                "reviewed_at": datetime.now(UTC),
                **({"schedule_updated": False} if category == "progress" else {}),
            }
        )
        self.repository.save(category, updated.id, updated)
        self._audit(p, f"{category}_reviewed", i, reviewer, {"decision": decision})
        return updated

    def _audit(self, p, event, subject, actor, metadata=None):
        item = AuditEvent(
            id="faudit_" + uuid4().hex,
            project_id=p,
            event_type=event,
            subject_id=subject,
            actor=actor,
            created_at=datetime.now(UTC),
            metadata=metadata or {},
        )
        self.repository.save("audit", item.id, item, immutable=True)

    def _notify(self, p, event, subject, summary):
        from .models import NotificationRequest

        item = NotificationRequest(
            id="fnotify_" + uuid4().hex,
            project_id=p,
            event_type=event,
            subject_id=subject,
            summary=summary,
            created_at=datetime.now(UTC),
        )
        self.repository.save("outbox", item.id, item, immutable=True)
