"""Runnable synthetic electrical RFI scenario for local validation."""

from datetime import UTC, date, datetime
from pathlib import Path

from change_workflow.models import (
    ActorReference,
    ChangeStatus,
    ImpactCertainty,
    ReviewerReference,
)
from change_workflow.repository import JsonChangeWorkflowRepository
from change_workflow.service import ProjectChangeService
from document_processing import DocumentIngestionService, DocumentType
from revision_intelligence.models import ComparisonRequest
from revision_intelligence.repository import JsonComparisonRepository
from revision_intelligence.service import RevisionComparisonService
from rfi.models import RFIImpactType, RFIReviewDecision, RFIStatus
from rfi.qa import RFIQuestionService
from rfi.repository import JsonRFIRepository
from rfi.reporting import RFIRenderer
from rfi.service import RFIService
from storage import JsonDocumentRepository


def run_synthetic_rfi_demo(data_root: Path, project_id: str) -> dict[str, str | int]:
    """Execute the documented scenario without network or model calls."""
    source_root = data_root / "demo-inputs"
    source_root.mkdir(parents=True, exist_ok=True)
    old_path = source_root / "electrical-r1.txt"
    new_path = source_root / "electrical-r2.txt"
    old_path.write_text(
        "Switchgear is indoor. Factory environmental controls not required.", encoding="utf-8"
    )
    new_path.write_text(
        "Switchgear is outdoor, NEMA 3R. Coordinate environmental controls. Lead time may affect schedule.",
        encoding="utf-8",
    )
    documents = JsonDocumentRepository(data_root / "ingested")
    comparisons = JsonComparisonRepository(data_root / "revision-intelligence")
    changes = JsonChangeWorkflowRepository(data_root / "change-workflow")
    rfis = JsonRFIRepository(data_root / "rfi")
    ingestion = DocumentIngestionService(documents)
    old = ingestion.ingest(
        file_path=old_path,
        project_id=project_id,
        document_type=DocumentType.SPECIFICATION,
        document_family_id="synthetic-electrical-spec",
        title="Synthetic Electrical Specification",
        revision="1",
        revision_sequence=1,
    )
    new = ingestion.ingest(
        file_path=new_path,
        revision="2",
        revision_sequence=2,
        supersedes_document_id=old.document.document_id,
        project_id=project_id,
        document_type=DocumentType.SPECIFICATION,
        document_family_id="synthetic-electrical-spec",
        title="Synthetic Electrical Specification",
    )
    comparison = RevisionComparisonService(documents, comparisons).compare(
        ComparisonRequest(
            project_id=project_id,
            old_document_id=old.document.document_id,
            new_document_id=new.document.document_id,
        )
    )
    actor = ActorReference(id="electrical-pm", display_name="Electrical PM")
    reviewer = ReviewerReference(id="project-manager", display_name="Project Manager")
    change_service = ProjectChangeService(changes)
    register = change_service.generate_register(comparison, actor)
    change_id = register.change_ids[0]
    service = RFIService(rfis, changes, documents=documents)
    item = service.draft_from_change(
        project_id,
        change_id,
        actor,
        instructions=(
            "Please confirm the required enclosure classification, installation location, "
            "and whether environmental controls are required."
        ),
        responsible_party="Electrical Engineer",
        required_date=date(2026, 8, 15),
    ).rfi
    service.assign_reviewer(project_id, item.id, reviewer, actor)
    service.transition(project_id, item.id, RFIStatus.PENDING_INTERNAL_REVIEW, actor)
    service.review(
        project_id,
        item.id,
        RFIReviewDecision.REVISIONS_REQUIRED,
        reviewer,
        actor,
        "Make the three requested confirmations explicit.",
    )
    service.revise(
        project_id,
        item.id,
        actor,
        question=(
            "Please confirm: (1) NEMA enclosure classification, (2) indoor or outdoor "
            "installation, and (3) required environmental controls."
        ),
        summary="Addressed internal review comment",
    )
    service.transition(project_id, item.id, RFIStatus.PENDING_INTERNAL_REVIEW, actor)
    service.review(project_id, item.id, RFIReviewDecision.APPROVED, reviewer, actor)
    service.transition(project_id, item.id, RFIStatus.ISSUED, actor)
    service.record_response(
        project_id,
        item.id,
        actor,
        text=(
            "Provide NEMA 3R switchgear at the outdoor location. Coordinate environmental "
            "controls. Procurement lead time may affect schedule."
        ),
        responding_party="Electrical Engineer",
    )
    service.add_impact(
        project_id,
        item.id,
        actor,
        impact_type=RFIImpactType.PROCUREMENT,
        certainty=ImpactCertainty.POSSIBLE,
        description="Procurement action may be required; human review pending.",
    )
    service.add_impact(
        project_id,
        item.id,
        actor,
        impact_type=RFIImpactType.SCHEDULE,
        certainty=ImpactCertainty.POSSIBLE,
        description="Schedule exposure is possible; no duration is confirmed.",
    )
    service.transition(project_id, item.id, RFIStatus.ANSWERED, actor)
    change_service.assign(project_id, change_id, reviewer, actor)
    change_service.transition(project_id, change_id, ChangeStatus.UNDER_REVIEW, actor)
    change_service.transition(project_id, change_id, ChangeStatus.ACCEPTED, actor)
    change_service.transition(
        project_id,
        change_id,
        ChangeStatus.RESOLVED,
        actor,
        resolution="Engineer direction recorded in the official RFI response.",
    )
    closed = service.transition(
        project_id,
        item.id,
        RFIStatus.CLOSED,
        actor,
        resolution="NEMA 3R outdoor installation direction coordinated.",
    )
    report = data_root / "demo-reports" / f"{closed.number}.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(RFIRenderer().markdown(closed), encoding="utf-8")
    answer = RFIQuestionService(rfis).answer(project_id, f"Why was {closed.number} created?")
    return {
        "project_id": project_id,
        "comparison_id": comparison.id,
        "change_id": change_id,
        "rfi_id": closed.id,
        "rfi_number": closed.number,
        "status": closed.status.value,
        "revision_count": len(closed.revisions),
        "audit_event_count": len(rfis.audit(project_id, closed.id)),
        "report": str(report),
        "qa": answer.answer,
        "completed_at": datetime.now(UTC).isoformat(),
    }
