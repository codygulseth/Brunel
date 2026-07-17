from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import app
from change_workflow.models import (
    ActorReference,
    ChangeStatus,
    ImpactCertainty,
    ReviewerReference,
)
from change_workflow.notifications import NoOpNotificationAdapter
from change_workflow.repository import JsonChangeWorkflowRepository
from change_workflow.service import ProjectChangeService
from config import get_settings
from document_processing import DocumentIngestionService, DocumentType
from revision_intelligence.models import ComparisonRequest
from revision_intelligence.repository import JsonComparisonRepository
from revision_intelligence.service import RevisionComparisonService
from rfi.drafting import RFIDuplicateDetector, RFIQualityValidator
from rfi.errors import RFIDraftingError, RFITransitionError
from rfi.models import (
    RFIImpactType,
    RFIResponseType,
    RFIReviewDecision,
    RFIStatus,
)
from rfi.notifications import RFINotificationService
from rfi.qa import RFIQuestionService
from rfi.repository import JsonRFIRepository
from rfi.reporting import RFILogService, RFIRenderer
from rfi.service import RFIService
from storage import JsonDocumentRepository


@pytest.fixture
def rfi_workflow(tmp_path: Path):
    documents = JsonDocumentRepository(tmp_path / "ingested")
    comparisons = JsonComparisonRepository(tmp_path / "revision-intelligence")
    changes = JsonChangeWorkflowRepository(tmp_path / "change-workflow")
    ingestion = DocumentIngestionService(documents)
    old_path = tmp_path / "electrical-r1.txt"
    new_path = tmp_path / "electrical-r2.txt"
    old_path.write_text("Indoor switchgear enclosure. Lead time is 12 weeks.", encoding="utf-8")
    new_path.write_text(
        "Outdoor NEMA 3R switchgear enclosure. Lead time is 24 weeks.", encoding="utf-8"
    )
    common = {
        "project_id": "demo-project",
        "document_type": DocumentType.SPECIFICATION,
        "document_family_id": "electrical-spec",
        "title": "Electrical Specification",
    }
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
            project_id="demo-project",
            old_document_id=old.document.document_id,
            new_document_id=new.document.document_id,
        )
    )
    actor = ActorReference(id="electrical-pm", display_name="Electrical PM")
    change_service = ProjectChangeService(changes)
    register = change_service.generate_register(comparison, actor)
    repository = JsonRFIRepository(tmp_path / "rfi")
    service = RFIService(repository, changes, documents=documents)
    return tmp_path, repository, changes, change_service, service, actor, register.change_ids[0]


def _draft(rfi_workflow):
    _, _, _, _, service, actor, change_id = rfi_workflow
    return service.draft_from_change(
        "demo-project",
        change_id,
        actor,
        instructions=(
            "Please confirm the required enclosure classification, installation location, "
            "and whether environmental controls are required."
        ),
        responsible_party="Electrical Engineer",
        required_date=date(2026, 8, 15),
    ).rfi


def test_evidence_drafting_numbering_links_and_project_isolation(rfi_workflow):
    _, repository, changes, _, service, actor, change_id = rfi_workflow
    first = _draft(rfi_workflow)
    second = service.create(
        project_id="demo-project", subject="Other", question="Confirm?", actor=actor
    )
    assert first.number == "RFI-001" and second.number == "RFI-002"
    assert first.evidence and first.related_project_change_ids == (change_id,)
    change = ProjectChangeService(changes).get("demo-project", change_id)
    assert any(link.reference == first.id for link in change.links)
    assert repository.get("another-project", first.id) is None


def test_draft_quality_duplicate_and_model_failure_fallback(rfi_workflow):
    _, repository, _, _, service, actor, change_id = rfi_workflow
    first = _draft(rfi_workflow)
    duplicate = service.draft_from_change("demo-project", change_id, actor)
    assert duplicate.duplicates.possible_duplicate_ids == (first.id,)
    assert "same_project_change" in duplicate.duplicates.reasons

    class FailingProvider:
        name = "failing"

        def improve(self, rfi):
            raise RuntimeError("offline")

    fallback = RFIService(
        repository, service.changes, provider=FailingProvider()
    ).draft_from_change("demo-project", change_id, actor, use_model=True)
    assert fallback.provider == "deterministic" and "failed safely" in fallback.warnings[0]

    unsupported = first.model_copy(update={"question": "Confirm a 90 day delay?"})
    assert any(
        issue.code == "unsupported_numeric_claim"
        for issue in RFIQualityValidator().assess(unsupported).issues
    )
    assert RFIDuplicateDetector().assess(duplicate.rfi, (first,)).strength == "strong"


def test_insufficient_evidence_is_blocked(rfi_workflow):
    _, _, changes, _, service, actor, change_id = rfi_workflow
    change = ProjectChangeService(changes).get("demo-project", change_id)
    evidence = change.evidence.model_copy(update={"old_citation": None, "new_citation": None})
    changes.save_change(
        change.model_copy(update={"evidence": evidence, "version": change.version + 1}),
        expected_version=change.version,
    )
    with pytest.raises(RFIDraftingError, match="insufficient cited evidence"):
        service.draft_from_change("demo-project", change_id, actor)


def test_review_revisions_approval_issue_and_audit(rfi_workflow):
    _, repository, _, _, service, actor, _ = rfi_workflow
    item = _draft(rfi_workflow)
    reviewer = ReviewerReference(id="reviewer", display_name="Reviewer")
    service.assign_reviewer("demo-project", item.id, reviewer, actor)
    service.transition("demo-project", item.id, RFIStatus.PENDING_INTERNAL_REVIEW, actor)
    service.review(
        "demo-project",
        item.id,
        RFIReviewDecision.REVISIONS_REQUIRED,
        reviewer,
        actor,
        "Clarify environmental controls.",
    )
    revised = service.revise(
        "demo-project",
        item.id,
        actor,
        question="Please confirm NEMA classification, outdoor location, and environmental controls.",
        summary="Addressed reviewer comment",
    )
    assert len(revised.revisions) == 2 and revised.status == RFIStatus.DRAFT
    service.transition("demo-project", item.id, RFIStatus.PENDING_INTERNAL_REVIEW, actor)
    approved = service.review("demo-project", item.id, RFIReviewDecision.APPROVED, reviewer, actor)
    assert approved.revisions[-1].approved
    issued = service.transition("demo-project", item.id, RFIStatus.ISSUED, actor)
    assert issued.issued_at and len(repository.audit("demo-project", item.id)) >= 8


def test_deferred_numbering_override_void_and_supersede(rfi_workflow):
    _, repository, changes, _, _, actor, _ = rfi_workflow
    service = RFIService(repository, changes, assign_number_at_creation=False)
    draft = service.create(
        project_id="demo-project", subject="Draft", question="Confirm?", actor=actor
    )
    assert draft.number.startswith("UNASSIGNED-")
    overridden = service.override_number(
        "demo-project", draft.id, "ELEC-RFI-012", actor, reason="Document control reservation"
    )
    assert overridden.number == "ELEC-RFI-012"
    with pytest.raises(RFITransitionError, match="Reason is required"):
        service.transition("demo-project", draft.id, RFIStatus.VOID, actor)
    assert (
        service.transition(
            "demo-project", draft.id, RFIStatus.VOID, actor, reason="Duplicate request"
        ).status
        == RFIStatus.VOID
    )
    second = service.create(
        project_id="demo-project", subject="Superseded", question="Confirm?", actor=actor
    )
    assert (
        service.transition(
            "demo-project",
            second.id,
            RFIStatus.SUPERSEDED,
            actor,
            reason="Replaced by consolidated RFI",
        ).status
        == RFIStatus.SUPERSEDED
    )


def test_response_analysis_impacts_closure_and_reopen(rfi_workflow):
    _, _, _, change_service, service, actor, change_id = rfi_workflow
    item = _draft(rfi_workflow)
    reviewer = ReviewerReference(id="reviewer", display_name="Reviewer")
    service.assign_reviewer("demo-project", item.id, reviewer, actor)
    service.transition("demo-project", item.id, RFIStatus.PENDING_INTERNAL_REVIEW, actor)
    service.review("demo-project", item.id, RFIReviewDecision.APPROVED, reviewer, actor)
    service.transition("demo-project", item.id, RFIStatus.ISSUED, actor)
    draft_response = service.record_response(
        "demo-project",
        item.id,
        actor,
        text="Internal interpretation only",
        responding_party="Project team",
        response_type=RFIResponseType.DRAFT,
    )
    assert draft_response.status == RFIStatus.ISSUED
    official = service.record_response(
        "demo-project",
        item.id,
        actor,
        text="Provide NEMA 3R outdoors. Procurement lead time may affect schedule.",
        responding_party="Engineer",
    )
    analysis = service.analyze_response("demo-project", item.id)
    assert official.status == RFIStatus.RESPONSE_RECEIVED
    assert set(analysis.potential_impacts) == {RFIImpactType.PROCUREMENT, RFIImpactType.SCHEDULE}
    service.transition("demo-project", item.id, RFIStatus.CLARIFICATION_REQUIRED, actor)
    service.transition("demo-project", item.id, RFIStatus.RESPONSE_RECEIVED, actor)
    service.add_impact(
        "demo-project",
        item.id,
        actor,
        impact_type=RFIImpactType.COST,
        certainty=ImpactCertainty.UNKNOWN,
        description="Cost impact has not been confirmed.",
    )
    service.transition("demo-project", item.id, RFIStatus.ANSWERED, actor)
    with pytest.raises(RFITransitionError, match="Related project changes"):
        service.transition(
            "demo-project", item.id, RFIStatus.CLOSED, actor, resolution="Direction coordinated."
        )
    change_service.assign(
        "demo-project",
        change_id,
        ReviewerReference(id="pm", display_name="PM"),
        actor,
    )
    change_service.transition("demo-project", change_id, ChangeStatus.UNDER_REVIEW, actor)
    change_service.transition("demo-project", change_id, ChangeStatus.ACCEPTED, actor)
    change_service.transition(
        "demo-project",
        change_id,
        ChangeStatus.RESOLVED,
        actor,
        resolution="RFI direction accepted.",
    )
    closed = service.transition(
        "demo-project", item.id, RFIStatus.CLOSED, actor, resolution="Direction coordinated."
    )
    with pytest.raises(RFITransitionError, match="requires a reason"):
        service.transition("demo-project", item.id, RFIStatus.UNDER_REVIEW, actor)
    assert (
        service.transition(
            "demo-project", item.id, RFIStatus.UNDER_REVIEW, actor, reason="New field condition"
        ).status
        == RFIStatus.UNDER_REVIEW
    )
    assert closed.closed_at


def test_log_dashboard_exports_qa_and_no_external_delivery(rfi_workflow):
    _, repository, changes, _, service, actor, _ = rfi_workflow
    item = _draft(rfi_workflow)
    overdue = item.model_copy(update={"required_date": date(2020, 1, 1)})
    repository.save(overdue, expected_version=item.version)
    assert RFILogService(repository).list("demo-project", overdue=True)[0].id == item.id
    assert RFILogService(repository).dashboard("demo-project").metrics["overdue"] == 1
    markdown = RFIRenderer().markdown(overdue)
    assert "Potential impact notice" in markdown and "## Evidence" in markdown
    assert "number,subject,status" in RFIRenderer().csv_log((overdue,))
    answer = RFIQuestionService(repository).answer("demo-project", "Why was RFI-001 created?")
    assert answer.sufficient and answer.citations and "project change" in answer.answer
    cost_answer = RFIQuestionService(repository).answer(
        "demo-project", "Does RFI-001 have a confirmed cost impact?"
    )
    assert "No confirmed cost impact" in cost_answer.answer
    service.assign_reviewer(
        "demo-project",
        item.id,
        ReviewerReference(id="reviewer", display_name="Reviewer"),
        actor,
    )
    assert RFINotificationService(repository, changes).queue_due_notifications("demo-project") == 1
    no_op = NoOpNotificationAdapter()
    assert no_op.deliver(changes.list_notifications("demo-project")[0]) is None


def test_rfi_api_openapi_scoping_and_cli(rfi_workflow, monkeypatch, capsys):
    from app.cli import main as cli_main

    tmp_path, _, _, _, _, _, change_id = rfi_workflow
    monkeypatch.setenv("BRUNEL_DATA_DIRECTORY", str(tmp_path))
    get_settings.cache_clear()
    client = TestClient(app)
    assert "/projects/{project_id}/rfis" in client.get("/openapi.json").json()["paths"]
    drafted = client.post(
        "/projects/demo-project/rfis/draft-from-change",
        json={
            "change_id": change_id,
            "responsible_party": "Engineer",
            "required_date": "2026-08-15",
        },
    )
    assert drafted.status_code == 201 and "source_location" not in drafted.text
    rfi_id = drafted.json()["rfi"]["id"]
    assert client.get(f"/projects/other/rfis/{rfi_id}").status_code == 404
    assert client.get("/projects/demo-project/rfis?limit=1").json()["total"] >= 1
    assert cli_main(["rfi-list", "--project-id", "demo-project"]) == 0
    assert "RFI-" in capsys.readouterr().out
    assert cli_main(["rfi-dashboard", "--project-id", "demo-project"]) == 0
    assert '"total"' in capsys.readouterr().out
    get_settings.cache_clear()
