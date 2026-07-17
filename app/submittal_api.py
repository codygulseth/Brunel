# mypy: disable-error-code=no-untyped-def
"""Thin FastAPI routes for canonical submittal services."""

from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Header, Query
from pydantic import BaseModel, ConfigDict, Field

from change_workflow.models import ActorReference, ReviewerReference
from change_workflow.repository import JsonChangeWorkflowRepository
from config import get_settings
from rfi.repository import JsonRFIRepository
from storage import JsonDocumentRepository
from submittal.extraction import SubmittalRequirementExtractionService
from submittal.models import (
    AttachmentMetadata,
    InternalReviewDecision,
    OfficialDisposition,
    RequirementReviewDecision,
    StalenessStatus,
    SubmittalEvidenceReference,
    SubmittalManufacturer,
    SubmittalProduct,
    SubmittalRequirement,
    SubmittalStatus,
    SubmittalType,
)
from submittal.numbering import ProjectSubmittalNumberingService
from submittal.qa import SubmittalQuestionService
from submittal.reporting import SubmittalLogService, SubmittalRenderer
from submittal.repository import JsonSubmittalRepository
from submittal.service import SubmittalService

router = APIRouter()


def _public(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: _public(item) for key, item in value.items() if key != "source_location"}
    if isinstance(value, (list, tuple)):
        return [_public(item) for item in value]
    return value


def _repository() -> JsonSubmittalRepository:
    return JsonSubmittalRepository(get_settings().data_directory / "submittals")


def _service() -> SubmittalService:
    settings = get_settings()
    repository = _repository()
    return SubmittalService(
        repository,
        JsonChangeWorkflowRepository(settings.data_directory / "change-workflow"),
        JsonRFIRepository(settings.data_directory / "rfi"),
        numbering=ProjectSubmittalNumberingService(
            repository,
            prefix=settings.submittal.numbering_prefix,
            digits=settings.submittal.numbering_digits,
            mode=settings.submittal.numbering_mode,
        ),
    )


def _actor(actor_id: str | None, actor_name: str | None) -> ActorReference:
    return ActorReference(id=actor_id or "local-user", display_name=actor_name or "Local User")


class ExtractRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_ids: tuple[str, ...] = ()
    specification_sections: tuple[str, ...] = ()
    use_model: bool = False


class CandidateReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: RequirementReviewDecision
    explanation: str = Field(min_length=1)
    description: str | None = None
    discipline: str | None = None
    responsible_subcontractor: str | None = None


class CreateSubmittalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    specification_section: str = Field(min_length=1)
    description: str = Field(min_length=1)
    requirements: tuple[SubmittalRequirement, ...] = ()
    discipline: str | None = None
    responsible_subcontractor: str | None = None
    related_project_change_ids: tuple[str, ...] = ()
    related_rfi_ids: tuple[str, ...] = ()
    required_on_site_date: date | None = None
    lead_time_days: int | None = Field(default=None, ge=0)


class AssignRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reviewer_id: str | None = None
    reviewer_name: str = "Reviewer"
    subcontractor: str | None = None
    planned_submit_date: date | None = None
    required_response_date: date | None = None


class TransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: SubmittalStatus
    reason: str | None = None


class ProcurementRequest(BaseModel):
    required_on_site_date: date
    fabrication_days: int = Field(ge=0)
    shipping_days: int = Field(default=0, ge=0)
    processing_days: int = Field(default=0, ge=0)
    review_days: int = Field(default=0, ge=0)
    resubmittal_days: int = Field(default=0, ge=0)
    buffer_days: int = Field(default=0, ge=0)


class CreatePackageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    register_item_ids: tuple[str, ...] = ()
    title: str | None = None
    description: str = ""
    submitter: str = Field(min_length=1)
    manufacturer: SubmittalManufacturer | None = None
    product: SubmittalProduct | None = None
    included_types: tuple[SubmittalType, ...] = ()
    attachments: tuple[AttachmentMetadata, ...] = ()
    deviations: tuple[str, ...] = ()
    related_rfi_ids: tuple[str, ...] = ()
    related_project_change_ids: tuple[str, ...] = ()


class SubmitReviewRequest(BaseModel):
    reviewer_id: str
    reviewer_name: str = "Reviewer"


class InternalReviewRequest(BaseModel):
    decision: InternalReviewDecision
    reviewer_id: str
    reviewer_name: str = "Reviewer"
    comments: str | None = None
    required_corrections: tuple[str, ...] = ()


class ResponseRequest(BaseModel):
    responding_organization: str
    responding_person: str | None = None
    disposition: OfficialDisposition
    original_disposition_text: str
    review_comments: tuple[str, ...] = ()
    required_corrections: tuple[str, ...] = ()
    evidence: tuple[SubmittalEvidenceReference, ...] = ()
    official: bool = True
    supersedes_response_id: str | None = None


class ResubmitRequest(BaseModel):
    change_summary: str = Field(min_length=1)


class StaleRequest(BaseModel):
    reasons: tuple[str, ...] = Field(min_length=1)
    source_references: tuple[str, ...] = ()
    status: StalenessStatus = StalenessStatus.POTENTIALLY_STALE


class ReleaseRequest(BaseModel):
    corrections_incorporated: bool = False


class QuestionRequest(BaseModel):
    question: str = Field(min_length=1)


@router.post("/projects/{project_id}/submittal-requirements/extract")
def extract_requirements(project_id: str, body: ExtractRequest):
    settings = get_settings()
    service = SubmittalRequirementExtractionService(
        JsonDocumentRepository(settings.data_directory / "ingested"), _repository()
    )
    return _public(
        service.extract(
            project_id,
            document_ids=body.document_ids,
            specification_sections=body.specification_sections,
            use_model=body.use_model,
        )
    )


@router.get("/projects/{project_id}/submittal-requirements/candidates")
def list_candidates(project_id: str, limit: int = Query(50, ge=1, le=200), offset: int = 0):
    items = _repository().list_candidates(project_id)
    return _public({"items": items[offset : offset + limit], "total": len(items)})


@router.post("/projects/{project_id}/submittal-requirements/{candidate_id}/review")
def review_candidate(
    project_id: str,
    candidate_id: str,
    body: CandidateReviewRequest,
    x_actor_id: str | None = Header(None),
    x_actor_name: str | None = Header(None),
):
    return _public(
        _service().review_candidate(
            project_id,
            candidate_id,
            body.decision,
            _actor(x_actor_id, x_actor_name),
            explanation=body.explanation,
            description=body.description,
            discipline=body.discipline,
            responsible_subcontractor=body.responsible_subcontractor,
        )
    )


@router.get("/projects/{project_id}/submittals")
def list_submittals(
    project_id: str,
    status: SubmittalStatus | None = None,
    discipline: str | None = None,
    subcontractor: str | None = None,
    specification_section: str | None = None,
    overdue: bool | None = None,
    search: str | None = None,
    sort_by: Literal["number", "created", "planned_submit", "required_response"] = "number",
    sort_order: Literal["asc", "desc"] = "asc",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    items = SubmittalLogService(_repository()).list(
        project_id,
        status=status,
        discipline=discipline,
        subcontractor=subcontractor,
        specification_section=specification_section,
        overdue=overdue,
        search=search,
    )
    sort_keys = {
        "number": lambda item: (item.register_number, item.id),
        "created": lambda item: (item.created_at, item.id),
        "planned_submit": lambda item: (item.planned_submit_date or date.max, item.id),
        "required_response": lambda item: (item.required_response_date or date.max, item.id),
    }
    items = tuple(sorted(items, key=sort_keys[sort_by], reverse=sort_order == "desc"))
    return _public({"items": items[offset : offset + limit], "total": len(items)})


@router.post("/projects/{project_id}/submittals", status_code=201)
def create_submittal(
    project_id: str,
    body: CreateSubmittalRequest,
    x_actor_id: str | None = Header(None),
    x_actor_name: str | None = Header(None),
    x_idempotency_key: str | None = Header(None),
):
    return _public(
        _service().create_register(
            project_id=project_id,
            specification_section=body.specification_section,
            description=body.description,
            actor=_actor(x_actor_id, x_actor_name),
            requirements=body.requirements,
            discipline=body.discipline,
            responsible_subcontractor=body.responsible_subcontractor,
            related_project_change_ids=body.related_project_change_ids,
            related_rfi_ids=body.related_rfi_ids,
            required_on_site_date=body.required_on_site_date,
            lead_time_days=body.lead_time_days,
            idempotency_key=x_idempotency_key,
        )
    )


@router.get("/projects/{project_id}/submittals/{submittal_id}")
def get_submittal(project_id: str, submittal_id: str):
    return _public(_service().get_register(project_id, submittal_id))


@router.patch("/projects/{project_id}/submittals/{submittal_id}")
def patch_submittal(
    project_id: str,
    submittal_id: str,
    body: AssignRequest,
    x_actor_id: str | None = Header(None),
    x_actor_name: str | None = Header(None),
):
    reviewer = (
        ReviewerReference(id=body.reviewer_id, display_name=body.reviewer_name)
        if body.reviewer_id
        else None
    )
    return _public(
        _service().assign(
            project_id,
            submittal_id,
            _actor(x_actor_id, x_actor_name),
            reviewer=reviewer,
            subcontractor=body.subcontractor,
            planned_submit_date=body.planned_submit_date,
            required_response_date=body.required_response_date,
        )
    )


@router.post("/projects/{project_id}/submittals/{submittal_id}/assign")
def assign_submittal(
    project_id: str,
    submittal_id: str,
    body: AssignRequest,
    x_actor_id: str | None = Header(None),
    x_actor_name: str | None = Header(None),
):
    return patch_submittal(project_id, submittal_id, body, x_actor_id, x_actor_name)


@router.post("/projects/{project_id}/submittals/{submittal_id}/procurement-dates")
def update_procurement(
    project_id: str,
    submittal_id: str,
    body: ProcurementRequest,
    x_actor_id: str | None = Header(None),
    x_actor_name: str | None = Header(None),
):
    return _public(
        _service().update_procurement(
            project_id,
            submittal_id,
            _actor(x_actor_id, x_actor_name),
            required_on_site_date=body.required_on_site_date,
            fabrication_days=body.fabrication_days,
            shipping_days=body.shipping_days,
            processing_days=body.processing_days,
            review_days=body.review_days,
            resubmittal_days=body.resubmittal_days,
            buffer_days=body.buffer_days,
        )
    )


@router.post("/projects/{project_id}/submittals/{submittal_id}/transition")
def transition_submittal(
    project_id: str,
    submittal_id: str,
    body: TransitionRequest,
    x_actor_id: str | None = Header(None),
    x_actor_name: str | None = Header(None),
):
    return _public(
        _service().transition(
            project_id,
            submittal_id,
            body.status,
            _actor(x_actor_id, x_actor_name),
            reason=body.reason,
        )
    )


@router.post("/projects/{project_id}/submittals/{submittal_id}/packages", status_code=201)
def create_package(
    project_id: str,
    submittal_id: str,
    body: CreatePackageRequest,
    x_actor_id: str | None = Header(None),
    x_actor_name: str | None = Header(None),
):
    return _public(
        _service().create_package(
            project_id,
            submittal_id,
            _actor(x_actor_id, x_actor_name),
            register_item_ids=body.register_item_ids,
            title=body.title,
            description=body.description,
            submitter=body.submitter,
            manufacturer=body.manufacturer,
            product=body.product,
            included_types=body.included_types,
            attachments=body.attachments,
            deviations=body.deviations,
            related_rfi_ids=body.related_rfi_ids,
            related_project_change_ids=body.related_project_change_ids,
        )
    )


@router.get("/projects/{project_id}/submittals/{submittal_id}/packages")
def list_packages(project_id: str, submittal_id: str):
    _service().get_register(project_id, submittal_id)
    return _public(
        tuple(
            package
            for package in _repository().list_packages(project_id)
            if submittal_id in package.register_item_ids
        )
    )


@router.get("/projects/{project_id}/submittal-packages/{package_id}")
def get_package(project_id: str, package_id: str):
    return _public(_service().get_package(project_id, package_id))


@router.post("/projects/{project_id}/submittal-packages/{package_id}/completeness-review")
def completeness_review(
    project_id: str,
    package_id: str,
    x_actor_id: str | None = Header(None),
    x_actor_name: str | None = Header(None),
):
    return _public(
        _service().review_completeness(project_id, package_id, _actor(x_actor_id, x_actor_name))
    )


@router.post("/projects/{project_id}/submittal-packages/{package_id}/submit-internal-review")
def submit_internal_review(
    project_id: str,
    package_id: str,
    body: SubmitReviewRequest,
    x_actor_id: str | None = Header(None),
    x_actor_name: str | None = Header(None),
):
    return _public(
        _service().submit_internal_review(
            project_id,
            package_id,
            ReviewerReference(id=body.reviewer_id, display_name=body.reviewer_name),
            _actor(x_actor_id, x_actor_name),
        )
    )


@router.post("/projects/{project_id}/submittal-packages/{package_id}/internal-review")
def internal_review(
    project_id: str,
    package_id: str,
    body: InternalReviewRequest,
    x_actor_id: str | None = Header(None),
    x_actor_name: str | None = Header(None),
):
    return _public(
        _service().internal_review(
            project_id,
            package_id,
            body.decision,
            ReviewerReference(id=body.reviewer_id, display_name=body.reviewer_name),
            _actor(x_actor_id, x_actor_name),
            comments=body.comments,
            required_corrections=body.required_corrections,
        )
    )


@router.post("/projects/{project_id}/submittal-packages/{package_id}/issue")
def issue_package(
    project_id: str,
    package_id: str,
    x_actor_id: str | None = Header(None),
    x_actor_name: str | None = Header(None),
):
    return _public(
        _service().issue_package(project_id, package_id, _actor(x_actor_id, x_actor_name))
    )


@router.post("/projects/{project_id}/submittal-packages/{package_id}/responses")
def record_response(
    project_id: str,
    package_id: str,
    body: ResponseRequest,
    x_actor_id: str | None = Header(None),
    x_actor_name: str | None = Header(None),
):
    return _public(
        _service().record_response(
            project_id,
            package_id,
            _actor(x_actor_id, x_actor_name),
            responding_organization=body.responding_organization,
            responding_person=body.responding_person,
            disposition=body.disposition,
            original_disposition_text=body.original_disposition_text,
            review_comments=body.review_comments,
            required_corrections=body.required_corrections,
            evidence=body.evidence,
            official=body.official,
            supersedes_response_id=body.supersedes_response_id,
        )
    )


@router.post("/projects/{project_id}/submittal-packages/{package_id}/analyze-response")
def analyze_response(
    project_id: str,
    package_id: str,
    x_actor_id: str | None = Header(None),
    x_actor_name: str | None = Header(None),
):
    return _public(
        _service().analyze_response(project_id, package_id, _actor(x_actor_id, x_actor_name))
    )


@router.post("/projects/{project_id}/submittal-packages/{package_id}/resubmit")
def resubmit(
    project_id: str,
    package_id: str,
    body: ResubmitRequest,
    x_actor_id: str | None = Header(None),
    x_actor_name: str | None = Header(None),
):
    return _public(
        _service().resubmit(
            project_id,
            package_id,
            _actor(x_actor_id, x_actor_name),
            change_summary=body.change_summary,
        )
    )


@router.post("/projects/{project_id}/submittal-packages/{package_id}/staleness")
def mark_stale(
    project_id: str,
    package_id: str,
    body: StaleRequest,
    x_actor_id: str | None = Header(None),
    x_actor_name: str | None = Header(None),
):
    return _public(
        _service().mark_stale(
            project_id,
            package_id,
            _actor(x_actor_id, x_actor_name),
            reasons=body.reasons,
            source_references=body.source_references,
            status=body.status,
        )
    )


@router.post("/projects/{project_id}/submittals/{submittal_id}/procurement-release")
def release_procurement(
    project_id: str,
    submittal_id: str,
    body: ReleaseRequest,
    x_actor_id: str | None = Header(None),
    x_actor_name: str | None = Header(None),
):
    return _public(
        _service().confirm_procurement_release(
            project_id,
            submittal_id,
            _actor(x_actor_id, x_actor_name),
            corrections_incorporated=body.corrections_incorporated,
        )
    )


@router.get("/projects/{project_id}/submittal-log")
def submittal_log(project_id: str):
    return _public(SubmittalLogService(_repository()).list(project_id))


@router.get("/projects/{project_id}/submittal-dashboard")
def submittal_dashboard(project_id: str):
    return _public(SubmittalLogService(_repository()).dashboard(project_id))


@router.get("/projects/{project_id}/submittals/{submittal_id}/audit")
def submittal_audit(project_id: str, submittal_id: str):
    _service().get_register(project_id, submittal_id)
    return _public(_repository().audit(project_id, submittal_id))


@router.get("/projects/{project_id}/submittals/{submittal_id}/export")
def export_submittal(
    project_id: str,
    submittal_id: str,
    format: Literal["markdown", "json"] = "markdown",
    x_actor_id: str | None = Header(None),
    x_actor_name: str | None = Header(None),
):
    service = _service()
    item = service.record_export(project_id, submittal_id, _actor(x_actor_id, x_actor_name), format)
    packages = tuple(
        package
        for package in _repository().list_packages(project_id)
        if item.id in package.register_item_ids
    )
    return {
        "format": format,
        "content": item.model_dump_json(indent=2)
        if format == "json"
        else SubmittalRenderer().markdown(item, packages),
    }


@router.post("/projects/{project_id}/submittal-questions")
def ask_submittal_question(project_id: str, body: QuestionRequest):
    return _public(SubmittalQuestionService(_repository()).answer(project_id, body.question))
