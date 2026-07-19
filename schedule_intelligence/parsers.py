"""Deterministic CSV, constrained XML, and XER schedule adapters."""

import csv
from dataclasses import dataclass
from pathlib import Path
import xml.etree.ElementTree as ET
from p6_adapter.parser import parse_p6


@dataclass(frozen=True)
class ParsedSchedule:
    metadata: dict[str, str]
    activities: tuple[dict[str, str], ...]
    relationships: tuple[dict[str, str], ...]
    calendars: tuple[dict[str, str], ...] = ()
    wbs: tuple[dict[str, str], ...] = ()
    unsupported: tuple[str, ...] = ()


class CSVScheduleParser:
    name = "csv-default"
    version = "1"

    def parse(self, path: Path, mapping: dict[str, str] | None = None) -> ParsedSchedule:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        mapping = mapping or {}
        activities = []
        relationships = []
        for index, row in enumerate(rows, start=2):
            normalized = {
                mapping.get(key, key): value.strip()
                for key, value in row.items()
                if key is not None and value is not None
            }
            normalized["_source_row"] = str(index)
            normalized["_source_fields"] = "|".join(row.keys())
            activities.append(normalized)
            successor = normalized.get("activity_id", "")
            for token in filter(
                None, (x.strip() for x in normalized.get("predecessors", "").split(";"))
            ):
                parts = token.split(":")
                relationships.append(
                    {
                        "predecessor_id": parts[0],
                        "successor_id": successor,
                        "relationship_type": parts[1] if len(parts) > 1 else "FS",
                        "lag": parts[2] if len(parts) > 2 else "0",
                        "_source_row": str(index),
                    }
                )
        return ParsedSchedule({}, tuple(activities), tuple(relationships))


class XMLScheduleParser:
    name = "xml-constrained"
    version = "1"

    def parse(self, path: Path, mapping=None) -> ParsedSchedule:
        # Production-shaped Primavera XML is parsed by the shared safe P6 parser.
        # Keep the constrained fallback below for synthetic MS Project fixtures.
        try:
            source = parse_p6(path)
            selected = _select_p6_project(source.projects, mapping)
            activities, relationships = _canonical_p6_rows(selected)
            return ParsedSchedule(
                selected.metadata,
                activities,
                relationships,
                selected.calendars,
                selected.wbs,
                selected.warnings,
            )
        except ValueError as exc:
            if "no Project element" not in str(exc):
                raise
        root = ET.parse(path).getroot()
        activities = []
        relationships = []
        calendars = []
        wbs = []
        for elem in root.iter():
            tag = elem.tag.split("}")[-1].casefold()
            children = {c.tag.split("}")[-1]: (c.text or "").strip() for c in elem}
            lower = {k.casefold(): v for k, v in children.items()}
            if tag in {"activity", "task"}:
                activities.append(
                    {
                        "activity_id": lower.get(
                            "activityid", lower.get("uid", lower.get("id", ""))
                        ),
                        "activity_name": lower.get("activityname", lower.get("name", "")),
                        "planned_start": lower.get("plannedstart", lower.get("start", "")),
                        "planned_finish": lower.get("plannedfinish", lower.get("finish", "")),
                        "original_duration": lower.get(
                            "originalduration", lower.get("duration", "")
                        ),
                        "activity_type": lower.get("activitytype", lower.get("milestone", "")),
                        "status": lower.get("status", lower.get("percentcomplete", "")),
                        "wbs_id": lower.get("wbsid", lower.get("outlinelevel", "")),
                        "calendar_id": lower.get("calendarid", lower.get("calendaruid", "")),
                        "_xml_path": tag,
                    }
                )
            elif tag in {"relationship", "predecessorlink"}:
                relationships.append(
                    {
                        "predecessor_id": lower.get(
                            "predecessoractivityid", lower.get("predecessoruid", "")
                        ),
                        "successor_id": lower.get(
                            "successoractivityid", lower.get("successoruid", "")
                        ),
                        "relationship_type": lower.get("type", "FS"),
                        "lag": lower.get("lag", "0"),
                    }
                )
            elif tag == "calendar":
                calendars.append(children)
            elif tag in {"wbs", "wbselement"}:
                wbs.append(children)
        return ParsedSchedule(
            {},
            tuple(activities),
            tuple(relationships),
            tuple(calendars),
            tuple(wbs),
            ("XML adapter supports constrained synthetic Primavera/MS Project structures only.",),
        )


class XERScheduleParser:
    name = "primavera-p6-xer"
    version = "1.0.0"

    def parse(self, path: Path, mapping=None) -> ParsedSchedule:
        source = parse_p6(path, encoding=(mapping or {}).get("encoding"))
        selected = _select_p6_project(source.projects, mapping)
        activities, relationships = _canonical_p6_rows(selected)
        return ParsedSchedule(
            selected.metadata,
            activities,
            relationships,
            selected.calendars,
            selected.wbs,
            source.warnings + selected.warnings,
        )


def _ci(row, *names, default=""):
    values = {str(k).casefold(): str(v) for k, v in row.items()}
    return next((values[name.casefold()] for name in names if values.get(name.casefold())), default)


def _select_p6_project(projects, mapping):
    external_id = (mapping or {}).get("p6_project_id")
    if external_id:
        selected = next((p for p in projects if p.external_project_id == external_id), None)
        if not selected:
            raise ValueError("Configured P6 project is not present in source")
        return selected
    if len(projects) != 1:
        raise ValueError("P6 source contains multiple projects; explicit p6_project_id is required")
    return projects[0]


def _canonical_p6_rows(project):
    object_to_code = {
        _ci(row, "task_id", "ObjectId", "UID", "Id"): _ci(
            row, "task_code", "Id", "ActivityId", "UID"
        )
        for row in project.activities
    }
    code_values = {
        _ci(row, "actv_code_id", "ObjectId"): _ci(row, "short_name", "CodeValue", "Value")
        for row in project.activity_codes
        if _ci(row, "actv_code_id", "ObjectId")
    }
    assigned = {}
    for row in project.activity_codes:
        task_id = _ci(row, "task_id", "ActivityObjectId")
        code_id = _ci(row, "actv_code_id", "ActivityCodeObjectId")
        if task_id and code_id:
            assigned.setdefault(task_id, []).append(code_values.get(code_id, code_id))
    udf_titles = {
        _ci(row, "udf_type_id", "ObjectId"): _ci(
            row, "udf_type_label", "Title", "Name", default="UDF"
        )
        for row in project.udfs
        if _ci(row, "udf_type_id", "ObjectId") and _ci(row, "udf_type_label", "Title", "Name")
    }
    udf_assignments = {}
    for row in project.udfs:
        task_id = _ci(row, "fk_id", "task_id", "ActivityObjectId")
        udf_type = _ci(row, "udf_type_id", "UDFTypeObjectId")
        value = _ci(
            row,
            "udf_text",
            "udf_number",
            "udf_date",
            "udf_code_id",
            "TextValue",
            "DoubleValue",
            "DateValue",
            "IndicatorValue",
            "CostValue",
        )
        if task_id and udf_type and value:
            udf_assignments.setdefault(task_id, {})[udf_titles.get(udf_type, udf_type)] = value
    activities = []
    for row in project.activities:
        object_id = _ci(row, "task_id", "ObjectId", "UID")
        code = _ci(row, "task_code", "Id", "ActivityId", "UID", default=object_id)
        item = dict(row)
        item.update(
            {
                f"p6_udf:{title}": value
                for title, value in udf_assignments.get(object_id, {}).items()
            }
        )
        item.update(
            {
                "activity_id": code,
                "activity_name": _ci(row, "task_name", "Name", "ActivityName", default=code),
                "p6_object_id": object_id,
                "p6_project_id": project.external_project_id,
                "wbs_id": _ci(row, "wbs_id", "WBSObjectId", "WBSId"),
                "calendar_id": _ci(row, "clndr_id", "CalendarObjectId", "CalendarId"),
                "status": _ci(row, "status_code", "Status"),
                "activity_type": _ci(row, "task_type", "Type", "ActivityType"),
                "original_duration": _ci(row, "target_drtn_hr_cnt", "OriginalDuration"),
                "remaining_duration": _ci(row, "remain_drtn_hr_cnt", "RemainingDuration"),
                "actual_duration": _ci(row, "act_drtn_hr_cnt", "ActualDuration"),
                "percent_complete": _ci(
                    row, "phys_complete_pct", "PhysicalPercentComplete", "PercentComplete"
                ),
                "percent_complete_type": _ci(row, "complete_pct_type", "PercentCompleteType"),
                "planned_start": _ci(row, "target_start_date", "PlannedStart", "Start"),
                "planned_finish": _ci(row, "target_end_date", "PlannedFinish", "Finish"),
                "actual_start": _ci(row, "act_start_date", "ActualStart"),
                "actual_finish": _ci(row, "act_end_date", "ActualFinish"),
                "early_start": _ci(row, "early_start_date", "EarlyStart"),
                "early_finish": _ci(row, "early_end_date", "EarlyFinish"),
                "late_start": _ci(row, "late_start_date", "LateStart"),
                "late_finish": _ci(row, "late_end_date", "LateFinish"),
                "forecast_finish": _ci(row, "expect_end_date", "ExpectedFinish"),
                "total_float": _ci(row, "total_float_hr_cnt", "TotalFloat"),
                "free_float": _ci(row, "free_float_hr_cnt", "FreeFloat"),
                "constraint_type": _ci(row, "cstr_type", "PrimaryConstraintType", "ConstraintType"),
                "constraint_date": _ci(row, "cstr_date", "PrimaryConstraintDate", "ConstraintDate"),
                "secondary_constraint_type": _ci(row, "cstr_type2", "SecondaryConstraintType"),
                "secondary_constraint_date": _ci(row, "cstr_date2", "SecondaryConstraintDate"),
                "activity_codes": ";".join(
                    f"P6_CODE_{i + 1}={value}"
                    for i, value in enumerate(assigned.get(object_id, []))
                ),
                "_xer_table": "TASK" if "task_id" in row else "Activity",
                "_source_row": row.get("_source_row", ""),
            }
        )
        activities.append(item)
    relationships = []
    for row in project.relationships:
        pred_object = _ci(row, "pred_task_id", "PredecessorActivityObjectId", "PredecessorUID")
        succ_object = _ci(row, "task_id", "SuccessorActivityObjectId", "SuccessorUID")
        relationships.append(
            {
                **row,
                "predecessor_id": object_to_code.get(pred_object, pred_object),
                "successor_id": object_to_code.get(succ_object, succ_object),
                "relationship_type": _ci(row, "pred_type", "Type", default="FS"),
                "lag": _ci(row, "lag_hr_cnt", "Lag", default="0"),
                "p6_predecessor_object_id": pred_object,
                "p6_successor_object_id": succ_object,
                "_xer_table": "TASKPRED" if "pred_task_id" in row else "Relationship",
                "_source_row": row.get("_source_row", ""),
            }
        )
    return tuple(activities), tuple(relationships)
