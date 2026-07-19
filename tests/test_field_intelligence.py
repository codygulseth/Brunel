from datetime import date
from fastapi.testclient import TestClient
import pytest
from app.api import app
from field_intelligence.models import ObservationType, ReportStatus
from field_intelligence.qa import FieldQuestionService
from field_intelligence.repository import JsonFieldRepository
from field_intelligence.service import FieldIntelligenceService


@pytest.fixture
def workflow(tmp_path):
    return FieldIntelligenceService(JsonFieldRepository(tmp_path / "field"))


TEXT = """Weather: rain and muddy ground reported.
Manpower: 12 electricians onsite in electrical room.
Work: Switchgear installation A300 ongoing.
Delivery: controls panels partial delivery received.
Inspection failed for feeder megger test.
Safety hazard: blocked access at electrical room.
"""


def test_ingestion_review_issue_dashboard_and_citations(workflow, tmp_path):
    source = tmp_path / "daily.md"
    source.write_text(TEXT, encoding="utf-8")
    report, revision, items = workflow.ingest("p", date(2027, 1, 4), source, prepared_by="super")
    assert len(items) == 6 and items[0].citation.source_locator == "line 1"
    manpower = next(x for x in items if x.observation_type == ObservationType.MANPOWER)
    assert manpower.headcount == 12
    for item in items:
        workflow.review_observation("p", item.id, "confirm", "super")
    workflow.transition("p", report.id, ReportStatus.UNDER_REVIEW, "super")
    workflow.transition("p", report.id, ReportStatus.APPROVED, "pm")
    issued = workflow.transition("p", report.id, ReportStatus.ISSUED_INTERNAL, "pm")
    assert (
        issued.status == ReportStatus.ISSUED_INTERNAL
        and workflow.dashboard("p").reports_issued == 1
    )
    assert "contractual" in workflow.draft("p", report.id)
    assert workflow.search("other", "switchgear") == ()


def test_schedule_proposals_do_not_update_schedule(workflow, tmp_path):
    from schedule_intelligence.models import (
        ActivityStatus,
        ActivityType,
        ScheduleActivityRevision,
        ScheduleFileFormat,
        ScheduleSourceReference,
    )

    report, revision = workflow.create_report("p", date(2027, 1, 4), text="Work: A300 completed.")
    obs = workflow.analyze("p", revision.id)[0]
    workflow.review_observation("p", obs.id, "confirm", "super")
    citation = ScheduleSourceReference(
        schedule_revision_id="s1",
        source_document_id="d",
        source_filename="s.csv",
        file_format=ScheduleFileFormat.CSV,
        source_table="CSV",
        source_row=2,
        parser_name="test",
        parser_version="1",
        imported_at=revision.created_at,
    )
    activity = ScheduleActivityRevision(
        id="ar1",
        activity_identity_id="a1",
        project_id="p",
        schedule_id="s",
        schedule_revision_id="s1",
        source_activity_id="A300",
        name="Install",
        activity_type=ActivityType.TASK_DEPENDENT,
        status=ActivityStatus.NOT_STARTED,
        source_fields={},
        citation=citation,
    )
    link = workflow.suggest_schedule_links("p", report.id, (activity,))[0]
    workflow.review_schedule_link("p", link.id, "accept", "super")
    proposal = workflow.create_progress_proposals("p", report.id)[0]
    reviewed = workflow.review_progress("p", proposal.id, "accept", "pm")
    assert reviewed.schedule_updated is False
    result = workflow.planned_vs_reported("p", report.id, (activity,))
    assert result["planned_reported"] == ("ar1",)


def test_revision_comparison_weekly_qa_and_api(workflow, monkeypatch, tmp_path):
    report, old = workflow.create_report("p", date(2027, 1, 4), text="Delivery: panels partial.")
    workflow.analyze("p", old.id)
    _, new = workflow.create_report(
        "p", date(2027, 1, 4), text="Delivery: panels received.", predecessor_revision_id=old.id
    )
    workflow.analyze("p", new.id)
    assert workflow.compare("p", old.id, new.id).changes
    assert (
        "cannot determine"
        in FieldQuestionService(workflow).answer("p", "Who caused the delay?").answer
    )
    from app import field_api

    monkeypatch.setattr(field_api, "_service", lambda: workflow)
    client = TestClient(app)
    assert client.get("/projects/p/field-dashboard").status_code == 200
    schema = client.get("/openapi.json").json()
    assert not any("schedule-update" in path for path in schema["paths"])


def test_acceptance_immutability_planned_work_supersede_void_and_notifications(workflow):
    report, first = workflow.create_report("p", date(2027, 1, 5), text="Work: underground ongoing.")
    workflow.add_planned_work(
        "p", report.id, "Underground utilities", date(2027, 1, 5), "lookahead"
    )
    workflow.transition("p", report.id, ReportStatus.UNDER_REVIEW, "super")
    workflow.transition("p", report.id, ReportStatus.ACCEPTED, "pm")
    with pytest.raises(ValueError, match="immutable"):
        workflow.transition("p", report.id, ReportStatus.UNDER_REVIEW, "pm")
    _, correction = workflow.create_report(
        "p",
        date(2027, 1, 5),
        text="Work: underground completed reported.",
        predecessor_revision_id=first.id,
    )
    superseded = workflow.supersede_report(
        "p", report.id, correction.id, "pm", "Corrected source record"
    )
    assert superseded.status == ReportStatus.SUPERSEDED
    assert workflow.repository.list("outbox", "p")
    other, _ = workflow.create_report("p", date(2027, 1, 6), text="No work")
    assert (
        workflow.void_report("p", other.id, "pm", "Duplicate contractor report").status
        == ReportStatus.VOIDED
    )
