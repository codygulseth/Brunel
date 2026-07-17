from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import app
from change_workflow.dashboard import ProjectChangeDashboardService
from change_workflow.errors import ConcurrencyError, InvalidTransitionError
from change_workflow.models import (
    ActorReference,
    ChangeDisposition,
    ChangeStatus,
    ImpactCertainty,
    NoteType,
    NotificationRequest,
    NotificationType,
    RelationshipType,
    ReviewerReference,
    WorkflowType,
)
from change_workflow.notifications import (
    NoOpNotificationAdapter,
    NotificationOutboxService,
    TestNotificationAdapter as WorkflowTestAdapter,
)
from change_workflow.qa import OperationalQuestionService
from change_workflow.repository import JsonChangeWorkflowRepository
from change_workflow.service import ProjectChangeService
from change_workflow.staleness import ChangeRegenerationService, StalenessStatus
from config import get_settings
from document_processing import DocumentIngestionService, DocumentType
from revision_intelligence.models import ComparisonRequest
from revision_intelligence.repository import JsonComparisonRepository
from revision_intelligence.service import RevisionComparisonService
from storage import JsonDocumentRepository


@pytest.fixture
def workflow(tmp_path: Path):
    documents = JsonDocumentRepository(tmp_path / "ingested")
    comparisons = JsonComparisonRepository(tmp_path / "revision-intelligence")
    changes = JsonChangeWorkflowRepository(tmp_path / "change-workflow")
    ingestion = DocumentIngestionService(documents)
    old_path = tmp_path / "electrical-r1.txt"
    new_path = tmp_path / "electrical-r2.txt"
    old_path.write_text(
        "1.1 Indoor switchgear enclosure.\n1.2 Lead time is 12 weeks.\n1.3 Factory testing is not required.",
        encoding="utf-8",
    )
    new_path.write_text(
        "1.1 Outdoor NEMA 3R switchgear enclosure.\n1.2 Lead time is 24 weeks.\n1.3 Factory testing is required.",
        encoding="utf-8",
    )
    common = dict(
        project_id="synthetic-project",
        document_type=DocumentType.SPECIFICATION,
        document_family_id="electrical-spec",
        title="Electrical Specification",
    )
    old = ingestion.ingest(file_path=old_path, revision="1", revision_sequence=1, **common)
    new = ingestion.ingest(
        file_path=new_path,
        revision="2",
        revision_sequence=2,
        supersedes_document_id=old.document.document_id,
        **common,
    )
    comparison = RevisionComparisonService(documents, comparisons).compare(
        ComparisonRequest(
            project_id="synthetic-project",
            old_document_id=old.document.document_id,
            new_document_id=new.document.document_id,
        )
    )

    def clock():
        return datetime(2026, 8, 1, 12, tzinfo=UTC)

    service = ProjectChangeService(changes, clock=clock)
    actor = ActorReference(id="pm", display_name="Project Manager")
    result = service.generate_register(comparison, actor)
    return tmp_path, documents, comparisons, changes, service, actor, comparison, result


def test_material_admission_and_idempotent_register_generation(workflow):
    _, _, _, _, service, actor, comparison, first = workflow
    assert first.evaluated == 3 and first.admitted == 3 and first.reused == 0
    second = service.generate_register(comparison, actor)
    assert second.change_ids == first.change_ids and second.reused == 3
    assert all(
        decision.reasons and decision.policy_version == "change-admission-v1"
        for decision in first.decisions
    )


def test_assignment_transition_notes_disposition_and_audit(workflow):
    _, _, _, repository, service, actor, _, result = workflow
    change_id = result.change_ids[0]
    reviewer = ReviewerReference(
        id="electrical-pm", display_name="Electrical PM", discipline="electrical"
    )
    assigned = service.assign(
        "synthetic-project", change_id, reviewer, actor, due_date=date(2026, 8, 5)
    )
    assert assigned.status == ChangeStatus.ASSIGNED and assigned.assignments[-1].due_date == date(
        2026, 8, 5
    )
    reviewing = service.transition("synthetic-project", change_id, ChangeStatus.UNDER_REVIEW, actor)
    noted = service.add_note(
        "synthetic-project", change_id, "Confirm enclosure location.", actor, NoteType.QUESTION
    )
    disposed = service.disposition(
        "synthetic-project",
        change_id,
        ChangeDisposition.REQUIRES_RFI,
        actor,
        "Design clarification required.",
        cost=ImpactCertainty.UNKNOWN,
    )
    assert reviewing.status == ChangeStatus.UNDER_REVIEW and noted.notes[-1].text.startswith(
        "Confirm"
    )
    assert disposed.disposition == ChangeDisposition.REQUIRES_RFI
    assert len(repository.list_audit("synthetic-project", change_id)) == 5


def test_invalid_transition_and_resolution_requirements(workflow):
    _, _, _, _, service, actor, _, result = workflow
    change_id = result.change_ids[0]
    with pytest.raises(InvalidTransitionError):
        service.transition("synthetic-project", change_id, ChangeStatus.UNDER_REVIEW, actor)
    service.assign(
        "synthetic-project",
        change_id,
        ReviewerReference(id="reviewer", display_name="Reviewer"),
        actor,
    )
    service.transition("synthetic-project", change_id, ChangeStatus.UNDER_REVIEW, actor)
    service.transition("synthetic-project", change_id, ChangeStatus.ACCEPTED, actor)
    with pytest.raises(InvalidTransitionError):
        service.transition("synthetic-project", change_id, ChangeStatus.RESOLVED, actor)
    assert service.transition(
        "synthetic-project",
        change_id,
        ChangeStatus.RESOLVED,
        actor,
        resolution="Reviewed and coordinated.",
    ).resolved_at


def test_workflow_links_related_items_and_duplicate_prevention(workflow):
    _, _, _, _, service, actor, _, result = workflow
    change_id = result.change_ids[0]
    linked = service.add_link(
        "synthetic-project",
        change_id,
        WorkflowType.RFI,
        "RFI-042",
        RelationshipType.REQUIRES,
        actor,
        url="https://example.test/rfi/42",
    )
    duplicate = service.add_link(
        "synthetic-project",
        change_id,
        WorkflowType.RFI,
        "RFI-042",
        RelationshipType.REQUIRES,
        actor,
    )
    first = service.create_related_item("synthetic-project", change_id, WorkflowType.RFI, actor)
    second = service.create_related_item("synthetic-project", change_id, WorkflowType.RFI, actor)
    assert len(linked.links) == len(duplicate.links) == 1 and first.id == second.id
    assert first.evidence.old_citation or first.evidence.new_citation
    removed = service.remove_link("synthetic-project", change_id, linked.links[0].id, actor)
    assert all(link.id != linked.links[0].id for link in removed.links)


def test_unassignment_preserves_assignment_history(workflow):
    _, _, _, _, service, actor, _, result = workflow
    change_id = result.change_ids[0]
    service.assign(
        "synthetic-project",
        change_id,
        ReviewerReference(id="reviewer", display_name="Reviewer"),
        actor,
    )
    unassigned = service.unassign(
        "synthetic-project", change_id, actor, reason="Reassignment pending"
    )
    assert unassigned.status == ChangeStatus.UNREVIEWED
    assert unassigned.assignments and not unassigned.assignments[-1].active


def test_project_isolation_and_optimistic_concurrency(workflow):
    _, _, _, repository, service, _, _, result = workflow
    item = service.get("synthetic-project", result.change_ids[0])
    assert repository.get_change("other-project", item.id) is None
    with pytest.raises(ConcurrencyError):
        repository.save_change(item.model_copy(update={"version": 2}), expected_version=99)


def test_dashboard_overdue_ranking_and_stale_marking(workflow):
    _, _, _, repository, service, actor, comparison, result = workflow
    service.assign(
        "synthetic-project",
        result.change_ids[0],
        ReviewerReference(id="pm", display_name="PM"),
        actor,
        due_date=date(2026, 7, 31),
    )
    service.mark_stale("synthetic-project", comparison.id, actor)
    dashboard = ProjectChangeDashboardService(repository).build(
        "synthetic-project", today=date(2026, 8, 1)
    )
    values = {metric.name: metric.count for metric in dashboard.metrics}
    assert values["total_open"] == 3 and values["overdue"] == 1 and values["stale_source"] == 3
    assert dashboard.priority_queue


def test_staleness_assessment_and_regeneration_preserve_history(workflow):
    _, documents, comparisons, repository, service, actor, comparison, _ = workflow
    comparison_service = RevisionComparisonService(documents, comparisons)
    orchestration = ChangeRegenerationService(comparison_service, service)
    assert orchestration.assess(comparison).status == StalenessStatus.CURRENT
    old = documents.get(comparison.old_document.document_id)
    assert old is not None
    documents.save(
        old.model_copy(
            update={"document": old.document.model_copy(update={"content_hash": "f" * 64})}
        )
    )
    assert orchestration.assess(comparison).status == StalenessStatus.STALE
    regenerated, result = orchestration.regenerate(
        comparison,
        ComparisonRequest(
            project_id="synthetic-project",
            old_document_id=comparison.old_document.document_id,
            new_document_id=comparison.new_document.document_id,
        ),
        actor,
    )
    assert regenerated.id != comparison.id and result.admitted == 3
    assert any(item.source_stale for item in repository.list_changes("synthetic-project"))
    assert repository.list_audit("synthetic-project")


def test_notification_outbox_is_local_idempotent_and_redacted(workflow):
    _, _, _, repository, _, actor, _, result = workflow
    recipient = ReviewerReference(id="pm", display_name="PM")
    request = NotificationRequest(
        id="temporary",
        project_id="synthetic-project",
        change_id=result.change_ids[0],
        event_id="event-1",
        recipient=recipient,
        notification_type=NotificationType.ASSIGNMENT_CREATED,
        created_at=datetime.now(UTC),
        payload={"title": "Review change", "source_excerpt": "confidential"},
    )
    service = NotificationOutboxService(repository)
    first = service.queue(request)
    second = service.queue(request)
    assert (
        first.id == second.id
        and "source_excerpt" not in first.payload
        and len(repository.list_notifications("synthetic-project")) == 1
    )
    assert NoOpNotificationAdapter().deliver(first) is None
    adapter = WorkflowTestAdapter()
    adapter.deliver(first)
    assert adapter.delivered == [first]


def test_operational_qa_labels_team_records_and_scopes_project(workflow):
    _, _, _, repository, service, actor, _, result = workflow
    service.assign(
        "synthetic-project",
        result.change_ids[0],
        ReviewerReference(id="epm", display_name="Electrical PM"),
        actor,
    )
    answer = OperationalQuestionService(repository).answer(
        "synthetic-project", "Who is assigned to the switchgear enclosure change?"
    )
    assert (
        answer.sufficient
        and answer.evidence_type == "project_team_record"
        and "Electrical PM" in answer.answer
    )
    assert not OperationalQuestionService(repository).answer("other", "switchgear").sufficient


def test_fastapi_health_openapi_project_isolation_and_workflow(workflow, monkeypatch):
    tmp_path, _, comparisons, _, _, _, comparison, _ = workflow
    monkeypatch.setenv("BRUNEL_DATA_DIRECTORY", str(tmp_path))
    get_settings.cache_clear()
    client = TestClient(app)
    assert (
        client.get("/health").status_code == 200 and client.get("/openapi.json").status_code == 200
    )
    generated = client.post(f"/projects/synthetic-project/comparisons/{comparison.id}/register")
    assert generated.status_code == 200
    change_id = generated.json()["change_ids"][0]
    assert client.get(f"/projects/other/changes/{change_id}").status_code == 404
    assigned = client.post(
        f"/projects/synthetic-project/changes/{change_id}/assign",
        json={"assignee_id": "epm", "assignee_name": "Electrical PM", "due_date": "2026-08-05"},
    )
    assert assigned.status_code == 200
    stale = client.post(f"/projects/synthetic-project/comparisons/{comparison.id}/staleness-check")
    assert stale.status_code == 200 and stale.json()["status"] == "current"
    unassigned = client.post(f"/projects/synthetic-project/changes/{change_id}/unassign", json={})
    assert unassigned.status_code == 200
    assert client.get("/projects/synthetic-project/changes?limit=1").json()["total"] == 3
    dashboard_response = client.get("/projects/synthetic-project/change-dashboard")
    assert dashboard_response.status_code == 200
    assert "source_location" not in dashboard_response.text
    get_settings.cache_clear()


def test_new_canonical_modules_do_not_import_legacy_prototype():
    roots = (Path("change_workflow"), Path("revision_intelligence"), Path("app"))
    for root in roots:
        for path in root.glob("*.py"):
            assert "ai_project_engineer" not in path.read_text(encoding="utf-8")


def test_change_workflow_cli_generation_assignment_and_dashboard(workflow, monkeypatch, capsys):
    from app.cli import main as cli_main

    tmp_path, _, _, _, _, _, comparison, _ = workflow
    monkeypatch.setenv("BRUNEL_DATA_DIRECTORY", str(tmp_path))
    get_settings.cache_clear()
    assert (
        cli_main(
            [
                "change-register-generate",
                "--project-id",
                "synthetic-project",
                "--comparison-id",
                comparison.id,
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert '"reused": 3' in output
    assert cli_main(["change-list", "--project-id", "synthetic-project"]) == 0
    listing = capsys.readouterr().out
    change_id = listing.split("\t", 1)[0]
    assert (
        cli_main(
            [
                "change-assign",
                "--project-id",
                "synthetic-project",
                "--change-id",
                change_id,
                "--assignee-id",
                "epm",
                "--assignee-name",
                "Electrical PM",
                "--due-date",
                "2026-08-05",
            ]
        )
        == 0
    )
    assert (
        cli_main(
            [
                "ask",
                "--project-id",
                "synthetic-project",
                "--question",
                "Who is assigned to this project change?",
            ]
        )
        == 0
    )
    assert "Evidence type: project_team_record" in capsys.readouterr().out
    assert cli_main(["change-dashboard", "--project-id", "synthetic-project"]) == 0
    assert '"total_open"' in capsys.readouterr().out
    assert (
        cli_main(
            [
                "comparison-stale-check",
                "--project-id",
                "synthetic-project",
                "--comparison-id",
                comparison.id,
            ]
        )
        == 0
    )
    assert '"status": "current"' in capsys.readouterr().out
    get_settings.cache_clear()
