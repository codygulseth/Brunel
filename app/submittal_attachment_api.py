# mypy: disable-error-code=no-untyped-def
"""FastAPI adapter for project-scoped submittal attachment intelligence."""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field

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
    AttachmentEvidenceReference,
    AttachmentRole,
    AttachmentType,
    HumanConfirmationStatus,
    ReadabilityStatus,
)
from submittal.attachment_qa import AttachmentQuestionService, AttachmentSearchService
from submittal.attachment_reporting import AttachmentIntelligenceRenderer
from submittal.attachment_repository import JsonAttachmentIntelligenceRepository
from submittal.models import MatrixStatus
from submittal.repository import JsonSubmittalRepository

router = APIRouter(tags=["submittal-attachment-intelligence"])


def _repositories() -> tuple[JsonAttachmentIntelligenceRepository, JsonSubmittalRepository]:
    settings = get_settings()
    return (
        JsonAttachmentIntelligenceRepository(
            settings.data_directory / "submittal-attachment-intelligence"
        ),
        JsonSubmittalRepository(settings.data_directory / "submittals"),
    )


def _analysis() -> PackageAttachmentAnalysisService:
    settings = get_settings()
    attachments, submittals = _repositories()
    return PackageAttachmentAnalysisService(
        attachments,
        submittals,
        JsonChangeWorkflowRepository(settings.data_directory / "change-workflow"),
        extraction_policy_version=settings.submittal.attachment_extractor_version,
        mapping_policy_version=settings.submittal.attachment_mapping_policy,
    )


def _ingestion() -> AttachmentIngestionService:
    settings = get_settings()
    attachments, submittals = _repositories()
    return AttachmentIngestionService(
        attachments,
        submittals,
        JsonDocumentRepository(settings.data_directory / "ingested"),
        LocalAttachmentFileStore(
            settings.data_directory / settings.submittal.attachment_storage_directory
        ),
        JsonChangeWorkflowRepository(settings.data_directory / "change-workflow"),
        maximum_file_size=settings.submittal.attachment_max_file_size,
        allowed_input_root=settings.data_directory.resolve().parent,
        extraction_policy_version=settings.submittal.attachment_extractor_version,
        mapping_policy_version=settings.submittal.attachment_mapping_policy,
    )


def _actor(actor_id: str | None, actor_name: str | None) -> ActorReference:
    return ActorReference(id=actor_id or "local-user", display_name=actor_name or "Local User")


def _public(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    if isinstance(value, dict):
        hidden = {"source_location", "source_path", "storage_reference"}
        return {key: _public(item) for key, item in value.items() if key not in hidden}
    if isinstance(value, (list, tuple)):
        return [_public(item) for item in value]
    return value


class RegisterAttachmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file_path: Path
    package_revision: int | None = Field(default=None, ge=1)
    attachment_id: str | None = None
    declared_type: AttachmentType | None = None
    role: AttachmentRole = AttachmentRole.UNKNOWN
    display_name: str | None = None
    revision_label: str | None = None
    supersedes_attachment_revision_id: str | None = None


class MappingReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reviewer_id: str
    reviewer_name: str = "Reviewer"
    confirmation: HumanConfirmationStatus
    status: MatrixStatus | None = None
    note: str | None = None
    added_evidence: tuple[AttachmentEvidenceReference, ...] = ()
    removed_evidence_ids: tuple[str, ...] = ()


class CompareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    old_package_revision: int = Field(ge=1)
    new_package_revision: int = Field(ge=1)


class QuestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1)


@router.post("/projects/{project_id}/submittal-packages/{package_id}/attachments")
def register_attachment(
    project_id: str,
    package_id: str,
    body: RegisterAttachmentRequest,
    x_actor_id: str | None = Header(None),
    x_actor_name: str | None = Header(None),
):
    return _public(
        _ingestion().ingest(
            project_id,
            package_id,
            body.file_path,
            _actor(x_actor_id, x_actor_name),
            package_revision=body.package_revision,
            attachment_id=body.attachment_id,
            declared_type=body.declared_type,
            role=body.role,
            display_name=body.display_name,
            revision_label=body.revision_label,
            supersedes_attachment_revision_id=body.supersedes_attachment_revision_id,
        )
    )


@router.get("/projects/{project_id}/submittal-packages/{package_id}/attachments")
def list_attachments(
    project_id: str,
    package_id: str,
    attachment_type: AttachmentType | None = None,
    readability: ReadabilityStatus | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    attachments, _ = _repositories()
    items = attachments.list_attachments(project_id, package_id)
    if attachment_type:
        items = tuple(
            item
            for item in items
            if any(
                revision.id == item.active_revision_id and revision.inferred_type == attachment_type
                for revision in item.revisions
            )
        )
    if readability:
        items = tuple(
            item
            for item in items
            if any(
                revision.id == item.active_revision_id
                and revision.readability_status == readability
                for revision in item.revisions
            )
        )
    return {"items": _public(items[offset : offset + limit]), "total": len(items)}


@router.get("/projects/{project_id}/submittal-attachments/search")
def search(
    project_id: str,
    q: str = Query(min_length=1),
    package_id: str | None = None,
    package_revision: int | None = Query(default=None, ge=1),
    attachment_type: AttachmentType | None = None,
):
    attachments, submittals = _repositories()
    return _public(
        AttachmentSearchService(attachments, submittals).search(
            project_id,
            q,
            package_id=package_id,
            package_revision=package_revision,
            attachment_type=attachment_type,
        )
    )


@router.get("/projects/{project_id}/submittal-attachments/{attachment_id}")
def get_attachment(project_id: str, attachment_id: str):
    attachments, _ = _repositories()
    item = attachments.get_attachment(project_id, attachment_id)
    if item is None:
        raise HTTPException(404, "Attachment not found in requested project")
    return _public(item)


@router.post("/projects/{project_id}/submittal-attachments/{attachment_id}/analyze")
def analyze_attachment(project_id: str, attachment_id: str):
    attachments, _ = _repositories()
    item = attachments.get_attachment(project_id, attachment_id)
    if item is None:
        raise HTTPException(404, "Attachment not found in requested project")
    active = next(value for value in item.revisions if value.id == item.active_revision_id)
    extraction = (
        attachments.get_extraction(project_id, active.extraction_result_id)
        if active.extraction_result_id
        else None
    )
    return _public(extraction)


@router.get(
    "/projects/{project_id}/submittal-attachments/{attachment_id}/extractions/{extraction_id}"
)
def get_extraction(project_id: str, attachment_id: str, extraction_id: str):
    attachments, _ = _repositories()
    extraction = attachments.get_extraction(project_id, extraction_id)
    return _public(extraction if extraction and extraction.attachment_id == attachment_id else None)


@router.post("/projects/{project_id}/submittal-packages/{package_id}/attachment-analysis")
def analyze(
    project_id: str,
    package_id: str,
    x_actor_id: str | None = Header(None),
    x_actor_name: str | None = Header(None),
):
    return _public(
        _analysis().analyze_package(project_id, package_id, _actor(x_actor_id, x_actor_name))
    )


@router.get("/projects/{project_id}/submittal-packages/{package_id}/attachment-summary")
def summary(project_id: str, package_id: str):
    return _public(_analysis().summary(project_id, package_id))


@router.get("/projects/{project_id}/submittal-packages/{package_id}/evidence-set")
def evidence_set(project_id: str, package_id: str):
    return _public(_analysis().latest_evidence_set(project_id, package_id))


@router.get("/projects/{project_id}/submittal-packages/{package_id}/conflicts")
def conflicts(project_id: str, package_id: str):
    evidence = _analysis().latest_evidence_set(project_id, package_id)
    return _public(evidence.conflicts if evidence else ())


@router.get("/projects/{project_id}/submittal-packages/{package_id}/missing-attachments")
def missing_attachments(project_id: str, package_id: str):
    evidence = _analysis().latest_evidence_set(project_id, package_id)
    return _public(evidence.missing_attachments if evidence else ())


@router.get("/projects/{project_id}/submittal-packages/{package_id}/mismatches")
def mismatches(project_id: str, package_id: str):
    evidence = _analysis().latest_evidence_set(project_id, package_id)
    return _public(evidence.mismatches if evidence else ())


@router.post("/projects/{project_id}/submittal-packages/{package_id}/compliance-matrix/generate")
def generate_compliance_matrix(
    project_id: str,
    package_id: str,
    x_actor_id: str | None = Header(None),
    x_actor_name: str | None = Header(None),
):
    return _public(
        _analysis().generate_mappings(project_id, package_id, _actor(x_actor_id, x_actor_name))
    )


@router.get("/projects/{project_id}/submittal-packages/{package_id}/compliance-matrix")
@router.get("/projects/{project_id}/submittal-packages/{package_id}/compliance-mappings")
def mappings(project_id: str, package_id: str):
    attachments, submittals = _repositories()
    package = submittals.get_package(project_id, package_id)
    return _public(
        attachments.list_mappings(
            project_id, package_id, package.current_revision if package else None
        )
    )


@router.post(
    "/projects/{project_id}/submittal-packages/{package_id}/compliance-matrix/{requirement_id}/review"
)
@router.post(
    "/projects/{project_id}/submittal-packages/{package_id}/compliance-mappings/{requirement_id}/review"
)
def review_mapping(
    project_id: str,
    package_id: str,
    requirement_id: str,
    body: MappingReviewRequest,
    x_actor_id: str | None = Header(None),
    x_actor_name: str | None = Header(None),
):
    return _public(
        _analysis().review_mapping(
            project_id,
            package_id,
            requirement_id,
            ReviewerReference(id=body.reviewer_id, display_name=body.reviewer_name),
            _actor(x_actor_id, x_actor_name),
            confirmation=body.confirmation,
            status=body.status,
            note=body.note,
            added_evidence=body.added_evidence,
            removed_evidence_ids=body.removed_evidence_ids,
        )
    )


@router.post("/projects/{project_id}/submittal-packages/{package_id}/attachment-comparisons")
def compare(
    project_id: str,
    package_id: str,
    body: CompareRequest,
    x_actor_id: str | None = Header(None),
    x_actor_name: str | None = Header(None),
):
    attachments, submittals = _repositories()
    return _public(
        PackageRevisionComparisonService(attachments, submittals).compare(
            project_id,
            package_id,
            body.old_package_revision,
            body.new_package_revision,
            _actor(x_actor_id, x_actor_name),
        )
    )


@router.get("/projects/{project_id}/submittal-package-comparisons/{comparison_id}")
def get_comparison(project_id: str, comparison_id: str):
    attachments, _ = _repositories()
    item = attachments.get_comparison(project_id, comparison_id)
    if item is None:
        raise HTTPException(404, "Package comparison not found in requested project")
    return _public(item)


@router.get("/projects/{project_id}/submittal-package-comparisons/{comparison_id}/export")
def export_comparison(project_id: str, comparison_id: str):
    attachments, submittals = _repositories()
    item = attachments.get_comparison(project_id, comparison_id)
    if item is None:
        raise HTTPException(404, "Package comparison not found in requested project")
    renderer = AttachmentIntelligenceRenderer(
        attachments, PackageAttachmentAnalysisService(attachments, submittals)
    )
    return PlainTextResponse(renderer.comparison_markdown(item))


@router.post("/projects/{project_id}/submittal-packages/{package_id}/attachment-staleness/check")
@router.post("/projects/{project_id}/submittal-packages/{package_id}/staleness-check")
def check_staleness(
    project_id: str,
    package_id: str,
    x_actor_id: str | None = Header(None),
    x_actor_name: str | None = Header(None),
):
    return _public(
        _analysis().check_staleness(project_id, package_id, _actor(x_actor_id, x_actor_name))
    )


@router.get("/projects/{project_id}/submittal-packages/{package_id}/staleness")
def get_staleness(project_id: str, package_id: str):
    attachments, _ = _repositories()
    return _public(attachments.list_staleness(project_id, package_id))


@router.post(
    "/projects/{project_id}/submittal-packages/{package_id}/attachment-staleness/acknowledge"
)
@router.post("/projects/{project_id}/submittal-packages/{package_id}/acknowledge-staleness")
def acknowledge_staleness(
    project_id: str,
    package_id: str,
    x_actor_id: str | None = Header(None),
    x_actor_name: str | None = Header(None),
):
    return _public(
        _analysis().acknowledge_staleness(project_id, package_id, _actor(x_actor_id, x_actor_name))
    )


@router.post("/projects/{project_id}/submittal-attachments/questions")
def question(project_id: str, body: QuestionRequest, package_id: str | None = None):
    attachments, submittals = _repositories()
    return _public(
        AttachmentQuestionService(attachments, submittals).answer(
            project_id, body.question, package_id=package_id
        )
    )


@router.get("/projects/{project_id}/submittal-packages/{package_id}/attachment-audit")
def attachment_audit(project_id: str, package_id: str):
    _, submittals = _repositories()
    attachment_ids = {
        item.id for item in _repositories()[0].list_attachments(project_id, package_id)
    }
    return _public(
        tuple(
            item
            for item in submittals.audit(project_id)
            if item.entity_id == package_id or item.entity_id in attachment_ids
        )
    )
