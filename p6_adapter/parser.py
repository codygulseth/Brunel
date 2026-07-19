"""Safe, deterministic XER and Primavera P6 XML parsing.

The parser preserves vendor fields in raw dictionaries. Normalized schedule admission is
performed by the canonical schedule service, not here.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import xml.etree.ElementTree as ET


MAX_SOURCE_BYTES = 50 * 1024 * 1024


@dataclass(frozen=True)
class ParsedP6Project:
    external_project_id: str
    short_name: str | None
    name: str
    metadata: dict[str, str]
    activities: tuple[dict[str, str], ...]
    wbs: tuple[dict[str, str], ...]
    calendars: tuple[dict[str, str], ...]
    relationships: tuple[dict[str, str], ...]
    activity_codes: tuple[dict[str, str], ...] = ()
    udfs: tuple[dict[str, str], ...] = ()
    resources: tuple[dict[str, str], ...] = ()
    assignments: tuple[dict[str, str], ...] = ()
    notes: tuple[dict[str, str], ...] = ()
    unsupported: dict[str, tuple[dict[str, str], ...]] | None = None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ParsedP6Source:
    source_format: str
    content_hash: str
    parser_version: str
    projects: tuple[ParsedP6Project, ...]
    warnings: tuple[str, ...] = ()


def _read(path: Path) -> bytes:
    source = path.expanduser().resolve()
    if not source.is_file():
        raise ValueError("P6 source file not found")
    size = source.stat().st_size
    if size > MAX_SOURCE_BYTES:
        raise ValueError("P6 source exceeds the configured safe parser limit")
    return source.read_bytes()


def _decode_xer(content: bytes, encoding: str | None) -> tuple[str, str]:
    candidates = tuple(filter(None, (encoding, "utf-8-sig", "cp1252")))
    for candidate in candidates:
        try:
            return content.decode(candidate), candidate
        except (UnicodeDecodeError, LookupError):
            continue
    raise ValueError("Unable to decode XER source using supported encodings")


class P6XERParser:
    name = "primavera-p6-xer"
    version = "1.0.0"

    def parse(self, path: Path, *, encoding: str | None = None) -> ParsedP6Source:
        content = _read(path)
        text, used_encoding = _decode_xer(content, encoding)
        tables: dict[str, list[dict[str, str]]] = {}
        fields: dict[str, tuple[str, ...]] = {}
        table: str | None = None
        warnings: list[str] = []
        for line_number, line in enumerate(text.splitlines(), 1):
            if not line:
                continue
            parts = line.split("\t")
            marker = parts[0]
            if marker == "%T" and len(parts) > 1:
                table = parts[1].upper()
                tables.setdefault(table, [])
            elif marker == "%F" and table:
                fields[table] = tuple(parts[1:])
            elif marker == "%R" and table:
                declared = fields.get(table, ())
                if not declared:
                    warnings.append(f"Line {line_number}: record without field declaration")
                    continue
                values = parts[1:]
                if len(values) != len(declared):
                    warnings.append(
                        f"Line {line_number}: {table} row has {len(values)} values for {len(declared)} fields"
                    )
                row = dict(zip(declared, values, strict=False))
                row["_source_row"] = str(line_number)
                tables[table].append(row)
            elif marker == "%E":
                break
            elif marker.startswith("%"):
                warnings.append(f"Line {line_number}: unsupported XER marker {marker}")
        if not tables.get("PROJECT"):
            raise ValueError("XER source contains no PROJECT records")
        known = {
            "PROJECT",
            "PROJWBS",
            "TASK",
            "TASKPRED",
            "CALENDAR",
            "ACTVCODETYPE",
            "ACTVTYPE",
            "ACTVCODE",
            "TASKACTV",
            "UDFTYPE",
            "UDFVALUE",
            "RSRC",
            "TASKRSRC",
            "COSTTYPE",
            "MEMOTYPE",
            "TASKMEMO",
            "PROJISSU",
            "PROJTHRS",
            "OBS",
            "CURRTYPE",
            "PROJECTBASELINE",
            "PROJPCAT",
            "PCATVAL",
        }
        unknown = {k: tuple(v) for k, v in tables.items() if k not in known}
        warnings.extend(f"Unsupported XER table preserved: {name}" for name in unknown)
        projects = []
        for project in tables["PROJECT"]:
            project_id = project.get("proj_id") or project.get("project_id")
            if not project_id:
                warnings.append("PROJECT record without project object ID was skipped")
                continue

            def scoped(name: str) -> tuple[dict[str, str], ...]:
                rows = tables.get(name, [])
                return tuple(
                    r for r in rows if not r.get("proj_id") or r.get("proj_id") == project_id
                )

            projects.append(
                ParsedP6Project(
                    external_project_id=project_id,
                    short_name=project.get("proj_short_name") or project.get("proj_code"),
                    name=project.get("proj_name") or project.get("proj_short_name") or project_id,
                    metadata={**project, "source_encoding": used_encoding},
                    activities=scoped("TASK"),
                    wbs=scoped("PROJWBS"),
                    calendars=scoped("CALENDAR"),
                    relationships=scoped("TASKPRED"),
                    activity_codes=scoped("TASKACTV") + scoped("ACTVCODE") + scoped("ACTVTYPE"),
                    udfs=scoped("UDFTYPE") + scoped("UDFVALUE"),
                    resources=scoped("RSRC"),
                    assignments=scoped("TASKRSRC"),
                    notes=scoped("TASKMEMO") + scoped("MEMOTYPE"),
                    unsupported=unknown,
                    warnings=tuple(warnings),
                )
            )
        return ParsedP6Source(
            "xer", sha256(content).hexdigest(), self.version, tuple(projects), tuple(warnings)
        )


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _children(element: ET.Element) -> dict[str, str]:
    return {_local(child.tag): (child.text or "").strip() for child in element}


class P6XMLParser:
    name = "primavera-p6-xml"
    version = "1.0.0"

    def parse(self, path: Path) -> ParsedP6Source:
        content = _read(path)
        upper = content[:65536].upper()
        if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
            raise ValueError("Unsafe XML declarations are not allowed")
        try:
            root = ET.fromstring(content)
        except ET.ParseError as exc:
            raise ValueError(f"Malformed P6 XML: {exc}") from exc
        project_elements = [e for e in root.iter() if _local(e.tag).casefold() == "project"]
        if not project_elements and _local(root.tag).casefold() == "project":
            project_elements = [root]
        projects = []
        for position, project in enumerate(project_elements, 1):
            metadata = _children(project)
            project_id = (
                metadata.get("ObjectId")
                or metadata.get("ProjectObjectId")
                or metadata.get("Id")
                or metadata.get("ProjectId")
                or f"xml-project-{position}"
            )
            groups: dict[str, list[dict[str, str]]] = {
                "activities": [],
                "wbs": [],
                "calendars": [],
                "relationships": [],
                "activity_codes": [],
                "udfs": [],
                "resources": [],
                "assignments": [],
                "notes": [],
            }
            aliases = {
                "activity": "activities",
                "task": "activities",
                "wbs": "wbs",
                "wbselement": "wbs",
                "calendar": "calendars",
                "relationship": "relationships",
                "predecessorlink": "relationships",
                "activitycode": "activity_codes",
                "activitycodeassignment": "activity_codes",
                "udfvalue": "udfs",
                "userdefinedfield": "udfs",
                "resource": "resources",
                "resourceassignment": "assignments",
                "activitynote": "notes",
                "notebooktopic": "notes",
            }
            for element in project.iter():
                key = aliases.get(_local(element.tag).casefold())
                if key:
                    row = _children(element)
                    row["_xml_path"] = _local(element.tag)
                    groups[key].append(row)
            projects.append(
                ParsedP6Project(
                    external_project_id=project_id,
                    short_name=metadata.get("Id") or metadata.get("ProjectId"),
                    name=metadata.get("Name") or metadata.get("ProjectName") or project_id,
                    metadata=metadata,
                    activities=tuple(groups["activities"]),
                    wbs=tuple(groups["wbs"]),
                    calendars=tuple(groups["calendars"]),
                    relationships=tuple(groups["relationships"]),
                    activity_codes=tuple(groups["activity_codes"]),
                    udfs=tuple(groups["udfs"]),
                    resources=tuple(groups["resources"]),
                    assignments=tuple(groups["assignments"]),
                    notes=tuple(groups["notes"]),
                )
            )
        if not projects:
            raise ValueError("P6 XML source contains no Project element")
        return ParsedP6Source("p6_xml", sha256(content).hexdigest(), self.version, tuple(projects))


def parse_p6(path: Path, *, encoding: str | None = None) -> ParsedP6Source:
    suffix = path.suffix.casefold()
    if suffix == ".xer":
        return P6XERParser().parse(path, encoding=encoding)
    if suffix == ".xml":
        return P6XMLParser().parse(path)
    raise ValueError("P6 adapter supports only .xer and .xml sources")
