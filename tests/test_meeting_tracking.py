from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.api import app
from meeting_tracking.models import (
    ActionStatus,
    MeetingItemType,
    MeetingType,
    MinutesStatus,
    RecordType,
    ReviewStatus,
)
from meeting_tracking.repository import JsonMeetingRepository
from meeting_tracking.service import MeetingTrackingService
from storage import JsonDocumentRepository


NOTES_14 = """Weekly OAC Meeting 014
Meeting Title: Weekly OAC Meeting
Meeting Number: 014
Date: August 7, 2026
Location: Project Conference Room
Chair: Project Manager
Recorder: Project Engineer
Attendees:
- Alice Architect | Architect | Design Studio
- Gary Builder | Project Manager | General Contractor

1. Electrical Procurement
Electrical subcontractor will provide updated switchgear lead time by Friday.
Architect will issue revised generator-pad detail by August 12, 2026.
Owner has not decided whether to relocate the UPS room.
Procurement release depends on switchgear submittal approval.
RFI-012 remains unanswered.
Submittal 26 24 13-001 is revise and resubmit.
The project team discussed a potential four-week schedule impact, but no schedule impact was confirmed.
Electrical PM will coordinate with commissioning on testing requirements.
Previous action A-008 remains open.
Next meeting is August 14, 2026.
"""


def service(tmp_path):
    return MeetingTrackingService(
        JsonDocumentRepository(tmp_path / "docs"), JsonMeetingRepository(tmp_path / "meetings")
    )


def test_ingest_extract_review_action_decision_minutes_dashboard_and_qa(tmp_path):
    svc = service(tmp_path)
    series = svc.create_series("p", "Weekly OAC", MeetingType.OWNER_ARCHITECT_CONTRACTOR)
    meeting = svc.create_meeting(
        "p",
        "Weekly OAC Meeting",
        date(2026, 8, 7),
        meeting_type=MeetingType.OWNER_ARCHITECT_CONTRACTOR,
        meeting_number="014",
        series_id=series.id,
    )
    source = tmp_path / "meeting-014.md"
    source.write_text(NOTES_14, encoding="utf-8")
    record = svc.ingest_record("p", meeting.id, source, RecordType.RAW_NOTES)
    analysis = svc.analyze("p", record.id)
    assert analysis.candidates and all(item.human_review_required for item in analysis.candidates)
    assert {item.field_name for item in analysis.metadata_candidates} >= {
        "meeting_date",
        "location",
        "chair",
        "recorder",
    }
    assert len(analysis.attendees) == 2 and len(analysis.organizations) == 2
    lead = next(item for item in analysis.candidates if "lead time" in item.description)
    reviewed, action = svc.review_candidate(
        "p", lead.id, ReviewStatus.CONFIRMED, "pm", owner_name="Electrical Subcontractor"
    )
    assert action and action.owner_name == "Electrical Subcontractor"
    action = svc.transition_action("p", action.id, ActionStatus.IN_PROGRESS, "pm")
    action = svc.transition_action(
        "p", action.id, ActionStatus.COMPLETED, "pm", resolution="Lead time received"
    )
    assert action.status == ActionStatus.COMPLETED
    with pytest.raises(ValueError):
        svc.transition_action("p", action.id, ActionStatus.IN_PROGRESS, "pm")
    decision_candidate = next(
        item
        for item in analysis.candidates
        if item.item_type == MeetingItemType.OWNER_DECISION_REQUEST
    )
    _, decision = svc.review_candidate("p", decision_candidate.id, ReviewStatus.CONFIRMED, "pm")
    assert decision is not None and decision.status.value == "pending_confirmation"
    minutes = svc.draft_minutes("p", meeting.id, "pm")
    assert "DRAFT" in minutes.markdown and "Lead time received" not in minutes.markdown
    minutes = svc.transition_minutes("p", minutes.id, MinutesStatus.PENDING_REVIEW, "pm")
    minutes = svc.transition_minutes("p", minutes.id, MinutesStatus.APPROVED, "pm")
    minutes = svc.transition_minutes("p", minutes.id, MinutesStatus.ISSUED, "pm")
    assert minutes.status == MinutesStatus.ISSUED
    assert svc.dashboard("p").total_open == 0
    assert not svc.search("other", "switchgear")
    assert svc.repository.list("audit", "p") and svc.repository.list("outbox", "p")
    assert svc.repository.list("commitments", "p")


def test_split_merge_dependency_and_proposal_guardrails(tmp_path):
    svc = service(tmp_path)
    meeting = svc.create_meeting("p", "Coordination", date(2026, 8, 7))
    source = tmp_path / "coordination.md"
    source.write_text(
        "Procurement release depends on switchgear submittal approval.\n"
        "Architect will issue detail and GC will review access.",
        encoding="utf-8",
    )
    record = svc.ingest_record("p", meeting.id, source, RecordType.RAW_NOTES)
    analysis = svc.analyze("p", record.id)
    dependency = next(
        item for item in analysis.candidates if item.item_type == MeetingItemType.DEPENDENCY
    )
    _, dependency_record = svc.review_candidate("p", dependency.id, ReviewStatus.CONFIRMED, "pm")
    assert dependency_record is not None and dependency_record.human_confirmed
    action = next(
        item for item in analysis.candidates if item.item_type == MeetingItemType.ACTION_ITEM
    )
    children = svc.split_candidate(
        "p", action.id, ("Architect will issue detail.", "GC will review access."), "pm"
    )
    merged = svc.merge_candidates(
        "p", tuple(item.id for item in children), "Coordinate detail and access review.", "pm"
    )
    assert len(children) == 2 and merged.review_status == ReviewStatus.UNREVIEWED
    assert not svc.repository.list("actions", "p")


def test_immutable_revisions_comparison_carry_forward_and_guardrails(tmp_path):
    svc = service(tmp_path)
    old_meeting = svc.create_meeting("p", "OAC", date(2026, 8, 7), meeting_number="014")
    old_file = tmp_path / "old.md"
    old_file.write_text(NOTES_14, encoding="utf-8")
    old = svc.ingest_record("p", old_meeting.id, old_file, RecordType.RAW_NOTES)
    analysis = svc.analyze("p", old.id)
    candidate = next(x for x in analysis.candidates if "generator-pad" in x.description)
    _, action = svc.review_candidate(
        "p", candidate.id, ReviewStatus.CONFIRMED, "pm", owner_name="Architect"
    )
    new_file = tmp_path / "new.md"
    new_file.write_text(
        NOTES_14.replace("August 12, 2026", "August 16, 2026")
        + "\nOwner approved keeping the UPS room in its current location.",
        encoding="utf-8",
    )
    new = svc.ingest_record(
        "p", old_meeting.id, new_file, RecordType.CORRECTED_MINUTES, predecessor_revision_id=old.id
    )
    comparison = svc.compare_records("p", old.id, new.id)
    assert comparison.changes and all(
        change.old_citation or change.new_citation for change in comparison.changes
    )
    next_meeting = svc.create_meeting(
        "p", "OAC", date(2026, 8, 14), meeting_number="015", previous_meeting_id=old_meeting.id
    )
    carried = svc.carry_forward(
        "p", old_meeting.id, next_meeting.id, "Architect has not issued generator-pad detail"
    )
    assert carried[0].carry_forward_count == 1 and carried[0].status != ActionStatus.COMPLETED
    assert action is not None


def test_openapi_contains_meeting_action_decision_and_minutes_routes():
    paths = TestClient(app).get("/openapi.json").json()["paths"]
    for path in (
        "/projects/{project_id}/meetings",
        "/projects/{project_id}/actions",
        "/projects/{project_id}/decisions",
        "/projects/{project_id}/action-dashboard",
        "/projects/{project_id}/meeting-records/compare",
    ):
        assert path in paths
