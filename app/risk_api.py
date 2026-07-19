from datetime import date
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict
from config import get_settings
from risk_intelligence.models import Evidence
from risk_intelligence.qa import RiskQuestionService
from risk_intelligence.repository import JsonRiskRepository
from risk_intelligence.service import RiskIntelligenceService

router = APIRouter(prefix="/projects/{project_id}", tags=["risk-commitment-intelligence"])


def _service():
    return RiskIntelligenceService(
        JsonRiskRepository(get_settings().data_directory / "risk-intelligence")
    )


def _call(fn):
    try:
        value = fn()
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        return [x.model_dump(mode="json") for x in value] if isinstance(value, tuple) else value
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


class EvidenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    record_type: str
    record_id: str
    citation: dict[str, object]
    excerpt: str
    status: str | None = None
    location: str | None = None
    system: str | None = None

    def value(self):
        return Evidence(**self.model_dump())


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence: tuple[EvidenceRequest, ...]
    category: str = "unknown"


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: str
    actor: str
    rationale: str = ""
    owner: str | None = None


class MitigationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str
    actor: str
    owner: str | None = None
    due_date: date | None = None


class CommitmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_type: str
    source_id: str
    title: str
    evidence: tuple[EvidenceRequest, ...]
    owner: str | None = None
    due_date: date | None = None
    dependencies: tuple[str, ...] = ()


class CompletionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor: str
    evidence: tuple[EvidenceRequest, ...]


class DependencyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str
    target_id: str
    relationship: str
    evidence: tuple[EvidenceRequest, ...]


class QuestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str


@router.post("/risk-candidates", status_code=201)
def generate(project_id: str, body: GenerateRequest):
    return _call(
        lambda: _service().generate(
            project_id, tuple(x.value() for x in body.evidence), body.category
        )
    )


@router.get("/risk-candidates")
def risks(project_id: str, status: str | None = None):
    return _call(
        lambda: tuple(
            x
            for x in _service().repository.list("risks", project_id)
            if not status or x.status == status
        )
    )


@router.get("/risk-candidates/{risk_id}")
def risk(project_id: str, risk_id: str):
    return _call(lambda: _service()._risk(project_id, risk_id))


@router.post("/risk-candidates/{risk_id}/review")
def review(project_id: str, risk_id: str, body: ReviewRequest):
    return _call(
        lambda: _service().review(
            project_id, risk_id, body.decision, body.actor, body.rationale, body.owner
        )
    )


@router.post("/risk-candidates/{risk_id}/mitigations", status_code=201)
def mitigation(project_id: str, risk_id: str, body: MitigationRequest):
    return _call(
        lambda: _service().add_mitigation(
            project_id, risk_id, body.description, body.actor, body.owner, body.due_date
        )
    )


@router.post("/commitments", status_code=201)
def commitment(project_id: str, body: CommitmentRequest):
    return _call(
        lambda: _service().normalize_commitment(
            project_id,
            body.source_type,
            body.source_id,
            body.title,
            tuple(x.value() for x in body.evidence),
            body.owner,
            body.due_date,
            body.dependencies,
        )
    )


@router.get("/commitments")
def commitments(project_id: str):
    return _call(lambda: _service().repository.list("commitments", project_id))


@router.post("/commitments/{commitment_id}/confirm-completion")
def completion(project_id: str, commitment_id: str, body: CompletionRequest):
    return _call(
        lambda: _service().confirm_completion(
            project_id, commitment_id, tuple(x.value() for x in body.evidence), body.actor
        )
    )


@router.post("/risk-dependencies", status_code=201)
def dependency(project_id: str, body: DependencyRequest):
    return _call(
        lambda: _service().add_dependency(
            project_id,
            body.source_id,
            body.target_id,
            body.relationship,
            tuple(x.value() for x in body.evidence),
        )
    )


@router.get("/risk-dependencies/{record_id}/blockers")
def blockers(project_id: str, record_id: str):
    return _call(lambda: _service().blockers(project_id, record_id))


@router.get("/risk-dependencies/{record_id}/downstream")
def downstream(project_id: str, record_id: str):
    return _call(lambda: _service().downstream(project_id, record_id))


@router.get("/risk-dashboard")
def dashboard(project_id: str):
    return _call(lambda: _service().dashboard(project_id))


@router.post("/risk-questions")
def question(project_id: str, body: QuestionRequest):
    return _call(lambda: RiskQuestionService(_service()).answer(project_id, body.question))
