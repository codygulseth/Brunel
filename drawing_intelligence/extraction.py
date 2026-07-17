# ruff: noqa: F403, F405
"""Deterministic parsing of explicit drawing text; no graphical interpretation."""

import re
from hashlib import sha256
from uuid import uuid4
from .models import *  # noqa: F403, F405

SHEET = re.compile(
    r"\b(?:SHEET(?:\s+NO\.?)?\s*[:#-]?\s*)?((?:G|C|L|A|I|S|M|P|FP|E|EP|EL|T|FA|IC)\d+(?:\.\d+)?)\b",
    re.I,
)
REFERENCE = re.compile(
    r"\b(?:(SEE|REFER TO|CONTINUED ON|MATCHLINE\s*-?\s*SEE|FOR SCHEDULE SEE|ONE-LINE DIAGRAM|PANEL SCHEDULE|SECTION|DETAIL|ELEVATION)\s+)?(?:(\d+)\/)?((?:G|C|L|A|I|S|M|P|FP|E|EP|EL|T|FA|IC)\d+(?:\.\d+)?)\b",
    re.I,
)
DISCIPLINES = {
    "G": DrawingDiscipline.GENERAL,
    "C": DrawingDiscipline.CIVIL,
    "L": DrawingDiscipline.LANDSCAPE,
    "A": DrawingDiscipline.ARCHITECTURAL,
    "I": DrawingDiscipline.INTERIORS,
    "S": DrawingDiscipline.STRUCTURAL,
    "M": DrawingDiscipline.MECHANICAL,
    "P": DrawingDiscipline.PLUMBING,
    "FP": DrawingDiscipline.FIRE_PROTECTION,
    "E": DrawingDiscipline.ELECTRICAL,
    "EP": DrawingDiscipline.ELECTRICAL_POWER,
    "EL": DrawingDiscipline.ELECTRICAL_LIGHTING,
    "T": DrawingDiscipline.TELECOM,
    "FA": DrawingDiscipline.LIFE_SAFETY,
    "IC": DrawingDiscipline.CONTROLS,
}


def classify(number: str | None) -> tuple[DrawingDiscipline, str | None, float]:
    if not number:
        return DrawingDiscipline.UNKNOWN, None, 0
    prefix = re.match(r"[A-Z]+", number.upper()).group(0)
    return (
        DISCIPLINES.get(prefix, DrawingDiscipline.UNKNOWN),
        prefix,
        0.9 if prefix in DISCIPLINES else 0.2,
    )


def full_region(
    project_id: str,
    document_id: str,
    revision_id: str,
    page: int,
    width: int,
    height: int,
    render_ref: str | None,
    text: str,
    label: str = "page text",
) -> VisualRegion:
    return VisualRegion(
        id=f"region_{uuid4().hex}",
        project_id=project_id,
        source_document_id=document_id,
        drawing_set_revision_id=revision_id,
        page_number=page,
        render_width=width,
        render_height=height,
        pixel_box=PixelBox(x_min=0, y_min=0, x_max=width, y_max=height),
        normalized_box=NormalizedBox(x_min=0, y_min=0, x_max=1, y_max=1),
        region_type="text_span",
        region_label=label,
        render_reference=render_ref,
        text_span=text[:1000] or None,
        extraction_method=ExtractionMethod.NATIVE_PDF_TEXT,
        evidence_strength=0.75,
    )


def citation(
    region: VisualRegion,
    sheet_id: str | None,
    number: str | None,
    title: str | None,
    text: str | None = None,
) -> VisualRegionCitation:
    return VisualRegionCitation(
        drawing_set_revision_id=region.drawing_set_revision_id,
        sheet_revision_id=sheet_id,
        sheet_number=number,
        sheet_title=title,
        page_number=region.page_number,
        region=region,
        extracted_text=text,
        extraction_method=region.extraction_method,
        evidence_strength=region.evidence_strength,
    )


def sheet_metadata(text: str) -> tuple[str | None, str | None, str | None]:
    explicit = re.search(
        r"(?:^|\n)\s*SHEET(?:\s+NO\.?)?\s*[:#-]?\s*((?:G|C|L|A|I|S|M|P|FP|E|EP|EL|T|FA|IC)\d+(?:\.\d+)?)",
        text,
        re.I,
    )
    matches = SHEET.findall(text)
    number = explicit.group(1).upper() if explicit else (matches[0].upper() if matches else None)
    title = None
    revision = None
    for line in (x.strip() for x in text.splitlines() if x.strip()):
        m = re.match(r"(?:SHEET TITLE|TITLE)\s*[:\-]\s*(.+)", line, re.I)
        if m:
            title = m.group(1).strip()
        m = re.match(r"(?:REVISION|REV)\s*[:#\-]?\s*(\S+)", line, re.I)
        if m:
            revision = m.group(1)
    return number, title, revision


def extract_references(
    project_id: str, revision_id: str, sheet: DrawingSheet, text: str, region: VisualRegion
) -> tuple[DrawingReference, ...]:
    values = []
    for m in REFERENCE.finditer(text):
        target = m.group(3).upper()
        if target == sheet.sheet_number and not m.group(1) and not m.group(2):
            continue
        lead = (m.group(1) or "").upper()
        view = m.group(2)
        kind = DrawingReferenceType.SHEET
        for token, enum in (
            ("DETAIL", DrawingReferenceType.DETAIL),
            ("SECTION", DrawingReferenceType.SECTION),
            ("ELEVATION", DrawingReferenceType.ELEVATION),
            ("SCHEDULE", DrawingReferenceType.SCHEDULE),
            ("MATCHLINE", DrawingReferenceType.MATCHLINE),
            ("CONTINUED", DrawingReferenceType.CONTINUATION),
            ("DIAGRAM", DrawingReferenceType.DIAGRAM),
        ):
            if token in lead:
                kind = enum
        exact = m.group(0)
        values.append(
            DrawingReference(
                id=f"ref_{sha256((sheet.sheet_revision_id + str(m.start()) + exact).encode()).hexdigest()[:20]}",
                project_id=project_id,
                drawing_set_revision_id=revision_id,
                source_sheet_revision_id=sheet.sheet_revision_id,
                reference_type=kind,
                reference_label=lead or "explicit sheet reference",
                exact_text=exact,
                target_sheet_number=target,
                target_view_number=view,
                citation=citation(
                    region, sheet.sheet_revision_id, sheet.sheet_number, sheet.sheet_title, exact
                ),
                evidence_strength=0.85,
                human_review_required=not bool(lead or view),
            )
        )
    return tuple(values)


def parse_index(text: str, region: VisualRegion) -> tuple[DrawingIndexEntry, ...]:
    if "DRAWING INDEX" not in text.upper() and "SHEET LIST" not in text.upper():
        return ()
    entries = []
    for line in text.splitlines():
        m = re.match(
            r"\s*((?:G|C|L|A|I|S|M|P|FP|E|EP|EL|T|FA|IC)\d+(?:\.\d+)?)\s*[-–:]\s*(.+?)\s*$",
            line,
            re.I,
        )
        if m:
            number = m.group(1).upper()
            entries.append(
                DrawingIndexEntry(
                    id=f"index_{uuid4().hex}",
                    sheet_number=number,
                    sheet_title=m.group(2).strip(),
                    discipline_group=classify(number)[0].value,
                    order=len(entries) + 1,
                    citation=citation(region, None, number, m.group(2).strip(), line.strip()),
                )
            )
    return tuple(entries)


def extract_keynotes(
    sheet: DrawingSheet, text: str, region: VisualRegion
) -> tuple[DrawingKeynote, ...]:
    """Extract explicitly labelled keynote legends and occurrences only."""
    legends: dict[str, KeynoteLegendEntry] = {}
    occurrences: dict[str, list[KeynoteOccurrence]] = {}
    in_legend = False
    for line_number, raw in enumerate(text.splitlines()):
        line = raw.strip()
        if re.fullmatch(r"(?:GENERAL\s+)?KEYNOTES?:?", line, re.I):
            in_legend = True
            continue
        legend = re.match(r"(?:KEYNOTE\s+)?([A-Z]?\d{1,3})\s*[-–:]\s*(.+)", line, re.I)
        if in_legend and legend:
            identifier = legend.group(1).upper()
            legends[identifier] = KeynoteLegendEntry(
                id=f"keylegend_{sha256((sheet.sheet_revision_id + identifier).encode()).hexdigest()[:20]}",
                identifier=identifier,
                text=legend.group(2).strip(),
                citation=citation(
                    region, sheet.sheet_revision_id, sheet.sheet_number, sheet.sheet_title, line
                ),
            )
            continue
        occurrence = re.search(r"\bKEYNOTE\s+([A-Z]?\d{1,3})\b", line, re.I)
        if occurrence:
            identifier = occurrence.group(1).upper()
            occurrences.setdefault(identifier, []).append(
                KeynoteOccurrence(
                    id=f"keyocc_{sha256((sheet.sheet_revision_id + str(line_number) + identifier).encode()).hexdigest()[:20]}",
                    identifier=identifier,
                    sheet_revision_id=sheet.sheet_revision_id,
                    citation=citation(
                        region, sheet.sheet_revision_id, sheet.sheet_number, sheet.sheet_title, line
                    ),
                    resolved=False,
                )
            )
    return tuple(
        DrawingKeynote(
            identifier=identifier,
            legend=legends.get(identifier),
            occurrences=tuple(
                item.model_copy(update={"resolved": identifier in legends})
                for item in occurrences.get(identifier, [])
            ),
        )
        for identifier in sorted(set(legends) | set(occurrences))
    )
