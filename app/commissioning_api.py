from datetime import date
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict
from config import get_settings
from commissioning_intelligence.models import DeficiencyStatus, Evidence
from commissioning_intelligence.qa import CommissioningQuestionService
from commissioning_intelligence.repository import JsonCommissioningRepository
from commissioning_intelligence.service import CommissioningService

router = APIRouter(prefix="/projects/{project_id}", tags=["commissioning-turnover-intelligence"])


def _service():
    return CommissioningService(
        JsonCommissioningRepository(get_settings().data_directory / "commissioning-intelligence")
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
    excerpt: str
    visual_region: tuple[float, float, float, float] | None = None
    human_confirmed: bool = False

    def value(self):
        return Evidence(**self.model_dump())


class SystemBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    parent_system_id: str | None = None
    discipline: str | None = None
    location: str | None = None
    evidence: tuple[EvidenceBody, ...] = ()


class AssetBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    system_id: str
    equipment_tag: str
    equipment_type: str
    manufacturer: str | None = None
    model: str | None = None
    product_lineage: dict[str, str] = {}
    evidence: tuple[EvidenceBody, ...] = ()


class RequirementBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    system_id: str | None = None
    evidence: tuple[EvidenceBody, ...]


class ChecklistBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    system_id: str
    title: str
    items: tuple[dict, ...]
    asset_id: str | None = None


class ProcedureBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    system_id: str
    title: str
    steps: tuple[dict, ...]
    evidence: tuple[EvidenceBody, ...] = ()
    procedure_id: str | None = None


class TestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    procedure_revision_id: str
    system_id: str
    test_date: date
    expected: tuple[str, ...]
    reported: tuple[str, ...]
    outcome: str
    evidence: tuple[EvidenceBody, ...] = ()
    retest_of_id: str | None = None


class DeficiencyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    system_id: str
    title: str
    description: str
    evidence: tuple[EvidenceBody, ...]


class TransitionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: DeficiencyStatus
    actor: str
    rationale: str = ""
    evidence: tuple[EvidenceBody, ...] = ()


class PackageBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    package_type: str
    item_types: tuple[str, ...]
    system_id: str | None = None


class QuestionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str


@router.post("/commissioning/systems", status_code=201)
def create_system(project_id: str, body: SystemBody):
    return _call(
        lambda: _service().create_system(
            project_id,
            body.name,
            parent_system_id=body.parent_system_id,
            discipline=body.discipline,
            location=body.location,
            evidence=tuple(x.value() for x in body.evidence),
        )
    )


@router.get("/commissioning/systems")
def systems(project_id: str):
    return _call(lambda: _service().repository.list("systems", project_id))


@router.post("/commissioning/assets", status_code=201)
def create_asset(project_id: str, body: AssetBody):
    return _call(
        lambda: _service().create_asset(
            project_id,
            body.system_id,
            body.equipment_tag,
            body.equipment_type,
            manufacturer=body.manufacturer,
            model=body.model,
            product_lineage=body.product_lineage,
            evidence=tuple(x.value() for x in body.evidence),
        )
    )


@router.get("/commissioning/assets")
def assets(project_id: str):
    return _call(lambda: _service().repository.list("assets", project_id))


@router.post("/commissioning/requirements/extract")
def requirements(project_id: str, body: RequirementBody):
    return _call(
        lambda: _service().extract_requirements(
            project_id, tuple(x.value() for x in body.evidence), system_id=body.system_id
        )
    )


@router.post("/commissioning/checklists", status_code=201)
def checklist(project_id: str, body: ChecklistBody):
    return _call(
        lambda: _service().create_checklist(
            project_id, body.system_id, body.title, body.items, asset_id=body.asset_id
        )
    )


@router.post("/commissioning/test-procedures", status_code=201)
def procedure(project_id: str, body: ProcedureBody):
    return _call(
        lambda: _service().create_procedure(
            project_id,
            body.system_id,
            body.title,
            body.steps,
            tuple(x.value() for x in body.evidence),
            procedure_id=body.procedure_id,
        )
    )


@router.post("/commissioning/test-executions", status_code=201)
def execution(project_id: str, body: TestBody):
    return _call(
        lambda: _service().record_test(
            project_id,
            body.procedure_revision_id,
            body.system_id,
            body.test_date,
            body.expected,
            body.reported,
            body.outcome,
            tuple(x.value() for x in body.evidence),
            retest_of_id=body.retest_of_id,
        )
    )


@router.post("/commissioning/deficiencies", status_code=201)
def deficiency(project_id: str, body: DeficiencyBody):
    return _call(
        lambda: _service().create_deficiency(
            project_id,
            body.system_id,
            body.title,
            body.description,
            tuple(x.value() for x in body.evidence),
        )
    )


@router.post("/commissioning/deficiencies/{deficiency_id}/transition")
def transition(project_id: str, deficiency_id: str, body: TransitionBody):
    return _call(
        lambda: _service().transition_deficiency(
            project_id,
            deficiency_id,
            body.status,
            body.actor,
            evidence=tuple(x.value() for x in body.evidence),
            rationale=body.rationale,
        )
    )


@router.post("/commissioning/systems/{system_id}/readiness")
def readiness(project_id: str, system_id: str, purpose: str = "startup"):
    return _call(lambda: _service().assess_readiness(project_id, system_id, purpose))


@router.post("/turnover/packages", status_code=201)
def package(project_id: str, body: PackageBody):
    return _call(
        lambda: _service().create_turnover_package(
            project_id, body.package_type, body.item_types, system_id=body.system_id
        )
    )


@router.get("/commissioning/dashboard")
def commissioning_dashboard(project_id: str):
    return _call(lambda: _service().commissioning_dashboard(project_id))


@router.get("/turnover/dashboard")
def turnover_dashboard(project_id: str):
    return _call(lambda: _service().turnover_dashboard(project_id))


@router.get("/commissioning/search")
def search(project_id: str, query: str):
    return _call(lambda: _service().search(project_id, query))


@router.post("/commissioning/questions")
def question(project_id: str, body: QuestionBody):
    return _call(lambda: CommissioningQuestionService(_service()).answer(project_id, body.question))
