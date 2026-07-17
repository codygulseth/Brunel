from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

from app.api import app
from app.cli import main
from app.submittal_attachment_demo import run_synthetic_attachment_demo
from change_workflow.models import ActorReference, ReviewerReference
from change_workflow.repository import JsonChangeWorkflowRepository
from config import get_settings
from storage import JsonDocumentRepository
from submittal.attachment_intelligence import (
    AttachmentIngestionService,
    LocalAttachmentFileStore,
    PackageAttachmentAnalysisService,
    PackageRevisionComparisonService,
)
from submittal.attachment_models import (
    AttachmentRole,
    AttachmentType,
    DuplicateStatus,
    ExtractionStatus,
    HumanConfirmationStatus,
    PackageAttachmentStalenessStatus,
    PackageChangeType,
    ReadabilityStatus,
)
from submittal.attachment_qa import AttachmentQuestionService, AttachmentSearchService
from submittal.attachment_reporting import AttachmentIntelligenceRenderer
from submittal.attachment_repository import JsonAttachmentIntelligenceRepository
from submittal.errors import AttachmentSecurityError, SubmittalConcurrencyError
from submittal.models import MatrixStatus, PackageReviewStatus
from submittal.repository import JsonSubmittalRepository


@pytest.fixture(scope="module")
def attachment_demo(tmp_path_factory: pytest.TempPathFactory):
    tmp_path = tmp_path_factory.mktemp("attachment-intelligence")
    data = tmp_path / "data"
    result = run_synthetic_attachment_demo(data, "project-a")
    attachments = JsonAttachmentIntelligenceRepository(data / "submittal-attachment-intelligence")
    submittals = JsonSubmittalRepository(data / "submittals")
    changes = JsonChangeWorkflowRepository(data / "change-workflow")
    actor = ActorReference(id="pm", display_name="Project Manager")
    analysis = PackageAttachmentAnalysisService(attachments, submittals, changes)
    ingestion = AttachmentIngestionService(
        attachments,
        submittals,
        JsonDocumentRepository(data / "ingested"),
        LocalAttachmentFileStore(data / "attachment-files"),
        changes,
        allowed_input_root=tmp_path,
    )
    return data, result, attachments, submittals, changes, actor, analysis, ingestion


def test_demo_builds_immutable_lineage_and_cited_extractions(attachment_demo):
    _, result, attachments, _, _, _, _, _ = attachment_demo
    items = attachments.list_attachments("project-a", result["package_id"])
    product = next(item for item in items if item.display_name == "switchboard-product-data.txt")
    assert product.revisions[0].active is False
    assert product.revisions[1].supersedes_attachment_revision_id == product.revisions[0].id
    extraction = attachments.get_extraction(
        "project-a", product.revisions[1].extraction_result_id or ""
    )
    assert extraction and extraction.extraction_status == ExtractionStatus.COMPLETE
    assert extraction.readability.status == ReadabilityStatus.READABLE
    assert extraction.identities[0].manufacturer == "Brunel Synthetic Electric"
    assert extraction.identities[0].model_number == "BSE-MSB-200"
    assert any(
        item.name == "short_circuit_rating" and item.value == "65"
        for item in extraction.technical_attributes
    )
    assert all(item.evidence.citation.chunk_id for item in extraction.technical_attributes)
    assert attachments.get_attachment("another-project", product.id) is None


def test_analysis_detects_conflicts_deviations_and_preserves_human_control(attachment_demo):
    _, result, attachments, _, _, actor, analysis, _ = attachment_demo
    revision_one = analysis.latest_evidence_set("project-a", result["package_id"], 1)
    evidence = analysis.latest_evidence_set("project-a", result["package_id"], 2)
    assert revision_one and revision_one.conflicts
    assert any(item.subject == "model_number" for item in revision_one.conflicts)
    assert revision_one.possible_deviations
    assert evidence and all(item.human_review_required for item in evidence.compliance_mappings)
    mapping = evidence.compliance_mappings[0]
    reviewed = analysis.review_mapping(
        "project-a",
        result["package_id"],
        mapping.requirement_id,
        ReviewerReference(id="reviewer", display_name="Reviewer"),
        actor,
        confirmation=HumanConfirmationStatus.MODIFIED,
        status=MatrixStatus.UNCLEAR,
        note="Conflicting model references require clarification.",
    )
    assert reviewed.confirmed_status == MatrixStatus.UNCLEAR
    assert reviewed.proposed_status == mapping.proposed_status
    assert reviewed.reviews[-1].reviewer.id == "reviewer"


def test_duplicate_unsupported_and_idempotent_ingestion(attachment_demo):
    data, result, _, _, _, actor, _, ingestion = attachment_demo
    product = (
        data
        / "synthetic-attachment-demo"
        / "project-a"
        / "revision-2"
        / "switchboard-product-data.txt"
    )
    duplicate = ingestion.ingest(
        "project-a",
        result["package_id"],
        product,
        actor,
        package_revision=2,
        attachment_id="att_duplicate",
        declared_type=AttachmentType.PRODUCT_DATA,
    )
    assert duplicate.duplicate.status == DuplicateStatus.EXACT_DUPLICATE
    repeated = ingestion.ingest(
        "project-a",
        result["package_id"],
        product,
        actor,
        package_revision=2,
        attachment_id="att_duplicate",
        declared_type=AttachmentType.PRODUCT_DATA,
    )
    assert repeated.revision.id == duplicate.revision.id
    assert "Idempotent" in repeated.warnings[0]
    unsupported = data / "synthetic-attachment-demo" / "project-a" / "manufacturer-certificate.docx"
    unsupported.write_bytes(b"synthetic metadata-only document")
    metadata = ingestion.ingest(
        "project-a",
        result["package_id"],
        unsupported,
        actor,
        package_revision=2,
        declared_type=AttachmentType.CERTIFICATE,
        role=AttachmentRole.CERTIFICATION,
    )
    assert (
        metadata.extraction
        and metadata.extraction.readability.status == ReadabilityStatus.UNSUPPORTED
    )
    assert metadata.extraction.readability.may_support_compliance_mapping is False


def test_pdf_partial_readability_classification_and_size_guard(attachment_demo):
    data, result, attachments, submittals, changes, actor, _, ingestion = attachment_demo
    source = data / "synthetic-attachment-demo" / "project-a" / "factory-test-report.pdf"
    pdf = canvas.Canvas(str(source))
    pdf.drawString(72, 720, "FACTORY TEST REPORT Model: BSE-MSB-200 Rating: 65 kA")
    pdf.showPage()
    pdf.showPage()
    pdf.save()
    ingested = ingestion.ingest(
        "project-a",
        result["package_id"],
        source,
        actor,
        package_revision=2,
        attachment_id="att_pdf_test",
        declared_type=AttachmentType.WARRANTY,
    )
    assert ingested.extraction
    assert ingested.extraction.readability.status == ReadabilityStatus.PARTIALLY_READABLE
    assert ingested.extraction.readability.pages_unavailable
    assert ingested.extraction.classification.inferred_type == AttachmentType.TEST_REPORT
    assert ingested.extraction.classification.disagreement
    assert all(
        item.citation.page_number == 1 for item in ingested.extraction.identities[0].evidence
    )
    limited = AttachmentIngestionService(
        attachments,
        submittals,
        JsonDocumentRepository(data / "ingested"),
        LocalAttachmentFileStore(data / "attachment-files"),
        changes,
        maximum_file_size=2,
        allowed_input_root=data.parent,
    )
    with pytest.raises(AttachmentSecurityError, match="file-size"):
        limited.ingest("project-a", result["package_id"], source, actor)


def test_security_boundaries_and_immutable_records(attachment_demo, tmp_path: Path):
    _, result, attachments, _, _, actor, _, ingestion = attachment_demo
    outside = tmp_path.parent / "outside-attachment.txt"
    outside.write_text("PRODUCT DATA", encoding="utf-8")
    try:
        with pytest.raises(AttachmentSecurityError):
            ingestion.ingest("project-a", result["package_id"], outside, actor)
    finally:
        outside.unlink(missing_ok=True)
    evidence = attachments.list_evidence_sets("project-a", result["package_id"])[0]
    changed = evidence.model_copy(
        update={"human_review_complete": not evidence.human_review_complete}
    )
    with pytest.raises(SubmittalConcurrencyError):
        attachments.save_evidence_set(changed)


def test_corrupt_records_are_skipped_without_cross_project_leakage(attachment_demo):
    data, _, attachments, _, _, _, _, _ = attachment_demo
    directory = data / "submittal-attachment-intelligence" / "attachments"
    (directory / "att_corrupt.json").write_text("{broken", encoding="utf-8")
    assert attachments.list_attachments("project-a")
    assert attachments.list_attachments("project-b") == ()


def test_revision_comparison_is_deterministic_and_cited(attachment_demo):
    _, result, attachments, submittals, _, actor, _, _ = attachment_demo
    comparison = PackageRevisionComparisonService(attachments, submittals).compare(
        "project-a", result["package_id"], 1, 2, actor
    )
    assert comparison.re_review_required
    assert {item.change_type for item in comparison.changes} >= {
        PackageChangeType.ATTACHMENT_MODIFIED,
        PackageChangeType.MODEL_CHANGED,
        PackageChangeType.RATING_CHANGED,
    }
    assert any(item.old_evidence and item.new_evidence for item in comparison.changes)
    repeated = PackageRevisionComparisonService(attachments, submittals).compare(
        "project-a", result["package_id"], 1, 2, actor
    )
    assert repeated.id == comparison.id


def test_search_and_qa_are_project_scoped_and_use_current_evidence(attachment_demo):
    _, result, attachments, submittals, _, _, _, _ = attachment_demo
    search = AttachmentSearchService(attachments).search(
        "project-a", "BSE-MSB-200 85 kA", package_id=result["package_id"]
    )
    assert search and search[0].excerpts
    assert AttachmentSearchService(attachments).search("project-b", "BSE-MSB-200") == ()
    answer = AttachmentQuestionService(attachments, submittals).answer(
        "project-a", "What model and rating were submitted?", package_id=result["package_id"]
    )
    assert answer.sufficient and answer.attachment_citations
    assert "BSE-MSB-200" in answer.answer
    assert all(item.package_revision == 2 for item in answer.attachment_citations)
    unsupported = AttachmentQuestionService(attachments, submittals).answer(
        "project-a", "Who approved professional design compliance?", package_id=result["package_id"]
    )
    assert not unsupported.sufficient
    assert "does not establish" in unsupported.answer


def test_report_has_citations_and_no_internal_file_paths(attachment_demo, tmp_path: Path):
    _, result, attachments, _, _, _, analysis, _ = attachment_demo
    renderer = AttachmentIntelligenceRenderer(attachments, analysis)
    content = renderer.markdown("project-a", result["package_id"])
    assert "Specification citation" in content
    assert "Attachment citation" in content
    assert "does not determine professional design compliance" in content
    assert "storage_reference" not in content and str(tmp_path) not in content


def test_api_openapi_routes_and_safe_serialization(attachment_demo, monkeypatch):
    data, result, _, _, _, _, _, _ = attachment_demo
    monkeypatch.setenv("BRUNEL_DATA_DIRECTORY", str(data))
    get_settings.cache_clear()
    client = TestClient(app)
    package_id = result["package_id"]
    assert (
        client.get(
            f"/projects/project-a/submittal-packages/{package_id}/attachment-summary"
        ).status_code
        == 200
    )
    response = client.get(
        "/projects/project-a/submittal-attachments/search",
        params={"q": "BSE-MSB-200", "package_id": package_id},
    )
    assert response.status_code == 200 and response.json()
    listed = client.get(f"/projects/project-a/submittal-packages/{package_id}/attachments")
    assert listed.status_code == 200
    assert "storage_reference" not in listed.text and str(data) not in listed.text
    schema = client.get("/openapi.json")
    assert schema.status_code == 200
    assert (
        "/projects/{project_id}/submittal-packages/{package_id}/attachments"
        in schema.json()["paths"]
    )
    get_settings.cache_clear()


def test_cli_commands_work_without_model_or_external_notification(
    attachment_demo, monkeypatch, capsys
):
    data, result, _, _, _, _, _, _ = attachment_demo
    monkeypatch.setenv("BRUNEL_DATA_DIRECTORY", str(data))
    get_settings.cache_clear()
    assert (
        main(
            [
                "submittal-attachment-search",
                "--project-id",
                "project-a",
                "--package-id",
                result["package_id"],
                "--query",
                "BSE-MSB-200",
            ]
        )
        == 0
    )
    assert "BSE-MSB-200" in capsys.readouterr().out
    assert get_settings().submittal.model_assistance_enabled is False
    assert get_settings().models.provider == "disabled"
    get_settings.cache_clear()


def test_changed_evidence_after_review_marks_stale_and_queues_local_notification(
    attachment_demo,
):
    data, result, attachments, submittals, changes, actor, _, ingestion = attachment_demo
    register = submittals.list_register("project-a")[0]
    reviewer = ReviewerReference(id="assigned-reviewer", display_name="Assigned Reviewer")
    submittals.save_register(
        register.model_copy(
            update={
                "version": register.version + 1,
                "internal_reviewer": reviewer,
            }
        ),
        expected_version=register.version,
    )
    package = submittals.get_package("project-a", result["package_id"])
    assert package
    submittals.save_package(
        package.model_copy(
            update={
                "version": package.version + 1,
                "internal_review_status": PackageReviewStatus.APPROVED_FOR_SUBMISSION,
            }
        ),
        expected_version=package.version,
    )
    supplemental = (
        data / "synthetic-attachment-demo" / "project-a" / "revision-2" / "supplemental-letter.txt"
    )
    supplemental.write_text(
        "LETTER\nSpecification Section 26 24 13\nSupplemental clarification only.",
        encoding="utf-8",
    )
    ingestion.ingest(
        "project-a",
        result["package_id"],
        supplemental,
        actor,
        package_revision=2,
        declared_type=AttachmentType.LETTER,
        role=AttachmentRole.SUPPLEMENTAL,
    )
    updated = submittals.get_package("project-a", result["package_id"])
    assert updated and updated.internal_review_status == PackageReviewStatus.DRAFT
    assert updated.staleness_assessments
    staleness = attachments.list_staleness("project-a", result["package_id"])
    assert staleness[-1].status == PackageAttachmentStalenessStatus.RE_REVIEW_REQUIRED
    queued = changes.list_notifications("project-a")
    assert queued and queued[-1].recipient.id == reviewer.id
    assert "excerpt" not in str(queued[-1].payload).casefold()


def test_staleness_acknowledgment_is_audited(attachment_demo):
    _, result, attachments, submittals, _, actor, analysis, _ = attachment_demo
    assessment = analysis.check_staleness("project-a", result["package_id"], actor)
    assert assessment.status in {
        PackageAttachmentStalenessStatus.CURRENT,
        PackageAttachmentStalenessStatus.POTENTIALLY_STALE,
    }
    acknowledged = analysis.acknowledge_staleness("project-a", result["package_id"], actor)
    assert acknowledged.acknowledged_by == actor
    assert any(
        event.event_type == "attachment_staleness_acknowledged"
        for event in submittals.audit("project-a", result["package_id"])
    )
    assert attachments.list_staleness("project-a", result["package_id"])
