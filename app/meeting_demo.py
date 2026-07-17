"""Runnable fully synthetic OAC meeting scenario."""

from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from meeting_tracking.models import MeetingType, RecordType, ReviewStatus
from meeting_tracking.repository import JsonMeetingRepository
from meeting_tracking.service import MeetingTrackingService
from storage import JsonDocumentRepository

NOTES_014 = """Weekly OAC Meeting 014
1. Electrical Procurement
Electrical subcontractor will provide updated switchgear lead time by Friday.
Architect will issue revised generator-pad detail by August 12, 2026.
Owner has not decided whether to relocate the UPS room.
Procurement release depends on switchgear submittal approval.
RFI-012 remains unanswered.
Submittal 26 24 13-001 is revise and resubmit.
Potential four-week schedule impact was discussed, but no impact was confirmed.
Electrical PM will coordinate with commissioning on testing requirements.
Previous action A-008 remains open.
"""


def main() -> int:
    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        repository = JsonMeetingRepository(root / "meeting-data")
        service = MeetingTrackingService(JsonDocumentRepository(root / "documents"), repository)
        series = service.create_series(
            "demo-project", "Weekly OAC Meeting", MeetingType.OWNER_ARCHITECT_CONTRACTOR
        )
        meeting = service.create_meeting(
            "demo-project",
            "Weekly OAC Meeting",
            date(2026, 8, 7),
            meeting_type=MeetingType.OWNER_ARCHITECT_CONTRACTOR,
            meeting_number="014",
            series_id=series.id,
        )
        source = root / "meeting-014.md"
        source.write_text(NOTES_014, encoding="utf-8")
        record = service.ingest_record("demo-project", meeting.id, source, RecordType.RAW_NOTES)
        analysis = service.analyze("demo-project", record.id)
        confirmed = 0
        for candidate in analysis.candidates:
            if candidate.item_type.value == "action_item":
                service.review_candidate(
                    "demo-project",
                    candidate.id,
                    ReviewStatus.CONFIRMED,
                    "project-manager",
                    owner_name=candidate.owner_candidate,
                )
                confirmed += 1
        minutes = service.draft_minutes("demo-project", meeting.id, "project-manager")
        dashboard = service.dashboard("demo-project")
        print(f"Meeting 014: {len(analysis.candidates)} proposals, {confirmed} confirmed actions")
        print(f"Action register: {dashboard.total_open} open, {dashboard.unassigned} unassigned")
        print(f"Draft minutes: {minutes.id}; external distribution: disabled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
