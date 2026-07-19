from datetime import date
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict
from config import get_settings
from enterprise_intelligence.models import Evidence, SharingLevel
from enterprise_intelligence.qa import EnterpriseQuestionService
from enterprise_intelligence.repository import JsonEnterpriseRepository
from enterprise_intelligence.service import EnterpriseIntelligenceService

router = APIRouter(
    prefix="/organizations/{organization_id}", tags=["enterprise-project-intelligence"]
)


def _service():
    return EnterpriseIntelligenceService(
        JsonEnterpriseRepository(get_settings().data_directory / "enterprise-intelligence")
    )


def _call(fn):
    try:
        value = fn()
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        return [x.model_dump(mode="json") for x in value] if isinstance(value, tuple) else value
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


class PortfolioBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    principal_ids: tuple[str, ...]
    actor: str


class MembershipBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str
    principal_ids: tuple[str, ...]
    sharing: SharingLevel
    actor: str
    taxonomy: dict[str, str] = {}
    eligible: bool = False


class EvidenceBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str
    record_type: str
    record_id: str
    citation: dict[str, object]
    excerpt: str
    recorded_on: date | None = None
    confidentiality: SharingLevel = SharingLevel.PROJECT_ONLY

    def value(self):
        return Evidence(**self.model_dump())


class MetricBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str
    name: str
    value: float
    unit: str
    occurred_on: date
    evidence: tuple[EvidenceBody, ...]
    dimensions: dict[str, str] = {}
    actor: str


class DefinitionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    metric_name: str
    unit: str
    method: str = "median"
    minimum_sample_size: int = 4
    minimum_group_size: int = 3
    actor: str
    criteria: dict[str, str] = {}


class BenchmarkBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    portfolio_id: str
    principal_id: str


class QuestionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str
    portfolio_id: str
    principal_id: str


@router.post("/portfolios", status_code=201)
def portfolio(organization_id: str, body: PortfolioBody):
    return _call(
        lambda: _service().create_portfolio(
            organization_id, body.name, body.principal_ids, body.actor
        )
    )


@router.get("/portfolios")
def portfolios(organization_id: str):
    return _call(lambda: _service().repository.list("portfolios", organization_id))


@router.post("/portfolios/{portfolio_id}/projects")
def membership(organization_id: str, portfolio_id: str, body: MembershipBody):
    return _call(
        lambda: _service().add_project(
            organization_id,
            portfolio_id,
            body.project_id,
            body.principal_ids,
            body.sharing,
            body.actor,
            taxonomy=body.taxonomy,
            eligible=body.eligible,
        )
    )


@router.get("/portfolios/{portfolio_id}/dashboard")
def dashboard(organization_id: str, portfolio_id: str, principal_id: str):
    return _call(lambda: _service().dashboard(organization_id, portfolio_id, principal_id))


@router.post("/metrics", status_code=201)
def metric(organization_id: str, body: MetricBody):
    return _call(
        lambda: _service().add_metric(
            organization_id,
            body.project_id,
            body.name,
            body.value,
            body.unit,
            body.occurred_on,
            tuple(x.value() for x in body.evidence),
            body.dimensions,
            body.actor,
        )
    )


@router.post("/benchmark-definitions", status_code=201)
def definition(organization_id: str, body: DefinitionBody):
    return _call(
        lambda: _service().create_benchmark_definition(
            organization_id,
            body.name,
            body.metric_name,
            body.unit,
            body.method,
            body.minimum_sample_size,
            body.actor,
            body.criteria,
            body.minimum_group_size,
        )
    )


@router.post("/benchmark-definitions/{definition_id}/approve")
def approve_definition(organization_id: str, definition_id: str, actor: str):
    return _call(
        lambda: _service().review_benchmark_definition(organization_id, definition_id, actor)
    )


@router.post("/benchmark-definitions/{definition_id}/calculate")
def benchmark(organization_id: str, definition_id: str, body: BenchmarkBody):
    return _call(
        lambda: _service().calculate_benchmark(
            organization_id, definition_id, body.portfolio_id, body.principal_id
        )
    )


@router.get("/benchmarks")
def benchmarks(organization_id: str):
    return _call(lambda: _service().repository.list("benchmarks", organization_id))


@router.post("/enterprise-questions")
def question(organization_id: str, body: QuestionBody):
    return _call(
        lambda: EnterpriseQuestionService(_service()).answer(
            organization_id, body.question, body.portfolio_id, body.principal_id
        )
    )
