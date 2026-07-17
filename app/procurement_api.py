"""Development FastAPI adapter for Procurement Intelligence."""

from datetime import date
from typing import Any
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from config import get_settings
from procurement.models import ProcurementCategory, ProcurementStatus
from procurement.repository import JsonProcurementRepository
from procurement.service import ProcurementService

router = APIRouter(prefix="/projects/{project_id}", tags=["procurement"])


def _service():
    return ProcurementService(
        JsonProcurementRepository(get_settings().data_directory / "procurement")
    )


def _public(v: Any):
    if hasattr(v, "model_dump"):
        v = v.model_dump(mode="json")
    if isinstance(v, dict):
        return {
            k: _public(x)
            for k, x in v.items()
            if k not in {"source_location", "authorized_amount", "forecast_cost"}
        }
    if isinstance(v, (list, tuple)):
        return [_public(x) for x in v]
    return v


def _call(fn):
    try:
        return _public(fn())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


class ExtractRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sources: list[dict[str, object]]


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: str
    title: str | None = None
    linked_item_id: str | None = None


class CreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1)
    description: str = ""
    category: ProcurementCategory = ProcurementCategory.OTHER
    required_on_site: date | None = None
    equipment_tag: str | None = None


class PatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    supplier: str | None = None
    manufacturer: str | None = None
    product: str | None = None
    model_number: str | None = None
    responsible_subcontractor: str | None = None
    criticality: str | None = None
    notes: tuple[str, ...] | None = None


class TransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: ProcurementStatus
    reason: str | None = None


class LeadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    duration: int = Field(gt=0)
    unit: str
    definition: str
    source_type: str = "human_entry"
    confirmed: bool = False
    active: bool = True
    notes: str | None = None


class DependencyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dependency_type: str
    target_reference: str
    status: str = "open"
    human_confirmed: bool = False


class MilestoneRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    milestone_type: str
    planned_date: date | None = None
    forecast_date: date | None = None
    actual_date: date | None = None
    human_confirmed: bool = False


class ForecastRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    delivery_date: date | None = None
    release_date: date | None = None
    confidence: str = "insufficient"
    basis: str
    assumptions: tuple[str, ...] = ()
    confirmed: bool = False


class AuthorizationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    authorized_by: str
    reference: str


class ProductSubmittalLinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    submittal_id: str | None = None
    product: str | None = None
    manufacturer: str | None = None
    model_number: str | None = None


class AcceptanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accepted_by: str
    reference: str


class DeliveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    delivery_date: date
    status: str = "delivered"
    quantity: float | None = None
    partial: bool = False
    damage_noted: bool = False
    accepted: bool = False


class PlanDatesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    shipping_days: int | None = None
    fabrication_days: int | None = None
    procurement_processing_days: int | None = None
    design_review_days: int | None = None
    receiving_days: int = 0
    buffer_days: int = 0


class StaleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1)


class CompareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    old_plan_id: str
    new_plan_id: str


@router.post("/procurement-candidates/extract")
def extract(project_id: str, body: ExtractRequest):
    return _call(lambda: _service().extract_candidates(project_id, body.sources))


@router.get("/procurement-candidates")
def candidates(project_id: str):
    return _public(_service().repository.list("candidates", project_id))


@router.post("/procurement-candidates/{candidate_id}/review")
def review(
    project_id: str, candidate_id: str, body: ReviewRequest, x_actor_id: str | None = Header(None)
):
    return _call(
        lambda: _service().review_candidate(
            project_id,
            candidate_id,
            body.decision,
            x_actor_id or "local-user",
            title=body.title,
            linked_item_id=body.linked_item_id,
        )
    )


@router.post("/procurement-items", status_code=201)
def create(project_id: str, body: CreateRequest, x_actor_id: str | None = Header(None)):
    return _call(
        lambda: _service().create_item(
            project_id,
            body.title,
            description=body.description,
            category=body.category,
            required_on_site=body.required_on_site,
            equipment_tag=body.equipment_tag,
            actor=x_actor_id or "local-user",
        )
    )


@router.get("/procurement-items")
def items(
    project_id: str,
    status: ProcurementStatus | None = None,
    query: str | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    return _public(
        _service().list_items(project_id, status=status, query=query)[offset : offset + limit]
    )


@router.get("/procurement-items/{item_id}")
def item(project_id: str, item_id: str):
    return _call(lambda: _service()._require_item(project_id, item_id))


@router.patch("/procurement-items/{item_id}")
def patch(project_id: str, item_id: str, body: PatchRequest, x_actor_id: str | None = Header(None)):
    return _call(
        lambda: _service().update_item(
            project_id, item_id, x_actor_id or "local-user", **body.model_dump(exclude_none=True)
        )
    )


@router.post("/procurement-items/{item_id}/transition")
def transition(
    project_id: str, item_id: str, body: TransitionRequest, x_actor_id: str | None = Header(None)
):
    return _call(
        lambda: _service().transition(
            project_id, item_id, body.status, x_actor_id or "local-user", reason=body.reason
        )
    )


@router.post("/procurement-items/{item_id}/lead-times")
def lead(project_id: str, item_id: str, body: LeadRequest, x_actor_id: str | None = Header(None)):
    return _call(
        lambda: _service().add_lead_time(
            project_id, item_id, actor=x_actor_id or "local-user", **body.model_dump()
        )
    )


@router.post("/procurement-items/{item_id}/dependencies")
def dependency(
    project_id: str, item_id: str, body: DependencyRequest, x_actor_id: str | None = Header(None)
):
    return _call(
        lambda: _service().add_dependency(
            project_id, item_id, actor=x_actor_id or "local-user", **body.model_dump()
        )
    )


@router.post("/procurement-items/{item_id}/milestones")
def milestone(
    project_id: str, item_id: str, body: MilestoneRequest, x_actor_id: str | None = Header(None)
):
    return _call(
        lambda: _service().add_milestone(
            project_id, item_id, actor=x_actor_id or "local-user", **body.model_dump()
        )
    )


@router.post("/procurement-items/{item_id}/forecasts")
def forecast(
    project_id: str, item_id: str, body: ForecastRequest, x_actor_id: str | None = Header(None)
):
    return _call(
        lambda: _service().forecast(
            project_id,
            item_id,
            body.delivery_date,
            body.release_date,
            body.confidence,
            body.basis,
            x_actor_id or "local-user",
            assumptions=body.assumptions,
            confirmed=body.confirmed,
        )
    )


@router.post("/procurement-items/{item_id}/plan-dates")
def dates(project_id: str, item_id: str, body: PlanDatesRequest):
    return _call(lambda: _service().calculate_dates(project_id, item_id, **body.model_dump()))


@router.post("/procurement-items/{item_id}/release-readiness")
def readiness(project_id: str, item_id: str):
    return _call(lambda: _service().assess_release_readiness(project_id, item_id))


@router.post("/procurement-items/{item_id}/release-authorization")
def authorization(project_id: str, item_id: str, body: AuthorizationRequest):
    return _call(
        lambda: _service().authorize_release(
            project_id, item_id, body.authorized_by, body.reference
        )
    )


@router.post("/procurement-items/{item_id}/product-submittal-link")
def product_submittal_link(
    project_id: str,
    item_id: str,
    body: ProductSubmittalLinkRequest,
    x_actor_id: str | None = Header(None),
):
    return _call(
        lambda: _service().link_product_and_submittal(
            project_id,
            item_id,
            actor=x_actor_id or "local-user",
            **body.model_dump(),
        )
    )


@router.post("/procurement-items/{item_id}/delivery")
def delivery(
    project_id: str, item_id: str, body: DeliveryRequest, x_actor_id: str | None = Header(None)
):
    return _call(
        lambda: _service().record_delivery(
            project_id, item_id, actor=x_actor_id or "local-user", **body.model_dump()
        )
    )


@router.post("/procurement-items/{item_id}/acceptance")
def acceptance(project_id: str, item_id: str, body: AcceptanceRequest):
    return _call(
        lambda: _service().record_acceptance(project_id, item_id, body.accepted_by, body.reference)
    )


@router.post("/procurement-items/{item_id}/staleness-check")
def stale(project_id: str, item_id: str, body: StaleRequest, x_actor_id: str | None = Header(None)):
    return _call(
        lambda: _service().mark_stale(project_id, item_id, body.reason, x_actor_id or "local-user")
    )


@router.get("/procurement-items/{item_id}/audit")
def audit(project_id: str, item_id: str):
    return _public(
        tuple(x for x in _service().repository.list("audit", project_id) if x.subject_id == item_id)
    )


@router.get("/procurement-register")
def register(project_id: str):
    return _public(_service().list_items(project_id))


@router.get("/procurement-dashboard")
def dashboard(project_id: str):
    return _public(_service().dashboard(project_id))


@router.get("/procurement-exposures")
def exposures(project_id: str):
    return _public(
        tuple(
            _service().assess_exposure(project_id, x.id) for x in _service().list_items(project_id)
        )
    )


@router.post("/procurement-plans", status_code=201)
def snapshot(project_id: str, x_actor_id: str | None = Header(None)):
    return _public(_service().snapshot(project_id, x_actor_id or "local-user"))


@router.get("/procurement-plans")
def plans(project_id: str):
    return _public(_service().repository.list("plans", project_id))


@router.post("/procurement-plan-comparisons")
def compare(project_id: str, body: CompareRequest):
    return _call(lambda: _service().compare_plans(project_id, body.old_plan_id, body.new_plan_id))


@router.get("/procurement-plan-comparisons/{comparison_id}")
def comparison(project_id: str, comparison_id: str):
    return _call(
        lambda: _service().repository.get("comparisons", comparison_id, project_id)
        or (_ for _ in ()).throw(ValueError("Comparison not found"))
    )
