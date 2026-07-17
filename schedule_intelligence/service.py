"""Schedule import, analysis, lineage, comparison, and decision-support services."""

from datetime import UTC, date, datetime, timedelta
from difflib import SequenceMatcher
from hashlib import sha256
from pathlib import Path
import shutil
from uuid import uuid4
from .models import (
    ActivityLineage,
    ActivityStatus,
    ActivityType,
    AuditEvent,
    Criticality,
    CriticalityAssessment,
    FloatHistoryRecord,
    MilestoneVarianceRecord,
    NotificationRequest,
    ProjectSchedule,
    RelationshipType,
    ScheduleActivityChange,
    ScheduleActivityRevision,
    ScheduleCalculationResult,
    ScheduleCalendar,
    ScheduleConstraint,
    ScheduleDashboard,
    ScheduleExposure,
    ScheduleFileFormat,
    ScheduleQualityAssessment,
    ScheduleQualityIssue,
    ScheduleRelationship,
    ScheduleRevision,
    ScheduleRevisionComparison,
    ScheduleSourceReference,
    ScheduleType,
    ScheduleWBSNode,
    SynchronizationProposal,
    WorkflowLink,
)
from .parsers import CSVScheduleParser, XMLScheduleParser, XERScheduleParser
from .repository import JsonScheduleRepository


def _date(value):
    if not value:
        return None
    text = str(value).strip().split(" ")[0]
    for format in (None, "%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return (
                date.fromisoformat(text)
                if format is None
                else datetime.strptime(text, format).date()
            )
        except ValueError:
            pass
    return None


def _float(value):
    try:
        return float(str(value).strip()) if str(value).strip() else None
    except (ValueError, TypeError):
        return None


class ScheduleIntelligenceService:
    def __init__(self, repository: JsonScheduleRepository):
        self.repository = repository

    def import_schedule(
        self,
        project_id: str,
        file_path: Path,
        name: str,
        schedule_type: ScheduleType,
        *,
        revision_label=None,
        revision_number=None,
        predecessor_revision_id=None,
        baseline_revision_id=None,
        imported_by="local-user",
        mapping=None,
        calendar_fallback=False,
    ):
        source = file_path.expanduser().resolve()
        if not source.is_file():
            raise ValueError("Schedule source file not found")
        suffix = source.suffix.lower()
        formats = {
            ".csv": ScheduleFileFormat.CSV,
            ".xml": ScheduleFileFormat.XML,
            ".xer": ScheduleFileFormat.XER,
        }
        if suffix not in formats:
            raise ValueError("Unsupported schedule format")
        content = source.read_bytes()
        digest = sha256(content).hexdigest()
        format = formats[suffix]
        schedule = next(
            (
                x
                for x in self.repository.list("schedules", project_id)
                if x.name.casefold() == name.casefold()
            ),
            None,
        )
        now = datetime.now(UTC)
        if not schedule:
            schedule = ProjectSchedule(
                id="schedule_" + sha256(f"{project_id}|{name}".encode()).hexdigest()[:20],
                project_id=project_id,
                name=name,
                schedule_type=schedule_type,
                created_at=now,
                updated_at=now,
            )
        revision_id = (
            "schedrev_" + sha256(f"{project_id}|{schedule.id}|{digest}".encode()).hexdigest()[:24]
        )
        existing = self.repository.get("revisions", revision_id, project_id)
        if existing:
            return existing
        parser = {
            ScheduleFileFormat.CSV: CSVScheduleParser(),
            ScheduleFileFormat.XML: XMLScheduleParser(),
            ScheduleFileFormat.XER: XERScheduleParser(),
        }[format]
        parsed = parser.parse(source, mapping)
        storage = (
            self.repository.root
            / "source-files"
            / project_id
            / schedule.id
            / revision_id
            / source.name
        )
        storage.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, storage)
        document_id = "scheduledoc_" + digest[:20]
        activities = []
        for index, row in enumerate(parsed.activities, start=1):
            source_id = row.get("activity_id", "").strip()
            if not source_id:
                continue
            citation = ScheduleSourceReference(
                schedule_revision_id=revision_id,
                source_document_id=document_id,
                source_filename=source.name,
                file_format=format,
                source_table=row.get(
                    "_xer_table", "CSV" if format == ScheduleFileFormat.CSV else "XML"
                ),
                source_row=int(row.get("_source_row", index))
                if row.get("_source_row", str(index)).isdigit()
                else index,
                source_record_key=source_id,
                source_activity_id=source_id,
                parser_name=parser.name,
                parser_version=parser.version,
                imported_at=now,
            )
            activity_type = self._type(
                row.get("activity_type", ""), _float(row.get("original_duration"))
            )
            status = self._status(row.get("status", ""), row)
            identity = "activity_" + sha256(f"{schedule.id}|{source_id}".encode()).hexdigest()[:20]
            constraints = ()
            if row.get("constraint_type"):
                constraints = (
                    ScheduleConstraint(
                        constraint_type=self._constraint(row["constraint_type"]),
                        constraint_date=_date(row.get("constraint_date")),
                        original_type=row["constraint_type"],
                        source_field="constraint_type",
                        citation=citation,
                    ),
                )
            activities.append(
                ScheduleActivityRevision(
                    id="activityrev_"
                    + sha256(f"{revision_id}|{source_id}".encode()).hexdigest()[:24],
                    activity_identity_id=identity,
                    project_id=project_id,
                    schedule_id=schedule.id,
                    schedule_revision_id=revision_id,
                    source_activity_id=source_id,
                    name=row.get("activity_name", source_id),
                    activity_type=activity_type,
                    status=status,
                    wbs_id=row.get("wbs_id") or None,
                    wbs_path=row.get("wbs_path") or None,
                    calendar_id=row.get("calendar_id") or None,
                    original_duration=_float(row.get("original_duration")),
                    remaining_duration=_float(row.get("remaining_duration")),
                    actual_duration=_float(row.get("actual_duration")),
                    percent_complete=_float(row.get("percent_complete")),
                    planned_start=_date(row.get("planned_start")),
                    planned_finish=_date(row.get("planned_finish")),
                    actual_start=_date(row.get("actual_start")),
                    actual_finish=_date(row.get("actual_finish")),
                    early_start=_date(row.get("early_start")),
                    early_finish=_date(row.get("early_finish")),
                    late_start=_date(row.get("late_start")),
                    late_finish=_date(row.get("late_finish")),
                    forecast_start=_date(row.get("forecast_start")),
                    forecast_finish=_date(row.get("forecast_finish")),
                    baseline_start=_date(row.get("baseline_start")),
                    baseline_finish=_date(row.get("baseline_finish")),
                    source_total_float=_float(row.get("total_float")),
                    source_free_float=_float(row.get("free_float")),
                    constraints=constraints,
                    activity_codes=self._codes(row.get("activity_codes", "")),
                    location=row.get("location") or None,
                    area=row.get("area") or None,
                    building=row.get("building") or None,
                    floor=row.get("floor") or None,
                    discipline=row.get("discipline") or None,
                    responsible_party=row.get("responsible_party") or None,
                    equipment_tags=tuple(
                        filter(None, (x.strip() for x in row.get("equipment_tags", "").split(";")))
                    ),
                    source_fields={k: str(v) for k, v in row.items() if not k.startswith("_")},
                    citation=citation,
                )
            )
        by_source = {x.source_activity_id: x for x in activities}
        relationships = []
        for index, row in enumerate(parsed.relationships, start=1):
            pred = row.get("predecessor_id", "")
            succ = row.get("successor_id", "")
            citation = ScheduleSourceReference(
                schedule_revision_id=revision_id,
                source_document_id=document_id,
                source_filename=source.name,
                file_format=format,
                source_table=row.get("_xer_table", "relationships"),
                source_row=int(row.get("_source_row", index))
                if str(row.get("_source_row", index)).isdigit()
                else index,
                source_record_key=f"{pred}->{succ}",
                parser_name=parser.name,
                parser_version=parser.version,
                imported_at=now,
            )
            validation = (
                "valid" if pred in by_source and succ in by_source and pred != succ else "invalid"
            )
            relationships.append(
                ScheduleRelationship(
                    id="rel_"
                    + sha256(f"{revision_id}|{pred}|{succ}|{index}".encode()).hexdigest()[:20],
                    revision_id=revision_id,
                    predecessor_id=pred,
                    successor_id=succ,
                    relationship_type=self._relationship(row.get("relationship_type", "FS")),
                    lag=_float(row.get("lag")) or 0,
                    lag_unit="hours" if format == ScheduleFileFormat.XER else "days",
                    source_fields={k: str(v) for k, v in row.items()},
                    citation=citation,
                    validation_status=validation,
                )
            )
        calendars = []
        for index, row in enumerate(parsed.calendars, start=1):
            raw = {str(k): str(v) for k, v in row.items()}
            lower = {k.casefold(): v for k, v in raw.items()}
            source_id = lower.get("clndr_id", lower.get("uid", lower.get("id", str(index))))
            calendars.append(
                ScheduleCalendar(
                    id=f"calendar_{revision_id}_{source_id}",
                    project_id=project_id,
                    revision_id=revision_id,
                    name=lower.get("clndr_name", lower.get("name", source_id)),
                    hours_per_day=_float(lower.get("day_hr_cnt", lower.get("hoursperday"))),
                    hours_per_week=_float(lower.get("week_hr_cnt", lower.get("hoursperweek"))),
                    source_fields=raw,
                    warnings=("Calendar work periods require human review.",),
                )
            )
        wbs_nodes = []
        for index, row in enumerate(parsed.wbs, start=1):
            raw = {str(k): str(v) for k, v in row.items()}
            lower = {k.casefold(): v for k, v in raw.items()}
            source_id = lower.get("wbs_id", lower.get("uid", lower.get("id", str(index))))
            name_value = lower.get("wbs_name", lower.get("name", source_id))
            wbs_nodes.append(
                ScheduleWBSNode(
                    id=f"wbs_{revision_id}_{source_id}",
                    project_id=project_id,
                    revision_id=revision_id,
                    parent_id=lower.get("parent_wbs_id", lower.get("parentuid")) or None,
                    name=name_value,
                    code=lower.get("wbs_short_name", lower.get("code", source_id)),
                    path=lower.get("path", name_value),
                    sequence=index,
                    source_fields=raw,
                )
            )
        starts = [x.planned_start for x in activities if x.planned_start]
        finishes = [
            x.forecast_finish or x.planned_finish
            for x in activities
            if x.forecast_finish or x.planned_finish
        ]
        revision = ScheduleRevision(
            id=revision_id,
            schedule_id=schedule.id,
            project_id=project_id,
            source_document_id=document_id,
            source_filename=source.name,
            file_format=format,
            content_hash=digest,
            revision_label=revision_label,
            revision_number=revision_number,
            data_date=_date(
                parsed.metadata.get("data_date") or parsed.metadata.get("last_recalc_date")
            ),
            planned_project_start=min(starts) if starts else None,
            planned_project_finish=max(finishes) if finishes else None,
            forecast_project_finish=max(finishes) if finishes else None,
            baseline_revision_id=baseline_revision_id,
            imported_at=now,
            imported_by=imported_by,
            parser_name=parser.name,
            parser_version=parser.version,
            activity_count=len(activities),
            milestone_count=sum(
                x.activity_type in {ActivityType.START_MILESTONE, ActivityType.FINISH_MILESTONE}
                for x in activities
            ),
            relationship_count=len(relationships),
            calendar_count=len(calendars),
            wbs_count=len(wbs_nodes),
            constraint_count=sum(len(x.constraints) for x in activities),
            warnings=parsed.unsupported,
            supersedes_revision_id=predecessor_revision_id,
        )
        self.repository.save("revisions", revision.id, revision, immutable=True)
        for item in activities:
            self.repository.save("activities", item.id, item, immutable=True)
        for item in relationships:
            self.repository.save("relationships", item.id, item, immutable=True)
        for item in calendars:
            self.repository.save("calendars", item.id, item, immutable=True)
        for item in wbs_nodes:
            self.repository.save("wbs", item.id, item, immutable=True)
        old_activities = (
            {x.source_activity_id: x for x in self.activities(project_id, predecessor_revision_id)}
            if predecessor_revision_id
            else {}
        )
        for item in activities:
            criticality = self.criticality(item)
            history = FloatHistoryRecord(
                id=f"float_{item.id}",
                project_id=project_id,
                activity_identity_id=item.activity_identity_id,
                revision_id=revision.id,
                data_date=revision.data_date,
                source_total_float=item.source_total_float,
                source_free_float=item.source_free_float,
                criticality=criticality.classification,
            )
            self.repository.save("floats", history.id, history, immutable=True)
            if item.activity_type in {ActivityType.START_MILESTONE, ActivityType.FINISH_MILESTONE}:
                prior = old_activities.get(item.source_activity_id)
                current_forecast = item.forecast_finish or item.planned_finish
                prior_forecast = (prior.forecast_finish or prior.planned_finish) if prior else None
                variance = MilestoneVarianceRecord(
                    id=f"milestone_variance_{item.id}",
                    project_id=project_id,
                    activity_identity_id=item.activity_identity_id,
                    revision_id=revision.id,
                    baseline_date=item.baseline_finish,
                    prior_forecast=prior_forecast,
                    current_forecast=current_forecast,
                    actual_date=item.actual_finish,
                    variance_from_baseline_days=(current_forecast - item.baseline_finish).days
                    if current_forecast and item.baseline_finish
                    else None,
                    variance_from_prior_days=(current_forecast - prior_forecast).days
                    if current_forecast and prior_forecast
                    else None,
                )
                self.repository.save("milestone_variances", variance.id, variance, immutable=True)
        schedule = schedule.model_copy(
            update={
                "current_revision_id": revision.id,
                "baseline_revision_id": baseline_revision_id or schedule.baseline_revision_id,
                "updated_at": now,
            }
        )
        self.repository.save("schedules", schedule.id, schedule)
        self.assess_quality(project_id, revision.id)
        self.calculate_cpm(project_id, revision.id, calendar_fallback=calendar_fallback)
        if predecessor_revision_id:
            self.resolve_lineage(project_id, predecessor_revision_id, revision.id)
        self._audit(
            project_id,
            "schedule_revision_imported",
            revision.id,
            imported_by,
            {"parser": parser.name},
        )
        self._notify(
            project_id,
            "schedule_import_completed",
            revision.id,
            "Schedule import completed; review quality and limitations.",
        )
        return revision

    def activities(self, project_id, revision_id):
        return tuple(
            x
            for x in self.repository.list("activities", project_id)
            if x.schedule_revision_id == revision_id
        )

    def relationships(self, project_id, revision_id):
        return tuple(
            x
            for x in self.repository.list("relationships", project_id)
            if x.revision_id == revision_id
        )

    def assess_quality(self, project_id, revision_id):
        activities = self.activities(project_id, revision_id)
        rels = self.relationships(project_id, revision_id)
        issues = []
        pred = {x.successor_id for x in rels if x.validation_status == "valid"}
        succ = {x.predecessor_id for x in rels if x.validation_status == "valid"}

        def add(cat, severity, code, msg, activity=None):
            issues.append(
                ScheduleQualityIssue(
                    id="sq_" + uuid4().hex,
                    category=cat,
                    severity=severity,
                    code=code,
                    message=msg,
                    activity_id=activity,
                )
            )

        for a in activities:
            if not a.wbs_id:
                add("identity", "warning", "missing_wbs", "Activity has no WBS.", a.id)
            if not a.calendar_id:
                add("calendars", "warning", "missing_calendar", "Activity has no calendar.", a.id)
            if a.source_activity_id not in pred and a.activity_type not in {
                ActivityType.START_MILESTONE
            }:
                add("logic", "warning", "open_start", "Activity has no predecessor.", a.id)
            if a.source_activity_id not in succ and a.activity_type not in {
                ActivityType.FINISH_MILESTONE
            }:
                add("logic", "warning", "open_finish", "Activity has no successor.", a.id)
            if a.planned_start and a.planned_finish and a.planned_finish < a.planned_start:
                add("dates", "error", "invalid_date_order", "Finish precedes start.", a.id)
            if a.status == ActivityStatus.COMPLETED and (a.remaining_duration or 0) > 0:
                add(
                    "progress",
                    "warning",
                    "completed_remaining",
                    "Completed activity retains remaining duration.",
                    a.id,
                )
            if (
                a.activity_type not in {ActivityType.START_MILESTONE, ActivityType.FINISH_MILESTONE}
                and a.original_duration == 0
            ):
                add("duration", "warning", "zero_duration", "Nonmilestone has zero duration.", a.id)
            if any(
                c.constraint_type in {"mandatory_start", "mandatory_finish"} for c in a.constraints
            ):
                add(
                    "constraints",
                    "warning",
                    "hard_constraint",
                    "Hard constraint requires review.",
                    a.id,
                )
            if a.source_total_float is not None and a.source_total_float < 0:
                add(
                    "float",
                    "warning",
                    "negative_float",
                    "Imported source total float is negative; this alone does not prove project delay.",
                    a.id,
                )
        for r in rels:
            if r.validation_status != "valid":
                add(
                    "logic",
                    "error",
                    "invalid_relationship",
                    f"Invalid relationship {r.predecessor_id}->{r.successor_id}.",
                )
            if r.lag < 0:
                add("logic", "warning", "negative_lag", "Negative lag requires review.")
            if abs(r.lag) > 120:
                add("logic", "warning", "excessive_lag", "Large lag requires review.")
        assessment = ScheduleQualityAssessment(
            id="quality_" + revision_id,
            project_id=project_id,
            revision_id=revision_id,
            issues=tuple(issues),
            assessed_at=datetime.now(UTC),
        )
        self.repository.save("quality", assessment.id, assessment)
        return assessment

    def calculate_cpm(self, project_id, revision_id, *, calendar_fallback=False):
        activities = self.activities(project_id, revision_id)
        rels = self.relationships(project_id, revision_id)
        warnings = []
        if not activities:
            supported = False
            warnings.append("No activities available.")
        elif any(a.original_duration is None for a in activities):
            supported = False
            warnings.append("Durations are incomplete; CPM calculation refused.")
        elif any(r.validation_status != "valid" for r in rels):
            supported = False
            warnings.append("Relationship identities are invalid; CPM calculation refused.")
        elif not calendar_fallback and any(not a.calendar_id for a in activities):
            supported = False
            warnings.append("Calendars are incomplete and no explicit fallback was selected.")
        elif self._has_cycle(activities, rels):
            supported = False
            warnings.append("Circular logic detected; CPM calculation refused.")
        else:
            supported = True
        metrics = {}
        if supported:
            by = {a.source_activity_id: a for a in activities}
            incoming = {x: [] for x in by}
            outgoing = {x: [] for x in by}
            for r in rels:
                incoming[r.successor_id].append(r)
                outgoing[r.predecessor_id].append(r)
            remaining = set(by)
            early = {}
            project_start = min(
                (a.planned_start for a in activities if a.planned_start), default=date.today()
            )
            while remaining:
                ready = [
                    x for x in remaining if all(r.predecessor_id in early for r in incoming[x])
                ]
                if not ready:
                    break
                for key in ready:
                    a = by[key]
                    start = max(
                        [
                            early[r.predecessor_id][1] + timedelta(days=int(r.lag))
                            for r in incoming[key]
                        ]
                        or [a.planned_start or project_start]
                    )
                    finish = start + timedelta(days=int(a.original_duration or 0))
                    early[key] = (start, finish)
                    remaining.remove(key)
            project_finish = max((v[1] for v in early.values()), default=project_start)
            late = {}
            remaining = set(by)
            while remaining:
                ready = [x for x in remaining if all(r.successor_id in late for r in outgoing[x])]
                if not ready:
                    break
                for key in ready:
                    a = by[key]
                    finish = min(
                        [
                            late[r.successor_id][0] - timedelta(days=int(r.lag))
                            for r in outgoing[key]
                        ]
                        or [project_finish]
                    )
                    start = finish - timedelta(days=int(a.original_duration or 0))
                    late[key] = (start, finish)
                    remaining.remove(key)
            for key, a in by.items():
                es, ef = early[key]
                ls, lf = late[key]
                metrics[a.id] = {
                    "early_start": es,
                    "early_finish": ef,
                    "late_start": ls,
                    "late_finish": lf,
                    "total_float": (ls - es).days,
                }
        result = ScheduleCalculationResult(
            id="calc_" + uuid4().hex,
            revision_id=revision_id,
            supported=supported,
            approximate=bool(supported and calendar_fallback),
            calendar_mode="calendar_day_fallback" if calendar_fallback else "imported_calendar",
            calculated_metrics=metrics,
            warnings=tuple(warnings)
            + (
                ("Approximate calendar-day fallback; no P6/MS Project parity is claimed.",)
                if supported and calendar_fallback
                else ()
            ),
            calculated_at=datetime.now(UTC),
        )
        self.repository.save("calculations", result.id, result, immutable=True)
        return result

    def criticality(self, activity, calculation=None):
        value = activity.source_total_float
        method = "source_total_float"
        if value is None and calculation:
            value = calculation.calculated_metrics.get(activity.id, {}).get("total_float")
            method = "calculated_total_float"
        classification = (
            Criticality.INDETERMINATE
            if value is None
            else Criticality.CRITICAL
            if value <= 0
            else Criticality.NEAR_CRITICAL
            if value <= 20
            else Criticality.NONCRITICAL
        )
        return CriticalityAssessment(
            activity_revision_id=activity.id,
            classification=classification,
            method=method if value is not None else "insufficient_data",
            metric_value=value,
        )

    def resolve_lineage(self, project_id, old_revision_id, new_revision_id):
        old = self.activities(project_id, old_revision_id)
        new = self.activities(project_id, new_revision_id)
        results = []
        used = set()
        for current in new:
            scored = []
            for prior in old:
                score = 0.7 if prior.source_activity_id == current.source_activity_id else 0
                score += (
                    0.2
                    * SequenceMatcher(None, prior.name.casefold(), current.name.casefold()).ratio()
                )
                score += 0.1 if prior.wbs_path and prior.wbs_path == current.wbs_path else 0
                scored.append((score, prior))
            scored.sort(key=lambda x: x[0], reverse=True)
            best = scored[0] if scored else (0, None)
            ambiguous = len(scored) > 1 and best[0] - scored[1][0] < 0.08
            status = (
                "added"
                if best[0] < 0.55
                else "ambiguous"
                if ambiguous
                else "unchanged_identity"
                if best[1].source_activity_id == current.source_activity_id
                else "renumbered"
            )
            lineage = ActivityLineage(
                id="lineage_"
                + sha256(f"{old_revision_id}|{new_revision_id}|{current.id}".encode()).hexdigest()[
                    :20
                ],
                project_id=project_id,
                old_activity_revision_id=best[1].id if best[1] and best[0] >= 0.55 else None,
                new_activity_revision_id=current.id,
                status=status,
                confidence=best[0],
                reasons=("same source ID",)
                if best[1] and best[1].source_activity_id == current.source_activity_id
                else ("name/WBS similarity",),
                candidates=tuple(x[1].id for x in scored[:3]),
            )
            self.repository.save("lineage", lineage.id, lineage)
            results.append(lineage)
            used.add(best[1].id if best[1] and best[0] >= 0.55 else "")
        for prior in old:
            if prior.id not in used:
                lineage = ActivityLineage(
                    id="lineage_" + uuid4().hex,
                    project_id=project_id,
                    old_activity_revision_id=prior.id,
                    status="removed",
                    confidence=1,
                    reasons=("No matching activity in new revision",),
                )
                self.repository.save("lineage", lineage.id, lineage)
                results.append(lineage)
        return tuple(results)

    def review_lineage(self, project_id, lineage_id, decision, reviewer):
        item = self.repository.get("lineage", lineage_id, project_id)
        if not isinstance(item, ActivityLineage):
            raise ValueError("Lineage record not found")
        updated = item.model_copy(
            update={"status": decision, "reviewer": reviewer, "reviewed_at": datetime.now(UTC)}
        )
        self.repository.save("lineage", updated.id, updated)
        self._audit(project_id, "activity_lineage_reviewed", updated.id, reviewer)
        return updated

    def compare(self, project_id, old_revision_id, new_revision_id):
        oldrev = self.repository.get("revisions", old_revision_id, project_id)
        newrev = self.repository.get("revisions", new_revision_id, project_id)
        if (
            not isinstance(oldrev, ScheduleRevision)
            or not isinstance(newrev, ScheduleRevision)
            or oldrev.schedule_id != newrev.schedule_id
        ):
            raise ValueError("Comparable project schedule revisions required")
        old = {x.source_activity_id: x for x in self.activities(project_id, old_revision_id)}
        new = {x.source_activity_id: x for x in self.activities(project_id, new_revision_id)}
        old_logic = {
            (x.predecessor_id, x.successor_id, x.relationship_type.value, x.lag)
            for x in self.relationships(project_id, old_revision_id)
        }
        new_logic = {
            (x.predecessor_id, x.successor_id, x.relationship_type.value, x.lag)
            for x in self.relationships(project_id, new_revision_id)
        }
        changes = []
        for key in sorted(set(old) | set(new)):
            a = old.get(key)
            b = new.get(key)
            types = []
            if not a:
                types = ["activity_added"]
            elif not b:
                types = ["activity_removed"]
            else:
                old_finish = a.forecast_finish or a.planned_finish
                new_finish = b.forecast_finish or b.planned_finish
                if old_finish and new_finish and new_finish > old_finish:
                    types.append("activity_delayed")
                if old_finish and new_finish and new_finish < old_finish:
                    types.append("activity_accelerated")
                if b.original_duration != a.original_duration:
                    types.append(
                        "duration_increased"
                        if (b.original_duration or 0) > (a.original_duration or 0)
                        else "duration_decreased"
                    )
                if b.source_total_float != a.source_total_float:
                    types.append(
                        "float_decreased"
                        if (b.source_total_float or 0) < (a.source_total_float or 0)
                        else "float_increased"
                    )
                if b.constraints != a.constraints:
                    types.append("constraint_changed")
                if b.wbs_path != a.wbs_path:
                    types.append("wbs_changed")
                if b.name != a.name:
                    types.append("renamed")
                if b.status != a.status or b.percent_complete != a.percent_complete:
                    types.append("progress_changed")
                old_predecessors = {x for x in old_logic if x[1] == key}
                new_predecessors = {x for x in new_logic if x[1] == key}
                if old_predecessors != new_predecessors:
                    types.append("resequenced")
                    if {x[0] for x in new_predecessors} - {x[0] for x in old_predecessors}:
                        types.append("predecessor_added")
                    if {x[0] for x in old_predecessors} - {x[0] for x in new_predecessors}:
                        types.append("predecessor_removed")
                old_criticality = self.criticality(a).classification
                new_criticality = self.criticality(b).classification
                if old_criticality != new_criticality:
                    if new_criticality == Criticality.CRITICAL:
                        types.append("became_critical")
                    elif new_criticality == Criticality.NEAR_CRITICAL:
                        types.append("became_near_critical")
                    elif old_criticality == Criticality.CRITICAL:
                        types.append("no_longer_critical")
            if types:
                changes.append(
                    ScheduleActivityChange(
                        id="schedchange_" + uuid4().hex,
                        activity_identity_id=(b or a).activity_identity_id,
                        old_activity_revision_id=a.id if a else None,
                        new_activity_revision_id=b.id if b else None,
                        change_types=tuple(types),
                        summary=f"{(b or a).source_activity_id}: {', '.join(types)}. Causation and contractual impact are not established.",
                        old_citation=a.citation if a else None,
                        new_citation=b.citation if b else None,
                    )
                )
        finish_change = (
            (newrev.forecast_project_finish - oldrev.forecast_project_finish).days
            if newrev.forecast_project_finish and oldrev.forecast_project_finish
            else None
        )
        result = ScheduleRevisionComparison(
            id="schedcompare_"
            + sha256(f"{old_revision_id}|{new_revision_id}".encode()).hexdigest()[:20],
            project_id=project_id,
            schedule_id=oldrev.schedule_id,
            old_revision_id=old_revision_id,
            new_revision_id=new_revision_id,
            changes=tuple(changes),
            project_finish_change_days=finish_change,
            created_at=datetime.now(UTC),
            limitations=(
                "Deterministic comparison is not a forensic delay analysis.",
                "Responsibility, causation, concurrency, and entitlement are not established.",
            ),
        )
        self.repository.save("comparisons", result.id, result, immutable=True)
        self._notify(
            project_id,
            "schedule_comparison_completed",
            result.id,
            "Schedule comparison completed; human review required.",
        )
        return result

    def link_activity(self, project_id, activity_id, workflow_type, reference, relationship, actor):
        item = self.repository.get("activities", activity_id, project_id)
        if not isinstance(item, ScheduleActivityRevision):
            raise ValueError("Activity not found")
        link = WorkflowLink(
            id="schedlink_" + uuid4().hex,
            workflow_type=workflow_type,
            reference=reference,
            relationship=relationship,
            created_by=actor,
            created_at=datetime.now(UTC),
        )
        updated = item.model_copy(
            update={"workflow_links": item.workflow_links + (link,), "human_confirmed": True}
        )
        self.repository.save("activities", updated.id, updated)
        return updated

    def propose_sync(
        self, project_id, activity_id, workflow_type, reference, existing_date, relationship
    ):
        activity = self.repository.get("activities", activity_id, project_id)
        if not isinstance(activity, ScheduleActivityRevision):
            raise ValueError("Activity not found")
        proposed = activity.forecast_start or activity.planned_start
        if not proposed:
            raise ValueError("Activity has no supported synchronization date")
        record = SynchronizationProposal(
            id="sync_" + uuid4().hex,
            project_id=project_id,
            revision_id=activity.schedule_revision_id,
            activity_revision_id=activity.id,
            workflow_type=workflow_type,
            workflow_reference=reference,
            existing_date=existing_date,
            proposed_date=proposed,
            difference_days=(proposed - existing_date).days if existing_date else None,
            relationship=relationship,
            evidence=activity.citation,
            potential_consequence="Review downstream planning date; no downstream record has been changed.",
        )
        self.repository.save("proposals", record.id, record)
        return record

    def review_proposal(self, project_id, proposal_id, decision, reviewer):
        item = self.repository.get("proposals", proposal_id, project_id)
        if not isinstance(item, SynchronizationProposal):
            raise ValueError("Proposal not found")
        if decision not in {"accept", "reject", "modify"}:
            raise ValueError("Unsupported proposal decision")
        updated = item.model_copy(
            update={
                "review_status": decision,
                "reviewer": reviewer,
                "reviewed_at": datetime.now(UTC),
                "downstream_updated": False,
            }
        )
        self.repository.save("proposals", updated.id, updated)
        self._audit(
            project_id,
            "synchronization_proposal_reviewed",
            updated.id,
            reviewer,
            {"decision": decision},
        )
        return updated

    def lookahead(self, project_id, revision_id, start, end, date_field):
        if date_field not in {"planned", "forecast", "early"}:
            raise ValueError("Explicit date field policy is required")

        def dates(a):
            return (
                (a.planned_start, a.planned_finish)
                if date_field == "planned"
                else (a.forecast_start, a.forecast_finish)
                if date_field == "forecast"
                else (a.early_start, a.early_finish)
            )

        return tuple(
            a
            for a in self.activities(project_id, revision_id)
            if any(x and start <= x <= end for x in dates(a))
        )

    def search(self, project_id, query, revision_id=None):
        needle = query.casefold()
        items = self.repository.list("activities", project_id)
        return tuple(
            a
            for a in items
            if (not revision_id or a.schedule_revision_id == revision_id)
            and needle
            in " ".join(
                str(x or "")
                for x in (
                    a.source_activity_id,
                    a.name,
                    a.wbs_path,
                    a.discipline,
                    a.responsible_party,
                    a.equipment_tags,
                    a.activity_codes,
                    a.workflow_links,
                )
            ).casefold()
        )

    def assess_exposures(self, project_id, revision_id):
        exposures = []
        for activity in self.activities(project_id, revision_id):
            criticality = self.criticality(activity)
            types = []
            reasons = []
            if activity.source_total_float is not None and activity.source_total_float < 0:
                types.append("negative_float")
                reasons.append("Imported source total float is negative.")
            if criticality.classification == Criticality.NEAR_CRITICAL:
                types.append("near_critical")
                reasons.append("Activity is near-critical under policy criticality-1.")
            for link in activity.workflow_links:
                types.append(f"{link.workflow_type}_dependency")
                reasons.append(f"Human-confirmed link to {link.workflow_type} {link.reference}.")
            if not reasons:
                continue
            level = "high" if "negative_float" in types else "medium"
            record = ScheduleExposure(
                id=f"exposure_{activity.id}",
                project_id=project_id,
                revision_id=revision_id,
                activity_revision_id=activity.id,
                level=level,
                exposure_types=tuple(types),
                reasons=tuple(reasons),
                evidence_strength="moderate",
            )
            self.repository.save("exposures", record.id, record)
            exposures.append(record)
        return tuple(exposures)

    def dashboard(self, project_id, revision_id=None):
        schedules = self.repository.list("schedules", project_id)
        if revision_id is None and schedules:
            revision_id = schedules[-1].current_revision_id
        if not revision_id:
            return ScheduleDashboard(
                project_id=project_id,
                revision_id=None,
                data_date=None,
                total_activities=0,
                status_counts={},
                critical=0,
                near_critical=0,
                negative_float=0,
                quality_issues=0,
                lineage_review_required=0,
                pending_synchronization=0,
            )
        revision = self.repository.get("revisions", revision_id, project_id)
        items = self.activities(project_id, revision_id)
        status = {}
        assessments = [self.criticality(x) for x in items]
        for a in items:
            status[a.status.value] = status.get(a.status.value, 0) + 1
        quality = self.repository.get("quality", "quality_" + revision_id, project_id)
        lineage = self.repository.list("lineage", project_id)
        proposals = self.repository.list("proposals", project_id)
        return ScheduleDashboard(
            project_id=project_id,
            revision_id=revision_id,
            data_date=revision.data_date if revision else None,
            total_activities=len(items),
            status_counts=status,
            critical=sum(x.classification == Criticality.CRITICAL for x in assessments),
            near_critical=sum(x.classification == Criticality.NEAR_CRITICAL for x in assessments),
            negative_float=sum(
                (x.source_total_float or 0) < 0 for x in items if x.source_total_float is not None
            ),
            quality_issues=len(quality.issues) if quality else 0,
            lineage_review_required=sum(x.status == "ambiguous" for x in lineage),
            pending_synchronization=sum(x.review_status == "pending" for x in proposals),
        )

    def _type(self, value, duration):
        low = value.casefold()
        if "start" in low and "milestone" in low:
            return ActivityType.START_MILESTONE
        if "finish" in low and "milestone" in low or low in {"milestone", "true"}:
            return ActivityType.FINISH_MILESTONE
        return ActivityType.TASK_DEPENDENT if value or duration else ActivityType.UNKNOWN

    def _status(self, value, row):
        low = value.casefold()
        if "complete" in low or row.get("actual_finish"):
            return ActivityStatus.COMPLETED
        if "progress" in low or row.get("actual_start"):
            return ActivityStatus.IN_PROGRESS
        return (
            ActivityStatus.NOT_STARTED
            if low in {"not_started", "not started", "tk_notstart", "0", ""}
            else ActivityStatus.UNKNOWN
        )

    def _relationship(self, value):
        low = value.casefold().replace("_", "").replace("-", "")
        return {
            "fs": RelationshipType.FS,
            "prfs": RelationshipType.FS,
            "finishtostart": RelationshipType.FS,
            "ss": RelationshipType.SS,
            "prss": RelationshipType.SS,
            "ff": RelationshipType.FF,
            "prff": RelationshipType.FF,
            "sf": RelationshipType.SF,
            "prsf": RelationshipType.SF,
        }.get(low, RelationshipType.UNKNOWN)

    def _constraint(self, value):
        return value.casefold().replace(" ", "_").replace("-", "_")

    def _codes(self, value):
        return {
            p.split("=", 1)[0].strip(): p.split("=", 1)[1].strip()
            for p in value.split(";")
            if "=" in p
        }

    def _has_cycle(self, activities, rels):
        graph = {a.source_activity_id: [] for a in activities}
        for r in rels:
            if r.validation_status == "valid":
                graph[r.predecessor_id].append(r.successor_id)
        visiting = set()
        visited = set()

        def visit(n):
            if n in visiting:
                return True
            if n in visited:
                return False
            visiting.add(n)
            if any(visit(x) for x in graph[n]):
                return True
            visiting.remove(n)
            visited.add(n)
            return False

        return any(visit(x) for x in graph)

    def _audit(self, p, event, subject, actor, metadata=None):
        item = AuditEvent(
            id="saudit_" + uuid4().hex,
            project_id=p,
            event_type=event,
            subject_id=subject,
            actor=actor,
            created_at=datetime.now(UTC),
            metadata=metadata or {},
        )
        self.repository.save("audit", item.id, item, immutable=True)

    def _notify(self, p, event, subject, summary):
        item = NotificationRequest(
            id="snotify_" + uuid4().hex,
            project_id=p,
            event_type=event,
            subject_id=subject,
            summary=summary,
            created_at=datetime.now(UTC),
        )
        self.repository.save("outbox", item.id, item, immutable=True)
