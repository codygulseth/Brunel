"""Development-only Drawing Intelligence HTTP adapter."""

from datetime import date
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Annotated
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, ConfigDict
from config import get_settings
from storage import JsonDocumentRepository
from drawing_intelligence.models import DrawingDiscipline
from drawing_intelligence.repository import JsonDrawingRepository
from drawing_intelligence.service import DrawingIntelligenceService
from drawing_intelligence.qa import DrawingQuestionService
from drawing_intelligence.rendering import PopplerPageRenderer

router = APIRouter(tags=["drawing-intelligence"])


def _service():
    root = get_settings().data_directory
    return DrawingIntelligenceService(
        JsonDocumentRepository(root / "ingested"),
        JsonDrawingRepository(root / "drawing-intelligence"),
        renderer=PopplerPageRenderer(root / "drawing-intelligence" / "renders"),
    )


def _analysis(project_id, revision_id):
    value = _service().repository.get_analysis(project_id, revision_id)
    if not value:
        raise HTTPException(404, "Drawing-set revision not found in requested project")
    return value


class MetadataReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sheet_number: str | None = None
    sheet_title: str | None = None
    revision: str | None = None
    discipline: DrawingDiscipline | None = None
    reviewer_id: str = "local-user"


class ComparisonRequest(BaseModel):
    old_revision_id: str
    new_revision_id: str


@router.post("/projects/{project_id}/drawing-sets", status_code=201)
async def ingest_set(
    project_id: str,
    file: Annotated[UploadFile, File()],
    set_title: Annotated[str | None, Form()] = None,
    revision: Annotated[str | None, Form()] = None,
    issue_date: Annotated[date | None, Form()] = None,
    title_block_template_id: Annotated[str | None, Form()] = None,
):
    if (
        file.content_type != "application/pdf"
        or not file.filename
        or not file.filename.lower().endswith(".pdf")
    ):
        raise HTTPException(415, "Only PDF drawing sets are accepted")
    payload = await file.read(50 * 1024 * 1024 + 1)
    if len(payload) > 50 * 1024 * 1024:
        raise HTTPException(413, "Drawing set exceeds 50 MiB limit")
    with NamedTemporaryFile(suffix=".pdf", delete=False) as temp:
        temp.write(payload)
        path = Path(temp.name)
    try:
        return _service().ingest(
            project_id=project_id,
            file_path=path,
            set_title=set_title,
            revision_label=revision,
            issue_date=issue_date,
            title_block_template_id=title_block_template_id,
        )
    finally:
        path.unlink(missing_ok=True)


@router.get("/projects/{project_id}/drawing-sets")
def list_sets(project_id: str, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    values = _service().repository.list_analyses(project_id)
    return {
        "items": [x.revision for x in values[offset : offset + limit]],
        "total": len(values),
        "limit": limit,
        "offset": offset,
    }


@router.get("/projects/{project_id}/drawing-sets/{drawing_set_id}")
def get_set(project_id: str, drawing_set_id: str):
    return [
        a.revision
        for a in _service().repository.list_analyses(project_id)
        if a.revision.drawing_set_id == drawing_set_id
    ]


@router.get("/projects/{project_id}/drawing-set-revisions/{revision_id}")
def get_revision(project_id: str, revision_id: str):
    return _analysis(project_id, revision_id).revision


@router.post("/projects/{project_id}/drawing-set-revisions/{revision_id}/analyze")
def analyze(project_id: str, revision_id: str):
    return _analysis(project_id, revision_id)


@router.get("/projects/{project_id}/drawing-set-revisions/{revision_id}/sheets")
def sheets(project_id: str, revision_id: str, discipline: DrawingDiscipline | None = None):
    return [
        s
        for s in _analysis(project_id, revision_id).sheets
        if not discipline or s.discipline == discipline
    ]


@router.get("/projects/{project_id}/drawing-sheets/{sheet_revision_id}")
def sheet(project_id: str, sheet_revision_id: str):
    a = _service()._find_sheet(project_id, sheet_revision_id)
    return next(s for s in a.sheets if s.sheet_revision_id == sheet_revision_id)


@router.patch("/projects/{project_id}/drawing-sheets/{sheet_revision_id}/metadata")
@router.post("/projects/{project_id}/drawing-sheets/{sheet_revision_id}/metadata-review")
def review(project_id: str, sheet_revision_id: str, body: MetadataReviewRequest):
    return _service().review_metadata(
        project_id,
        sheet_revision_id,
        body.model_dump(exclude={"reviewer_id"}, exclude_none=True, mode="json"),
        body.reviewer_id,
    )


@router.get("/projects/{project_id}/drawing-sheets/{sheet_revision_id}/references")
def references(project_id: str, sheet_revision_id: str):
    return [
        r
        for r in _service()._find_sheet(project_id, sheet_revision_id).references
        if r.source_sheet_revision_id == sheet_revision_id
    ]


@router.get("/projects/{project_id}/drawing-sheets/{sheet_revision_id}/regions")
def regions(project_id: str, sheet_revision_id: str):
    a = _service()._find_sheet(project_id, sheet_revision_id)
    s = next(x for x in a.sheets if x.sheet_revision_id == sheet_revision_id)
    return [r for r in a.regions if r.page_number == s.source_page_number]


@router.get("/projects/{project_id}/drawing-set-revisions/{revision_id}/validation")
def validation(project_id: str, revision_id: str):
    return _analysis(project_id, revision_id).validation


@router.get("/projects/{project_id}/drawing-set-revisions/{revision_id}/reference-graph")
def graph(project_id: str, revision_id: str):
    return _analysis(project_id, revision_id).graph


@router.get("/projects/{project_id}/drawing-set-revisions/{revision_id}/unresolved-references")
def unresolved(project_id: str, revision_id: str):
    return [r for r in _analysis(project_id, revision_id).references if not r.resolved]


@router.post("/projects/{project_id}/drawing-sheets/{sheet_revision_id}/ocr")
def ocr(project_id: str, sheet_revision_id: str):
    return _service().request_ocr(project_id, sheet_revision_id)


@router.get("/projects/{project_id}/drawing-sheets/{sheet_revision_id}/ocr-results")
def ocr_results(project_id: str, sheet_revision_id: str):
    return _service().repository.list_ocr(project_id, sheet_revision_id)


@router.post("/projects/{project_id}/drawing-set-comparisons", status_code=201)
def compare(project_id: str, body: ComparisonRequest):
    return _service().compare(project_id, body.old_revision_id, body.new_revision_id)


@router.get("/projects/{project_id}/drawing-set-comparisons/{comparison_id}")
def comparison(project_id: str, comparison_id: str):
    v = _service().repository.get_comparison(project_id, comparison_id)
    if not v:
        raise HTTPException(404, "Comparison not found")
    return v


@router.get("/projects/{project_id}/drawing-set-comparisons/{comparison_id}/export")
def comparison_export(project_id: str, comparison_id: str):
    return comparison(project_id, comparison_id)


@router.get("/projects/{project_id}/drawing-search")
def search(
    project_id: str,
    query: str,
    revision_id: str | None = None,
    discipline: DrawingDiscipline | None = None,
):
    return _service().search(project_id, query, revision_id=revision_id, discipline=discipline)


@router.get("/projects/{project_id}/drawing-ask")
def ask_drawing(project_id: str, question: str):
    return DrawingQuestionService(_service().repository).answer(project_id, question)


@router.get("/projects/{project_id}/drawing-audit-events")
def drawing_audit(project_id: str):
    return _service().repository.list_audit(project_id)


@router.get("/projects/{project_id}/drawing-notification-outbox")
def drawing_outbox(project_id: str):
    return _service().repository.list_notifications(project_id)
