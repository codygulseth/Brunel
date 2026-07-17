"""Runnable deterministic electrical submittal scenario for local validation."""

from datetime import UTC, date, datetime
from pathlib import Path

from change_workflow.models import ActorReference, ReviewerReference
from change_workflow.repository import JsonChangeWorkflowRepository
from document_processing import DocumentIngestionService, DocumentType
from rfi.repository import JsonRFIRepository
from rfi.service import RFIService
from storage import JsonDocumentRepository
from submittal.extraction import SubmittalRequirementExtractionService
from submittal.models import (
    AttachmentMetadata,
    InternalReviewDecision,
    OfficialDisposition,
    RequirementReviewDecision,
    StalenessStatus,
    SubmittalType,
)
from submittal.qa import SubmittalQuestionService
from submittal.reporting import SubmittalRenderer
from submittal.repository import JsonSubmittalRepository
from submittal.service import SubmittalService


def _attachments(types: tuple[SubmittalType, ...]) -> tuple[AttachmentMetadata, ...]:
    return tuple(
        AttachmentMetadata(
            id=f"demo-{kind.value}",
            filename=f"electrical-{kind.value}.pdf",
            document_type=kind,
            storage_reference=f"synthetic://{kind.value}",
            signed_or_stamped=kind == SubmittalType.CALCULATION,
        )
        for kind in types
    )


def run_synthetic_submittal_demo(data_root: Path, project_id: str) -> dict[str, str | int]:
    """Execute extraction through approved package without network or model calls."""
    source_root = data_root / "demo-inputs"
    source_root.mkdir(parents=True, exist_ok=True)
    spec_path = source_root / "section-26-24-13.txt"
    spec_path.write_text(
        "SECTION 26 24 13 SWITCHBOARDS\n"
        "1.5.A Submit product data for switchboards.\n"
        "1.5.B Submit shop drawings showing dimensions and connections.\n"
        "1.5.C Submit short-circuit calculations signed by the engineer.\n"
        "1.5.D Submit coordination drawings for electrical rooms.\n"
        "1.5.E Submit factory test reports before shipment.\n",
        encoding="utf-8",
    )
    documents = JsonDocumentRepository(data_root / "ingested")
    repository = JsonSubmittalRepository(data_root / "submittals")
    changes = JsonChangeWorkflowRepository(data_root / "change-workflow")
    rfis = JsonRFIRepository(data_root / "rfi")
    ingested = DocumentIngestionService(documents).ingest(
        project_id=project_id,
        file_path=spec_path,
        document_type=DocumentType.SPECIFICATION,
        document_family_id="electrical-switchboards",
        title="Section 26 24 13 Switchboards",
        discipline="electrical",
        specification_section="26 24 13",
    )
    extraction = SubmittalRequirementExtractionService(documents, repository).extract(project_id)
    actor = ActorReference(id="electrical-pm", display_name="Electrical PM")
    reviewer = ReviewerReference(id="project-manager", display_name="Project Manager")
    service = SubmittalService(repository, changes, rfis)
    register_ids = []
    for candidate_id in extraction.candidate_ids:
        result = service.review_candidate(
            project_id,
            candidate_id,
            RequirementReviewDecision.ACCEPT,
            actor,
            explanation="Verified against the cited specification paragraph.",
            responsible_subcontractor="Electrical Subcontractor",
        )
        if result.register_item_id:
            register_ids.append(result.register_item_id)
    if not register_ids:
        raise RuntimeError("Synthetic extraction produced no register items")
    rfi = RFIService(rfis).create(
        project_id=project_id,
        subject="Switchboard coordination dimensions",
        question="Confirm final electrical-room coordination dimensions.",
        actor=actor,
    )
    service.link_rfi(project_id, register_ids[0], rfi.id, actor)
    for item_id in register_ids:
        service.assign(project_id, item_id, actor, reviewer=reviewer)
        service.update_procurement(
            project_id,
            item_id,
            actor,
            required_on_site_date=date(2027, 6, 1),
            fabrication_days=168,
            shipping_days=14,
            processing_days=7,
            review_days=14,
            resubmittal_days=14,
            buffer_days=7,
        )
    initial_types = (SubmittalType.PRODUCT_DATA, SubmittalType.SHOP_DRAWING)
    package = service.create_package(
        project_id,
        register_ids[0],
        actor,
        register_item_ids=tuple(register_ids[1:]),
        title="Switchboard Package",
        submitter="Electrical Subcontractor",
        included_types=initial_types,
        attachments=_attachments(initial_types),
        related_rfi_ids=(rfi.id,),
    )
    blocked = service.review_completeness(project_id, package.id, actor)
    all_types = (
        SubmittalType.PRODUCT_DATA,
        SubmittalType.SHOP_DRAWING,
        SubmittalType.CALCULATION,
        SubmittalType.COORDINATION_DRAWING,
        SubmittalType.TEST_REPORT,
    )
    package = service.revise_package(
        project_id,
        package.id,
        actor,
        change_summary="Added all cited required documentation.",
        included_types=all_types,
        attachments=_attachments(all_types),
        deviations=("No deviations declared; pending design-team review.",),
    )
    complete = service.review_completeness(project_id, package.id, actor)
    service.submit_internal_review(project_id, package.id, reviewer, actor)
    service.internal_review(
        project_id,
        package.id,
        InternalReviewDecision.APPROVED_FOR_SUBMISSION,
        reviewer,
        actor,
    )
    service.issue_package(project_id, package.id, actor)
    first_evidence = service.get_register(project_id, register_ids[0]).requirements[0].evidence
    service.record_response(
        project_id,
        package.id,
        actor,
        responding_organization="Electrical Engineer",
        disposition=OfficialDisposition.REVISE_AND_RESUBMIT,
        original_disposition_text="Revise and resubmit with confirmed clearances.",
        required_corrections=("Confirm switchboard working clearances.",),
        evidence=first_evidence,
    )
    package = service.resubmit(
        project_id,
        package.id,
        actor,
        change_summary="Confirmed working clearances and updated coordination drawing.",
    )
    service.review_completeness(project_id, package.id, actor)
    service.submit_internal_review(project_id, package.id, reviewer, actor)
    service.internal_review(
        project_id,
        package.id,
        InternalReviewDecision.APPROVED_FOR_SUBMISSION,
        reviewer,
        actor,
    )
    service.issue_package(project_id, package.id, actor)
    service.record_response(
        project_id,
        package.id,
        actor,
        responding_organization="Electrical Engineer",
        disposition=OfficialDisposition.APPROVED_AS_NOTED,
        original_disposition_text="Approved as noted.",
        required_corrections=("Coordinate final conduit entries.",),
        evidence=first_evidence,
    )
    analysis = service.analyze_response(project_id, package.id, actor)
    service.mark_stale(
        project_id,
        package.id,
        actor,
        reasons=("RFI coordination was reviewed in the current package revision.",),
        source_references=(rfi.number,),
        status=StalenessStatus.CURRENT,
    )
    for item_id in register_ids:
        service.confirm_procurement_release(
            project_id, item_id, actor, corrections_incorporated=True
        )
    item = service.get_register(project_id, register_ids[0])
    report = data_root / "demo-reports" / f"{item.register_number}.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        SubmittalRenderer(repository).markdown(
            item, (service.get_package(project_id, package.id),)
        ),
        encoding="utf-8",
    )
    answer = SubmittalQuestionService(repository).answer(
        project_id, f"Is {item.register_number} approved and released for procurement?"
    )
    return {
        "project_id": project_id,
        "document_id": ingested.document.document_id,
        "candidate_count": len(extraction.candidate_ids),
        "register_count": len(register_ids),
        "package_id": package.id,
        "package_revision_count": service.get_package(project_id, package.id).current_revision,
        "initial_completeness": blocked.status.value,
        "final_completeness": complete.status.value,
        "official_disposition": analysis.disposition.value if analysis.disposition else "unknown",
        "rfi_id": rfi.id,
        "report": str(report),
        "qa": answer.answer,
        "audit_event_count": len(repository.audit(project_id)),
        "completed_at": datetime.now(UTC).isoformat(),
    }
