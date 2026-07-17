"""Deterministic CSV, constrained XML, and XER schedule adapters."""

import csv
from dataclasses import dataclass
from pathlib import Path
import xml.etree.ElementTree as ET


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
    name = "xer-foundation"
    version = "1"

    def parse(self, path: Path, mapping=None) -> ParsedSchedule:
        tables = {}
        table = None
        fields = []
        unsupported = []
        for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            parts = line.split("\t")
            marker = parts[0]
            if marker == "%T":
                table = parts[1]
                tables.setdefault(table, [])
                fields = []
            elif marker == "%F":
                fields = parts[1:]
            elif marker == "%R" and table and fields:
                values = parts[1:]
                tables[table].append(dict(zip(fields, values, strict=False)))
        if "TASK" not in tables:
            raise ValueError("XER required TASK table is unavailable")
        activities = []
        for row in tables["TASK"]:
            item = dict(row)
            item.update(
                {
                    "activity_id": row.get("task_code", row.get("task_id", "")),
                    "activity_name": row.get("task_name", ""),
                    "wbs_id": row.get("wbs_id", ""),
                    "calendar_id": row.get("clndr_id", ""),
                    "status": row.get("status_code", ""),
                    "original_duration": row.get("target_drtn_hr_cnt", ""),
                    "remaining_duration": row.get("remain_drtn_hr_cnt", ""),
                    "planned_start": row.get("target_start_date", ""),
                    "planned_finish": row.get("target_end_date", ""),
                    "actual_start": row.get("act_start_date", ""),
                    "actual_finish": row.get("act_end_date", ""),
                    "total_float": row.get("total_float_hr_cnt", ""),
                    "_xer_table": "TASK",
                }
            )
            activities.append(item)
        rels = []
        for row in tables.get("TASKPRED", []):
            rels.append(
                {
                    **row,
                    "predecessor_id": row.get("pred_task_id", ""),
                    "successor_id": row.get("task_id", ""),
                    "relationship_type": row.get("pred_type", "FS"),
                    "lag": row.get("lag_hr_cnt", "0"),
                    "_xer_table": "TASKPRED",
                }
            )
        known = {
            "PROJECT",
            "PROJWBS",
            "TASK",
            "TASKPRED",
            "CALENDAR",
            "ACTVTYPE",
            "ACTVCODE",
            "TASKACTV",
            "UDFTYPE",
            "UDFVALUE",
        }
        unsupported.extend(
            f"Unsupported XER table preserved: {x}" for x in tables if x not in known
        )
        return ParsedSchedule(
            (tables.get("PROJECT") or [{}])[0],
            tuple(activities),
            tuple(rels),
            tuple(tables.get("CALENDAR", [])),
            tuple(tables.get("PROJWBS", [])),
            tuple(unsupported),
        )
