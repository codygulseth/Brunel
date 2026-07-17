from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import app
from app.cli import main
from app.submittal_demo import run_synthetic_submittal_demo
from change_workflow.models import ActorReference, ImpactCertainty, ReviewerReference
from change_workflow.repository import JsonChangeWorkflowRepository
from config import get_settings
from document_processing import DocumentIngestionService, DocumentType
from rfi.repository import JsonRFIRepository
from rfi.service import RFIService
from storage import JsonDocumentRepository
from submittal.errors import SubmittalTransitionError
from submittal.extraction import SubmittalRequirementExtractionService
from submittal.models import (
    AttachmentMetadata,
    CandidateStatus,
    CompletenessStatus,
    InternalReviewDecision,
    MatrixStatus,
    OfficialDisposition,
    RequirementReviewDecision,
    StalenessStatus,
    SubmittalManufacturer,
    SubmittalProduct,
    SubmittalStatus,
    SubmittalType,
    SubstitutionRequest,
    SubstitutionStatus,
)
from submittal.notifications import SubmittalNotificationService
from submittal.qa import SubmittalQuestionService
from submittal.reporting import SubmittalLogService, SubmittalRenderer
from submittal.repository import JsonSubmittalRepository
from submittal.service import SubmittalService


@pytest.fixture
def workflow(tmp_path: Path):
    documents = JsonDocumentRepository(tmp_path / "ingested")
    repository = JsonSubmittalRepository(tmp_path / "submittals")
    changes = JsonChangeWorkflowRepository(tmp_path / "change-workflow")
    rfis = JsonRFIRepository(tmp_path / "rfi")
    source = tmp_path / "section-26-24-13.txt"
    source.write_text(
        "SECTION 26 24 13 SWITCHBOARDS\n"
        "1.5.A Submit product data for switchboards.\n"
        "1.5.B Submit shop drawings showing dimensions.\n"
        "1.5.C Submit short-circuit calculations signed by the engineer.\n"
        "1.5.D Submit coordination drawings for electrical rooms.\n"
        "1.5.E Submit factory test reports before shipment.\n",
        encoding="utf-8",
    )
    ingested = DocumentIngestionService(documents).ingest(
        project_id="project-a",
        file_path=source,
        document_type=DocumentType.SPECIFICATION,
        title="Switchboards",
        discipline="electrical",
        specification_section="26 24 13",
    )
    actor = ActorReference(id="pm", display_name="Project Manager")
    service = SubmittalService(repository, changes, rfis)
    return tmp_path, documents, repository, changes, rfis, service, actor, ingested


def _accept_all(workflow):
    _, documents, repository, _, _, service, actor, _ = workflow
    result = SubmittalRequirementExtractionService(documents, repository).extract("project-a")
    ids = []
    for candidate_id in result.candidate_ids:
        admitted = service.review_candidate(
            "project-a",
            candidate_id,
            RequirementReviewDecision.ACCEPT,
            actor,
            explanation="Cited paragraph verified.",
            responsible_subcontractor="Electrical Subcontractor",
        )
        if admitted.register_item_id:
            ids.append(admitted.register_item_id)
    return tuple(ids)


def _attachment(kind: SubmittalType) -> AttachmentMetadata:
    return AttachmentMetadata(
        id=f"att-{kind.value}",
        filename=f"{kind.value}.pdf",
        document_type=kind,
        storage_reference=f"local://{kind.value}",
    )


def _complete_package(workflow):
    _, _, _, _, _, service, actor, _ = workflow
    ids = _accept_all(workflow)
    kinds = tuple(
        service.get_register("project-a", item_id).requirements[0].submittal_type for item_id in ids
    )
    package = service.create_package(
        "project-a",
        ids[0],
        actor,
        register_item_ids=ids[1:],
        submitter="Electrical Subcontractor",
        included_types=kinds,
        attachments=tuple(_attachment(kind) for kind in kinds),
        deviations=("No deviations declared; pending design-team review.",),
    )
    assessment = service.review_completeness("project-a", package.id, actor)
    return ids, service.get_package("project-a", package.id), assessment


def _issue(workflow):
    _, _, _, _, _, service, actor, _ = workflow
    ids, package, assessment = _complete_package(workflow)
    reviewer = ReviewerReference(id="reviewer", display_name="Reviewer")
    service.submit_internal_review("project-a", package.id, reviewer, actor)
    service.internal_review(
        "project-a",
        package.id,
        InternalReviewDecision.APPROVED_FOR_SUBMISSION,
        reviewer,
        actor,
    )
    return ids, service.issue_package("project-a", package.id, actor), assessment


def test_cited_extraction_is_deterministic_idempotent_and_project_scoped(workflow):
    _, documents, repository, _, _, _, _, ingested = workflow
    extraction = SubmittalRequirementExtractionService(documents, repository)
    first = extraction.extract("project-a")
    second = extraction.extract("project-a")
    assert first.extracted == 5 and first.reused == 0
    assert second.candidate_ids == first.candidate_ids and second.reused == 5
    candidates = repository.list_candidates("project-a")
    assert {item.submittal_type for item in candidates} == {
        SubmittalType.PRODUCT_DATA,
        SubmittalType.SHOP_DRAWING,
        SubmittalType.CALCULATION,
        SubmittalType.COORDINATION_DRAWING,
        SubmittalType.TEST_REPORT,
    }
    assert all(
        item.evidence.excerpt in ingested.document.source_path.read_text(encoding="utf-8")
        and item.evidence.citation.document_id == ingested.document.document_id
        for item in candidates
    )
    assert repository.list_candidates("another-project") == ()


def test_optional_provider_failure_falls_back_without_fabricated_candidates(workflow):
    _, documents, repository, _, _, _, _, _ = workflow

    class FailingProvider:
        name = "failing"

        def enhance(self, candidates):
            raise RuntimeError("offline")

    result = SubmittalRequirementExtractionService(
        documents, repository, provider=FailingProvider()
    ).extract("project-a", use_model=True)
    assert result.provider == "deterministic"
    assert result.candidate_ids and "failed safely" in result.warnings[0]


def test_candidate_review_numbering_merge_split_and_manual_creation(workflow):
    _, documents, repository, _, _, service, actor, _ = workflow
    extraction = SubmittalRequirementExtractionService(documents, repository).extract("project-a")
    candidates = repository.list_candidates("project-a")
    first = service.review_candidate(
        "project-a",
        candidates[0].id,
        RequirementReviewDecision.REJECT,
        actor,
        explanation="Not in subcontract scope.",
    )
    assert first.register_item_id is None
    assert service.get_candidate("project-a", candidates[0].id).status == CandidateStatus.REJECTED
    split = service.split_candidate(
        "project-a",
        candidates[1].id,
        actor,
        ((SubmittalType.SHOP_DRAWING, "Layout"), (SubmittalType.OTHER, "Details")),
    )
    assert len(split) == 2 and all(item.status == CandidateStatus.PENDING_REVIEW for item in split)
    merged = service.merge_candidates(
        "project-a", (candidates[2].id, candidates[3].id), actor, description="Engineering package"
    )
    manual = service.create_register(
        project_id="project-a",
        specification_section="01 33 00",
        description="Manual closeout package",
        actor=actor,
    )
    assert merged.register_number == "SUB-001" and manual.register_number == "SUB-002"
    assert extraction.extracted == 5


def test_completeness_matrix_blocks_missing_content_and_requires_reapproval(workflow):
    _, _, _, _, _, service, actor, _ = workflow
    ids = _accept_all(workflow)
    package = service.create_package(
        "project-a",
        ids[0],
        actor,
        register_item_ids=ids[1:],
        submitter="Electrical Subcontractor",
        included_types=(SubmittalType.PRODUCT_DATA,),
        attachments=(_attachment(SubmittalType.PRODUCT_DATA),),
    )
    blocked = service.review_completeness("project-a", package.id, actor)
    assert blocked.status == CompletenessStatus.BLOCKED
    assert any(issue.blocks_routing and issue.citation for issue in blocked.issues)
    with pytest.raises(SubmittalTransitionError, match="completeness"):
        service.submit_internal_review(
            "project-a", package.id, ReviewerReference(id="r", display_name="R"), actor
        )
    kinds = tuple(
        service.get_register("project-a", item_id).requirements[0].submittal_type for item_id in ids
    )
    revised = service.revise_package(
        "project-a",
        package.id,
        actor,
        change_summary="Added cited requirements",
        included_types=kinds,
        attachments=tuple(_attachment(kind) for kind in kinds),
        deviations=("No deviations declared; pending design-team review.",),
    )
    assessment = service.review_completeness("project-a", package.id, actor)
    assert assessment.status in {
        CompletenessStatus.COMPLETE,
        CompletenessStatus.COMPLETE_WITH_WARNINGS,
    }
    assert revised.revisions[0].internally_approved is False
    matrix = service.get_package("project-a", package.id).compliance_matrix
    assert matrix and all(item.status == MatrixStatus.ADDRESSED for item in matrix)
    assert all(item.human_review_required for item in matrix)


def test_project_scoped_product_tracking_and_controlled_substitution(workflow):
    _, _, _, _, _, service, actor, _ = workflow
    item_id = _accept_all(workflow)[0]
    package = service.create_package(
        "project-a",
        item_id,
        actor,
        submitter="Electrical Subcontractor",
        manufacturer=SubmittalManufacturer(name="Synthetic Electric", project_id="project-a"),
        product=SubmittalProduct(
            name="Main Switchboard",
            model_number="MSB-1",
            supplier="Synthetic Supplier",
            lead_time_days=120,
        ),
        included_types=(SubmittalType.PRODUCT_DATA,),
        attachments=(_attachment(SubmittalType.PRODUCT_DATA),),
    )
    revision = package.revisions[-1]
    assert revision.product and revision.product.project_id == "project-a"
    assert revision.product.approved is False
    assert revision.product.related_submittal_ids == (item_id,)
    substitution = SubstitutionRequest(
        id="substitution-001",
        specified_product="Basis-of-design switchboard",
        proposed_substitute="Main Switchboard MSB-1",
        reason="Supply-chain review",
        product_comparison={"rating": "Human comparison required"},
        cost_impact=ImpactCertainty.UNKNOWN,
        schedule_impact=ImpactCertainty.POSSIBLE,
        required_documentation=("Product data", "Warranty comparison"),
        status=SubstitutionStatus.PENDING_INTERNAL_REVIEW,
    )
    updated = service.create_substitution("project-a", package.id, actor, substitution)
    assert updated.substitution_request == substitution
    assert updated.substitution_request.official_decision is None
    assert any(
        event.event_type == "substitution_requested"
        for event in service.repository.audit("project-a", package.id)
    )


def test_official_response_is_distinct_resubmittal_and_human_release(workflow):
    _, _, _, _, _, service, actor, _ = workflow
    ids, package, _ = _issue(workflow)
    informal = service.record_response(
        "project-a",
        package.id,
        actor,
        responding_organization="Project team",
        disposition=OfficialDisposition.REVIEWED,
        original_disposition_text="Internal note only.",
        official=False,
    )
    assert informal.internal_review_status.value == "issued"
    evidence = service.get_register("project-a", ids[0]).requirements[0].evidence
    service.record_response(
        "project-a",
        package.id,
        actor,
        responding_organization="Engineer",
        disposition=OfficialDisposition.REVISE_AND_RESUBMIT,
        original_disposition_text="Revise and resubmit.",
        required_corrections=("Confirm clearances.",),
        evidence=evidence,
    )
    analysis = service.analyze_response("project-a", package.id, actor)
    assert analysis.resubmittal_required and analysis.citations == evidence
    revised = service.resubmit(
        "project-a", package.id, actor, change_summary="Confirmed clearances"
    )
    assert revised.current_revision == 2 and len(revised.revisions) == 2
    service.review_completeness("project-a", package.id, actor)
    reviewer = ReviewerReference(id="reviewer", display_name="Reviewer")
    service.submit_internal_review("project-a", package.id, reviewer, actor)
    service.internal_review(
        "project-a",
        package.id,
        InternalReviewDecision.APPROVED_FOR_SUBMISSION,
        reviewer,
        actor,
    )
    service.issue_package("project-a", package.id, actor)
    service.record_response(
        "project-a",
        package.id,
        actor,
        responding_organization="Engineer",
        disposition=OfficialDisposition.APPROVED_AS_NOTED,
        original_disposition_text="Approved as noted.",
        required_corrections=("Coordinate entries.",),
        evidence=evidence,
    )
    with pytest.raises(SubmittalTransitionError, match="human confirmation"):
        service.confirm_procurement_release(
            "project-a", ids[0], actor, corrections_incorporated=False
        )
    released = service.confirm_procurement_release(
        "project-a", ids[0], actor, corrections_incorporated=True
    )
    assert released.status == SubmittalStatus.PROCUREMENT_RELEASED


def test_procurement_staleness_rfi_links_reporting_notifications_and_qa(workflow):
    _, _, repository, changes, rfis, service, actor, _ = workflow
    ids, package, _ = _issue(workflow)
    rfi = RFIService(rfis).create(
        project_id="project-a", subject="Coordination", question="Confirm dimensions?", actor=actor
    )
    linked = service.link_rfi("project-a", ids[0], rfi.id, actor)
    assert linked.related_rfi_ids == (rfi.id,)
    assert ids[0] in RFIService(rfis).get("project-a", rfi.id).related_submittal_ids
    updated = service.update_procurement(
        "project-a",
        ids[0],
        actor,
        required_on_site_date=date(2027, 1, 1),
        fabrication_days=120,
        shipping_days=14,
        processing_days=7,
        review_days=14,
        resubmittal_days=14,
        buffer_days=7,
    )
    assert updated.procurement.derived_latest_submit_date == date(2026, 7, 9)
    assert updated.procurement.calculation_basis == "calendar_days"
    stale = service.mark_stale(
        "project-a",
        package.id,
        actor,
        reasons=("RFI may change dimensions.",),
        source_references=(rfi.number,),
        status=StalenessStatus.POTENTIALLY_STALE,
    )
    assert stale.staleness_assessments[-1].status == StalenessStatus.POTENTIALLY_STALE
    service.assign(
        "project-a",
        ids[0],
        actor,
        reviewer=ReviewerReference(id="reviewer", display_name="Reviewer"),
        planned_submit_date=date(2026, 7, 1),
    )
    assert SubmittalNotificationService(repository, changes).queue_due_notifications(
        "project-a", now=datetime(2026, 7, 17, tzinfo=UTC)
    )
    log = SubmittalLogService(repository)
    assert log.list("project-a", related_rfi_id=rfi.id)[0].id == ids[0]
    assert log.dashboard("project-a").metrics["total"] == 5
    assert "Specification requirements" in SubmittalRenderer().markdown(
        service.get_register("project-a", ids[0]), (stale,)
    )
    csv_text = SubmittalRenderer(repository).csv_log(log.list("project-a"))
    assert "procurement_exposure" in csv_text and "SUB-" in csv_text
    answer = SubmittalQuestionService(repository).answer(
        "project-a", f"Is {linked.register_number} stale and released for procurement?"
    )
    assert answer.sufficient and linked.register_number in answer.answer and answer.citations


def test_api_openapi_cli_demo_and_no_model_default(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setenv("BRUNEL_DATA_DIRECTORY", str(tmp_path / "api-data"))
    get_settings.cache_clear()
    client = TestClient(app)
    created = client.post(
        "/projects/api-project/submittals",
        json={"specification_section": "01 33 00", "description": "Manual product data"},
        headers={"X-Idempotency-Key": "manual-product-data"},
    )
    assert created.status_code == 201
    item_id = created.json()["id"]
    replay = client.post(
        "/projects/api-project/submittals",
        json={"specification_section": "01 33 00", "description": "Manual product data"},
        headers={"X-Idempotency-Key": "manual-product-data"},
    )
    assert replay.json()["id"] == item_id
    assert client.get(f"/projects/api-project/submittals/{item_id}").status_code == 200
    assert client.get("/projects/api-project/submittal-dashboard").status_code == 200
    assert (
        "/projects/{project_id}/submittal-packages/{package_id}/responses" in app.openapi()["paths"]
    )
    assert (
        main(
            [
                "submittal-create",
                "--project-id",
                "cli-project",
                "--specification-section",
                "03 30 00",
                "--description",
                "Concrete mix design",
            ]
        )
        == 0
    )
    assert "Created SUB-001" in capsys.readouterr().out
    assert (
        main(
            [
                "ask",
                "--project-id",
                "api-project",
                "--question",
                "Is SUB-001 released for procurement?",
            ]
        )
        == 0
    )
    assert "Evidence type: cited specification, project record, and official response" in (
        capsys.readouterr().out
    )
    result = run_synthetic_submittal_demo(tmp_path / "demo-data", "demo-project")
    assert result["candidate_count"] == 5
    assert result["official_disposition"] == "approved_as_noted"
    assert Path(str(result["report"])).is_file()
    assert get_settings().submittal.model_assistance_enabled is False
    assert get_settings().models.provider == "disabled"
    get_settings.cache_clear()
