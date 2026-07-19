from datetime import date
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict
from config import get_settings
from contract_intelligence.models import Evidence
from contract_intelligence.qa import ContractQuestionService
from contract_intelligence.repository import JsonContractRepository
from contract_intelligence.service import ContractIntelligenceService

router = APIRouter(prefix="/projects/{project_id}", tags=["contract-intelligence"])


def _service():
    return ContractIntelligenceService(
        JsonContractRepository(get_settings().data_directory / "contract-intelligence")
    )


def _call(fn):
    try:
        value = fn()
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        return [x.model_dump(mode="json") for x in value] if isinstance(value, tuple) else value
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


class EvidenceBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    record_type: str
    record_id: str
    citation: dict[str, object]
    exact_text: str
    source_date: date | None = None
    human_confirmed: bool = False

    def value(self):
        return Evidence(**self.model_dump())


class DocumentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_revision_id: str
    document_type: str
    title: str
    evidence: tuple[EvidenceBody, ...]
    relationship_id: str | None = None
    supersedes_id: str | None = None


class RelationshipBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    parties: tuple[str, ...]
    roles: dict[str, str]
    evidence: tuple[EvidenceBody, ...] = ()


class ClauseBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence: tuple[EvidenceBody, ...]


class RequirementBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    clause_id: str
    title: str
    description: str
    time_limit: int | None = None
    calendar_basis: str | None = None
    recipient: str | None = None
    delivery_method: str | None = None
    trigger: str | None = None


class DeadlineBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trigger_date: date | None = None
    holidays: tuple[date, ...] = ()
    direction: str = "after"


class CandidateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requirement_id: str
    event_record_id: str
    event_evidence: tuple[EvidenceBody, ...]
    trigger_date: date | None = None
    notice_type: str = "unknown"


class QuestionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str


@router.post("/contracts", status_code=201)
def ingest(project_id: str, body: DocumentBody):
    return _call(
        lambda: _service().ingest_contract(
            project_id,
            body.source_revision_id,
            body.document_type,
            body.title,
            tuple(x.value() for x in body.evidence),
            relationship_id=body.relationship_id,
            supersedes_id=body.supersedes_id,
        )
    )


@router.get("/contracts")
def documents(project_id: str):
    return _call(lambda: _service().repository.list("documents", project_id))


@router.get("/contracts/{document_id}")
def document(project_id: str, document_id: str):
    return _call(lambda: _service()._get("documents", project_id, document_id))


@router.post("/contract-relationships", status_code=201)
def relationship(project_id: str, body: RelationshipBody):
    return _call(
        lambda: _service().create_relationship(
            project_id, body.parties, body.roles, tuple(x.value() for x in body.evidence)
        )
    )


@router.post("/contracts/{document_id}/clauses/extract")
def clauses(project_id: str, document_id: str, body: ClauseBody):
    return _call(
        lambda: _service().extract_clauses(
            project_id, document_id, tuple(x.value() for x in body.evidence)
        )
    )


@router.get("/contract-clauses")
def list_clauses(project_id: str):
    return _call(lambda: _service().repository.list("clauses", project_id))


@router.post("/contract-requirements", status_code=201)
def requirement(project_id: str, body: RequirementBody):
    return _call(
        lambda: _service().create_requirement(
            project_id,
            body.clause_id,
            body.title,
            body.description,
            time_limit=body.time_limit,
            calendar_basis=body.calendar_basis,
            recipient=body.recipient,
            delivery_method=body.delivery_method,
            trigger=body.trigger,
        )
    )


@router.get("/contract-requirements")
def requirements(project_id: str):
    return _call(lambda: _service().repository.list("requirements", project_id))


@router.post("/contract-requirements/{requirement_id}/deadline")
def deadline(project_id: str, requirement_id: str, body: DeadlineBody):
    return _call(
        lambda: _service().calculate_deadline(
            project_id,
            requirement_id,
            body.trigger_date,
            holidays=body.holidays,
            direction=body.direction,
        )
    )


@router.post("/notice-candidates", status_code=201)
def candidate(project_id: str, body: CandidateBody):
    return _call(
        lambda: _service().generate_notice_candidate(
            project_id,
            body.requirement_id,
            body.event_record_id,
            tuple(x.value() for x in body.event_evidence),
            trigger_date=body.trigger_date,
            notice_type=body.notice_type,
        )
    )


@router.get("/notice-candidates")
def candidates(project_id: str):
    return _call(lambda: _service().repository.list("candidates", project_id))


@router.get("/contract-chronology")
def chronology(project_id: str):
    return _call(lambda: _service().chronology(project_id))


@router.post("/contract-conflicts/generate")
def conflicts(project_id: str):
    return _call(lambda: _service().detect_conflicts(project_id))


@router.get("/contract-dashboard")
def dashboard(project_id: str):
    return _call(lambda: _service().dashboard(project_id))


@router.get("/contract-search")
def search(project_id: str, query: str):
    return _call(lambda: _service().search(project_id, query))


@router.post("/contract-questions")
def question(project_id: str, body: QuestionBody):
    return _call(lambda: ContractQuestionService(_service()).answer(project_id, body.question))
