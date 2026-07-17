"""Small deterministic parsers for meeting metadata, agenda, dates, and item proposals."""

import re
from datetime import date, timedelta
from hashlib import sha256

from document_processing.models import IngestedDocument

from .models import (
    DueDateCandidate,
    ExtractedMeetingItem,
    MeetingAgendaItem,
    MeetingEvidenceReference,
    MeetingAttendee,
    MeetingMetadataCandidate,
    MeetingOrganization,
    MeetingItemType,
)


def parse_metadata(document: IngestedDocument):
    candidates = []
    attendees = []
    organizations: dict[str, MeetingOrganization] = {}
    attendee_section = False
    fields = {
        "meeting title": "title",
        "meeting number": "meeting_number",
        "meeting no": "meeting_number",
        "date": "meeting_date",
        "time": "meeting_time",
        "location": "location",
        "chair": "chair",
        "recorder": "recorder",
        "meeting owner": "meeting_owner",
        "next meeting": "next_meeting_date",
    }
    for page in document.pages:
        for raw in page.content.splitlines():
            line = raw.strip()
            heading = re.match(r"^([A-Za-z ]{2,30}):\s*(.+)$", line)
            if heading and heading.group(1).casefold() in fields:
                candidates.append(
                    MeetingMetadataCandidate(
                        field_name=fields[heading.group(1).casefold()],
                        candidate_value=heading.group(2).strip(),
                        citation=evidence(document, page.page_number, line),
                        evidence_strength=0.95,
                    )
                )
            if re.fullmatch(r"(?:attendees|attendance|present):?", line, re.I):
                attendee_section = True
                continue
            if attendee_section:
                if not line or re.match(r"^(?:agenda|discussion|[0-9]+\.)", line, re.I):
                    attendee_section = False
                    continue
                parts = [
                    part.strip()
                    for part in re.split(r"\s*[|–-]\s*", line.lstrip("-* "))
                    if part.strip()
                ]
                if parts and len(parts[0].split()) >= 2:
                    organization = parts[2] if len(parts) > 2 else None
                    citation = evidence(document, page.page_number, line)
                    attendees.append(
                        MeetingAttendee(
                            name=parts[0],
                            role=parts[1] if len(parts) > 1 else None,
                            organization=organization,
                            attendance_status="present",
                            citation=citation,
                        )
                    )
                    if organization:
                        organizations[organization.casefold()] = MeetingOrganization(
                            name=organization, citation=citation
                        )
    return tuple(candidates), tuple(attendees), tuple(organizations.values())


def evidence(
    document: IngestedDocument, page_number: int, excerpt: str
) -> MeetingEvidenceReference:
    chunk = next((item for item in document.chunks if item.page_number == page_number), None)
    return MeetingEvidenceReference(
        document_id=document.document.document_id,
        document_name=document.document.original_filename,
        page_number=page_number,
        chunk_id=chunk.id if chunk else f"page-{page_number}",
        source_location=f"page {page_number}",
        exact_excerpt=excerpt.strip(),
    )


def parse_due_date(text: str, meeting_date: date | None) -> DueDateCandidate | None:
    match = re.search(
        r"\b(?:due|by)\s+(?P<value>(?:[A-Z][a-z]+\s+\d{1,2}(?:,\s*\d{4})?)|(?:\d{1,2}/\d{1,2}/\d{2,4})|Friday|Monday|Tuesday|Wednesday|Thursday|next meeting|within two weeks|end of month)\b",
        text,
        re.I,
    )
    if not match:
        return None
    original = match.group("value")
    parsed = None
    method = "relative_unresolved"
    ambiguous = False
    for fmt in ("%B %d, %Y", "%B %d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            parsed = __import__("datetime").datetime.strptime(original, fmt).date()
            if fmt == "%B %d" and meeting_date:
                parsed = parsed.replace(year=meeting_date.year)
            method = "explicit_calendar_date"
            break
        except ValueError:
            pass
    lowered = original.casefold()
    if (
        parsed is None
        and meeting_date
        and lowered in {"friday", "monday", "tuesday", "wednesday", "thursday"}
    ):
        target = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4}[lowered]
        delta = (target - meeting_date.weekday()) % 7 or 7
        parsed = meeting_date + timedelta(days=delta)
        method = "weekday_after_meeting"
    elif parsed is None and meeting_date and lowered == "within two weeks":
        parsed = meeting_date + timedelta(days=14)
        method = "relative_to_meeting"
    elif parsed is None:
        ambiguous = True
    return DueDateCandidate(
        original_text=original,
        parsed_date=parsed,
        interpretation_method=method,
        reference_date=meeting_date,
        ambiguous=ambiguous,
    )


def parse_agenda(document: IngestedDocument) -> tuple[MeetingAgendaItem, ...]:
    result = []
    for page in document.pages:
        for line in page.content.splitlines():
            match = re.match(r"\s*(\d+(?:\.\d+)*)[.)]?\s+(.+)", line)
            if match and len(match.group(2).split()) <= 14:
                result.append(
                    MeetingAgendaItem(
                        id=f"agenda_{sha256((document.document.document_id + line).encode()).hexdigest()[:20]}",
                        sequence=len(result) + 1,
                        heading=match.group(2).strip(),
                        citation=evidence(document, page.page_number, line),
                    )
                )
    return tuple(result)


def parse_candidates(
    document: IngestedDocument, meeting_id: str, revision_id: str, meeting_date: date | None
) -> tuple[ExtractedMeetingItem, ...]:
    result = []
    action_words = re.compile(
        r"\b(will|shall|to provide|to submit|to review|to confirm|to coordinate|to issue|to revise|to complete|action|follow up|outstanding|open item)\b",
        re.I,
    )
    decision_words = re.compile(
        r"\b(approved|agreed|confirmed|directed|selected|accepted|rejected|proceed with|owner decided)\b",
        re.I,
    )
    dependency_words = re.compile(
        r"\b(depends on|dependent on|cannot proceed until|blocked pending|requires)\b", re.I
    )
    for page in document.pages:
        for raw in page.content.splitlines():
            line = raw.strip(" -*\t")
            if len(line) < 8:
                continue
            lowered = line.casefold()
            item_type = None
            reason = ""
            if dependency_words.search(line):
                item_type, reason = MeetingItemType.DEPENDENCY, "explicit dependency phrase"
            elif "?" in line or re.search(
                r"\b(remains unanswered|information needed|has not decided)\b", line, re.I
            ):
                item_type, reason = (
                    MeetingItemType.QUESTION,
                    "explicit unresolved-question language",
                )
                if "owner" in lowered and "decid" in lowered:
                    item_type = MeetingItemType.OWNER_DECISION_REQUEST
            elif re.search(r"\b(blocked|cannot proceed)\b", line, re.I):
                item_type, reason = MeetingItemType.BLOCKER, "explicit blocker language"
            elif re.search(r"\b(potential|possible|risk|may impact)\b", line, re.I):
                item_type, reason = MeetingItemType.RISK, "explicit uncertainty or risk language"
            elif decision_words.search(line):
                item_type, reason = MeetingItemType.DECISION, "explicit decision verb"
            elif action_words.search(line):
                item_type, reason = (
                    MeetingItemType.ACTION_ITEM,
                    "explicit action or commitment verb",
                )
            elif re.search(r"\bRFI[- ]?\d+\b", line, re.I):
                item_type, reason = MeetingItemType.ISSUE, "explicit RFI status reference"
            elif re.search(r"\bSubmittal\b", line, re.I):
                item_type, reason = MeetingItemType.SUBMITTAL_ACTION, "explicit submittal reference"
            if item_type is None:
                continue
            owner = None
            owner_match = re.match(
                r"(.{2,60}?)\s+(?:will|shall|to provide|to issue|to coordinate)\b", line, re.I
            )
            if owner_match:
                owner = owner_match.group(1).strip(" :-")
                if owner.casefold() in {"team", "project team", "all"}:
                    owner = None
            identifiers = tuple(
                match.group(0)
                for match in re.finditer(
                    r"\b(?:RFI[- ]?\d+|Submittal\s+[\w -]+-\d+|A-\d+)\b", line, re.I
                )
            )
            due = parse_due_date(line, meeting_date)
            ambiguities = []
            if item_type == MeetingItemType.ACTION_ITEM and owner is None:
                ambiguities.append("owner not explicit")
            if due and due.ambiguous:
                ambiguities.append("due date requires confirmation")
            candidate_id = (
                f"mcand_{sha256((revision_id + line + item_type.value).encode()).hexdigest()[:20]}"
            )
            result.append(
                ExtractedMeetingItem(
                    id=candidate_id,
                    project_id=document.document.project_id,
                    meeting_id=meeting_id,
                    record_revision_id=revision_id,
                    item_type=item_type,
                    title=line[:120],
                    description=line,
                    owner_candidate=owner,
                    due_date_candidate=due,
                    citations=(evidence(document, page.page_number, line),),
                    related_identifiers=identifiers,
                    extraction_strength=0.9 if reason.startswith("explicit") else 0.7,
                    extraction_reason=reason,
                    ambiguities=tuple(ambiguities),
                )
            )
    return tuple(result)
