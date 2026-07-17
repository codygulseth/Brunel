"""Synthetic end-to-end demonstration for attachment content intelligence."""

from pathlib import Path
from typing import Any

from change_workflow.models import ActorReference, ReviewerReference
from change_workflow.repository import JsonChangeWorkflowRepository
from document_processing import DocumentIngestionService, DocumentType
from rfi.repository import JsonRFIRepository
from storage import JsonDocumentRepository
from submittal.attachment_intelligence import (
    AttachmentIngestionService,
    LocalAttachmentFileStore,
    PackageAttachmentAnalysisService,
    PackageRevisionComparisonService,
)
from submittal.attachment_models import AttachmentRole, AttachmentType, HumanConfirmationStatus
from submittal.attachment_qa import AttachmentQuestionService
from submittal.attachment_reporting import AttachmentIntelligenceRenderer
from submittal.attachment_repository import JsonAttachmentIntelligenceRepository
from submittal.extraction import SubmittalRequirementExtractionService
from submittal.models import MatrixStatus, RequirementReviewDecision, SubmittalType
from submittal.repository import JsonSubmittalRepository
from submittal.service import SubmittalService


def run_synthetic_attachment_demo(data_root: Path, project_id: str) -> dict[str, Any]:
    """Create cited requirements, two package evidence sets, review, compare, Q&A, and export."""
    data_root = data_root.expanduser().resolve()
    inputs = data_root / "synthetic-attachment-demo" / project_id
    inputs.mkdir(parents=True, exist_ok=True)
    spec = inputs / "section-26-24-13.txt"
    product_v1 = inputs / "switchboard-product-data.txt"
    duplicate_v1 = inputs / "switchboard-catalog-copy.txt"
    shop_v1 = inputs / "switchboard-shop-drawing.txt"
    warranty_v1 = inputs / "switchboard-warranty.txt"
    installation_v1 = inputs / "switchboard-installation-instructions.txt"
    cover_v1 = inputs / "switchboard-cover-sheet.txt"
    product_v2 = inputs / "revision-2" / "switchboard-product-data.txt"
    product_v2.parent.mkdir(parents=True, exist_ok=True)
    shop_v2 = inputs / "revision-2" / "switchboard-shop-drawing.txt"
    calculation_v2 = inputs / "revision-2" / "switchboard-calculation.txt"
    test_v2 = inputs / "revision-2" / "switchboard-factory-test-report.txt"
    warranty_v2 = inputs / "revision-2" / "switchboard-warranty.txt"
    installation_v2 = inputs / "revision-2" / "switchboard-installation-instructions.txt"
    spec.write_text(
        "SECTION 26 24 13 SWITCHBOARDS\n"
        "1.5.A Submit product data for switchboards rated NEMA 3R, 480Y/277 V, 65 kA, with copper bus.\n"
        "1.5.B Submit shop drawings identifying the selected model and 52 in x 30 in dimensions.\n"
        "1.5.C Submit short-circuit calculations identifying the selected equipment model.\n"
        "1.5.D Submit factory test reports for the selected model and rating.\n"
        "1.5.E Submit manufacturer's instructions for installation.\n"
        "1.5.F Submit a five-year warranty.\n",
        encoding="utf-8",
    )
    product_v1.write_text(
        "PRODUCT DATA\nManufacturer: Brunel Synthetic Electric\n"
        "Product Name: Main Distribution Switchboard\nModel: BSE-MSB-100\n"
        "Specification Section 26 24 13\nEquipment Tag MSB-1\n"
        "Rating: 480Y/277 V, 42 kA, NEMA 1. Material: painted steel bus.\n",
        encoding="utf-8",
    )
    duplicate_v1.write_text(product_v1.read_text(encoding="utf-8"), encoding="utf-8")
    shop_v1.write_text(
        "SHOP DRAWING\nSpecification Section 26 24 13\n"
        "Manufacturer: Brunel Synthetic Electric\nProduct Name: Main Distribution Switchboard\n"
        "Model: BSE-MSB-999\nEquipment Tag MSB-1\nOverall dimensions: 48 in x 30 in.\n",
        encoding="utf-8",
    )
    warranty_v1.write_text(
        "WARRANTY\nManufacturer: Brunel Synthetic Electric\nProduct: Main Distribution Switchboard\n"
        "Model: BSE-MSB-100\nSpecification Section 26 24 13\nOne-year warranty.\n",
        encoding="utf-8",
    )
    installation_v1.write_text(
        "MANUFACTURER INSTALLATION INSTRUCTIONS\nSpecification Section 26 24 13\n"
        "Manufacturer: Brunel Synthetic Electric\nProduct: Main Distribution Switchboard\n"
        "Model: BSE-MSB-100\nEquipment Tag MSB-1\n",
        encoding="utf-8",
    )
    cover_v1.write_text(
        "SUBMITTAL COVER SHEET\nSpecification Section 26 24 13\n"
        "Manufacturer: Brunel Synthetic Electric\nProduct: Main Distribution Switchboard\n"
        "Model: BSE-MSB-100\nRevision 1. No deviations declared.\n",
        encoding="utf-8",
    )
    product_v2.write_text(
        "PRODUCT DATA REVISION 2\nManufacturer: Brunel Synthetic Electric\n"
        "Product Name: Main Distribution Switchboard\nModel: BSE-MSB-200\n"
        "Specification Section 26 24 13\nEquipment Tag MSB-1\n"
        "Rating: 480Y/277 V, 65 kA, NEMA 3R. Copper bus.\n",
        encoding="utf-8",
    )
    shop_v2.write_text(
        "SHOP DRAWING REVISION 2\nSpecification Section 26 24 13\n"
        "Manufacturer: Brunel Synthetic Electric\nProduct: Main Distribution Switchboard\n"
        "Model: BSE-MSB-200\nEquipment Tag MSB-1\nOverall dimensions: 52 in x 30 in.\n",
        encoding="utf-8",
    )
    calculation_v2.write_text(
        "SHORT-CIRCUIT CALCULATION\nSpecification Section 26 24 13\n"
        "Selected Model: BSE-MSB-200\nEquipment Tag MSB-1\n"
        "Equipment short-circuit rating: 65 kA. Study confirms adequate rating.\n",
        encoding="utf-8",
    )
    test_v2.write_text(
        "FACTORY TEST REPORT\nSpecification Section 26 24 13\n"
        "Manufacturer: Brunel Synthetic Electric\nProduct: Main Distribution Switchboard\n"
        "Model: BSE-MSB-200\nEquipment Tag MSB-1\nTested rating: 65 kA.\n",
        encoding="utf-8",
    )
    warranty_v2.write_text(
        "WARRANTY REVISION 2\nManufacturer: Brunel Synthetic Electric\n"
        "Product: Main Distribution Switchboard\nModel: BSE-MSB-200\n"
        "Specification Section 26 24 13\nFive-year warranty.\n",
        encoding="utf-8",
    )
    installation_v2.write_text(
        "MANUFACTURER INSTALLATION INSTRUCTIONS\nSpecification Section 26 24 13\n"
        "Manufacturer: Brunel Synthetic Electric\nProduct: Main Distribution Switchboard\n"
        "Model: BSE-MSB-200\nEquipment Tag MSB-1\n",
        encoding="utf-8",
    )

    documents = JsonDocumentRepository(data_root / "ingested")
    submittals = JsonSubmittalRepository(data_root / "submittals")
    attachments = JsonAttachmentIntelligenceRepository(
        data_root / "submittal-attachment-intelligence"
    )
    changes = JsonChangeWorkflowRepository(data_root / "change-workflow")
    actor = ActorReference(id="demo-pm", display_name="Synthetic Project Manager")
    service = SubmittalService(submittals, changes, JsonRFIRepository(data_root / "rfi"))
    existing_packages = submittals.list_packages(project_id)
    if existing_packages:
        package = existing_packages[0]
        analysis = PackageAttachmentAnalysisService(attachments, submittals, changes)
        evidence = analysis.latest_evidence_set(project_id, package.id)
        return {
            "project_id": project_id,
            "package_id": package.id,
            "package_number": package.package_number,
            "current_revision": package.current_revision,
            "evidence_set_id": evidence.id if evidence else None,
            "message": "Existing synthetic demonstration reused.",
        }

    ingested = DocumentIngestionService(documents).ingest(
        project_id=project_id,
        file_path=spec,
        document_type=DocumentType.SPECIFICATION,
        title="Synthetic Switchboard Specification",
        specification_section="26 24 13",
    )
    extracted = SubmittalRequirementExtractionService(documents, submittals).extract(
        project_id, document_ids=(ingested.document.document_id,)
    )
    register_ids: list[str] = []
    for candidate_id in extracted.candidate_ids:
        result = service.review_candidate(
            project_id,
            candidate_id,
            RequirementReviewDecision.ACCEPT,
            actor,
            explanation="Synthetic cited requirement verified for demonstration.",
        )
        if result.register_item_id:
            register_ids.append(result.register_item_id)
    if not register_ids:
        raise RuntimeError("Synthetic specification did not produce requirements")
    package = service.create_package(
        project_id,
        register_ids[0],
        actor,
        register_item_ids=tuple(register_ids[1:]),
        submitter="Synthetic Electrical Subcontractor",
        included_types=(
            SubmittalType.PRODUCT_DATA,
            SubmittalType.SHOP_DRAWING,
            SubmittalType.CALCULATION,
            SubmittalType.TEST_REPORT,
            SubmittalType.INSTALLATION_INSTRUCTION,
            SubmittalType.WARRANTY,
        ),
        deviations=("No deviations declared by submitter.",),
    )
    ingestion = AttachmentIngestionService(
        attachments,
        submittals,
        documents,
        LocalAttachmentFileStore(data_root / "attachment-files"),
        changes,
        allowed_input_root=data_root.parent,
    )
    first = ingestion.ingest(
        project_id,
        package.id,
        product_v1,
        actor,
        declared_type=AttachmentType.PRODUCT_DATA,
        role=AttachmentRole.MANUFACTURER_DATA,
        revision_label="1",
    )
    duplicate = ingestion.ingest(
        project_id,
        package.id,
        duplicate_v1,
        actor,
        declared_type=AttachmentType.PRODUCT_DATA,
        role=AttachmentRole.MANUFACTURER_DATA,
        revision_label="1",
    )
    shop_first = ingestion.ingest(
        project_id,
        package.id,
        shop_v1,
        actor,
        declared_type=AttachmentType.SHOP_DRAWING,
        role=AttachmentRole.DESIGN_DOCUMENT,
        revision_label="1",
    )
    warranty_first = ingestion.ingest(
        project_id,
        package.id,
        warranty_v1,
        actor,
        declared_type=AttachmentType.WARRANTY,
        role=AttachmentRole.REQUIRED_DOCUMENT,
        revision_label="1",
    )
    installation_first = ingestion.ingest(
        project_id,
        package.id,
        installation_v1,
        actor,
        declared_type=AttachmentType.INSTALLATION_INSTRUCTION,
        role=AttachmentRole.REQUIRED_DOCUMENT,
        revision_label="1",
    )
    ingestion.ingest(
        project_id,
        package.id,
        cover_v1,
        actor,
        declared_type=AttachmentType.COVER_SHEET,
        role=AttachmentRole.SUPPORTING_DOCUMENT,
        revision_label="1",
    )
    analysis = PackageAttachmentAnalysisService(attachments, submittals, changes)
    evidence_v1 = analysis.analyze_package(project_id, package.id, actor)
    confirmed = None
    reviewer = ReviewerReference(id="demo-reviewer", display_name="Synthetic Reviewer")
    for mapping in evidence_v1.compliance_mappings:
        if mapping.missing_evidence and mapping.proposed_status == MatrixStatus.NOT_ADDRESSED:
            confirmation = HumanConfirmationStatus.MODIFIED
            status = MatrixStatus.NOT_ADDRESSED
            note = "Required document is absent from Revision 1."
        elif mapping.conflicting_evidence_ids:
            confirmation = HumanConfirmationStatus.NEEDS_INFORMATION
            status = None
            note = "Conflicting product identity requires clarification."
        elif confirmed is None:
            confirmation = HumanConfirmationStatus.CONFIRMED
            status = None
            note = "Cited evidence checked for synthetic demonstration."
        else:
            confirmation = HumanConfirmationStatus.REJECTED
            status = None
            note = "Automated mapping rejected for synthetic review exercise."
        reviewed = analysis.review_mapping(
            project_id,
            package.id,
            mapping.requirement_id,
            reviewer,
            actor,
            confirmation=confirmation,
            status=status,
            note=note,
        )
        if confirmation == HumanConfirmationStatus.CONFIRMED:
            confirmed = reviewed
    service.revise_package(
        project_id,
        package.id,
        actor,
        change_summary="Synthetic revised product selection.",
    )
    second = ingestion.ingest(
        project_id,
        package.id,
        product_v2,
        actor,
        package_revision=2,
        attachment_id=first.attachment.id,
        declared_type=AttachmentType.PRODUCT_DATA,
        role=AttachmentRole.MANUFACTURER_DATA,
        revision_label="2",
        supersedes_attachment_revision_id=first.revision.id,
    )
    ingestion.ingest(
        project_id,
        package.id,
        shop_v2,
        actor,
        package_revision=2,
        attachment_id=shop_first.attachment.id,
        declared_type=AttachmentType.SHOP_DRAWING,
        role=AttachmentRole.DESIGN_DOCUMENT,
        revision_label="2",
        supersedes_attachment_revision_id=shop_first.revision.id,
    )
    ingestion.ingest(
        project_id,
        package.id,
        calculation_v2,
        actor,
        package_revision=2,
        declared_type=AttachmentType.CALCULATION,
        role=AttachmentRole.CALCULATION_PACKAGE,
        revision_label="2",
    )
    ingestion.ingest(
        project_id,
        package.id,
        test_v2,
        actor,
        package_revision=2,
        declared_type=AttachmentType.TEST_REPORT,
        role=AttachmentRole.REQUIRED_DOCUMENT,
        revision_label="2",
    )
    ingestion.ingest(
        project_id,
        package.id,
        warranty_v2,
        actor,
        package_revision=2,
        attachment_id=warranty_first.attachment.id,
        declared_type=AttachmentType.WARRANTY,
        role=AttachmentRole.REQUIRED_DOCUMENT,
        revision_label="2",
        supersedes_attachment_revision_id=warranty_first.revision.id,
    )
    ingestion.ingest(
        project_id,
        package.id,
        installation_v2,
        actor,
        package_revision=2,
        attachment_id=installation_first.attachment.id,
        declared_type=AttachmentType.INSTALLATION_INSTRUCTION,
        role=AttachmentRole.REQUIRED_DOCUMENT,
        revision_label="2",
        supersedes_attachment_revision_id=installation_first.revision.id,
    )
    evidence_v2 = analysis.analyze_package(project_id, package.id, actor)
    comparison = PackageRevisionComparisonService(attachments, submittals).compare(
        project_id, package.id, 1, 2, actor
    )
    answer = AttachmentQuestionService(attachments, submittals).answer(
        project_id, "What model and short-circuit rating were submitted?", package_id=package.id
    )
    report = AttachmentIntelligenceRenderer(attachments, analysis).export(
        project_id,
        package.id,
        data_root / "synthetic-attachment-demo" / f"{project_id}-attachment-report.md",
    )
    return {
        "project_id": project_id,
        "package_id": package.id,
        "package_number": package.package_number,
        "requirement_count": len(register_ids),
        "specification_document_id": ingested.document.document_id,
        "first_attachment_revision_id": first.revision.id,
        "second_attachment_revision_id": second.revision.id,
        "evidence_set_v1": evidence_v1.id,
        "evidence_set_v2": evidence_v2.id,
        "confirmed_mapping_id": confirmed.id if confirmed else None,
        "revision_1_duplicate_status": duplicate.duplicate.status.value,
        "revision_1_missing_types": [
            item.missing_type.value for item in evidence_v1.missing_attachments
        ],
        "revision_1_conflicts": [item.subject for item in evidence_v1.conflicts],
        "revision_1_possible_deviations": [
            item.attribute_name for item in evidence_v1.possible_deviations
        ],
        "revision_2_missing_types": [
            item.missing_type.value for item in evidence_v2.missing_attachments
        ],
        "revision_2_conflicts": [item.subject for item in evidence_v2.conflicts],
        "comparison_id": comparison.id,
        "comparison_summary": comparison.summary,
        "question_answer": answer.model_dump(mode="json"),
        "report": str(report),
        "external_model_calls": 0,
        "external_notifications_sent": 0,
    }
