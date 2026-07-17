from pathlib import Path
from reportlab.pdfgen.canvas import Canvas
from fastapi.testclient import TestClient

from app.api import app
from drawing_intelligence.models import NormalizedBox, OCRTextBlock, PresenceStatus
from drawing_intelligence.ocr import SyntheticOCRProvider
from drawing_intelligence.qa import DrawingQuestionService
from drawing_intelligence.rendering import NullPageRenderer, PopplerPageRenderer
from drawing_intelligence.repository import JsonDrawingRepository
from drawing_intelligence.service import DrawingIntelligenceService
from drawing_intelligence.templates import TitleBlockTemplateRegistry
from storage import JsonDocumentRepository


def make_set(path: Path, revision: int = 1) -> None:
    pages = [
        (
            "G0.01",
            "Cover Sheet and Drawing Index",
            [
                "DRAWING INDEX",
                "G0.01 - Cover Sheet and Drawing Index",
                "A1.01 - Level 1 Floor Plan",
                "E3.01 - Electrical One-Line Diagram",
                "E7.01 - Electrical Details",
            ],
        ),
        (
            "A1.01",
            "Level 1 Floor Plan",
            ["ROOM 105", "SEE SECTION 2/A5.01", "KEYNOTES", "1 - EXISTING WALL", "KEYNOTE 1"],
        ),
        (
            "E3.01",
            "Electrical One-Line Diagram"
            if revision == 1
            else "Electrical One-Line and Riser Diagram",
            ["SWBD-1", "SEE DETAIL 4/E7.01"],
        ),
        ("E3.01", "Duplicate Test", []),
    ]
    if revision == 2:
        pages.insert(3, ("E7.01", "Electrical Details", ["DETAIL 4"]))
        pages.append(("E2.02", "Revised Electrical Power Plan", ["SEE E3.01"]))
    c = Canvas(str(path), pagesize=(792, 612))
    for number, title, lines in pages:
        c.drawString(50, 550, f"SHEET: {number}")
        c.drawString(50, 530, f"SHEET TITLE: {title}")
        c.drawString(50, 510, f"REV: {revision}")
        for i, line in enumerate(lines):
            c.drawString(50, 470 - i * 20, line)
        c.rect(500, 50, 250, 100, stroke=1, fill=0)
        c.showPage()
    c.save()


def service(tmp_path, ocr=None):
    return DrawingIntelligenceService(
        JsonDocumentRepository(tmp_path / "docs"),
        JsonDrawingRepository(tmp_path / "drawings"),
        renderer=NullPageRenderer(),
        ocr_provider=ocr,
    )


def test_ingestion_index_validation_graph_search_review_and_ocr(tmp_path):
    pdf = tmp_path / "rev1.pdf"
    make_set(pdf)
    svc = service(
        tmp_path,
        SyntheticOCRProvider(
            (
                OCRTextBlock(
                    text="image text",
                    box=NormalizedBox(x_min=0, y_min=0, x_max=0.2, y_max=0.2),
                    confidence=0.6,
                ),
            )
        ),
    )
    analysis = svc.ingest(project_id="p1", file_path=pdf, set_title="Synthetic", revision_label="1")
    assert analysis.revision.total_page_count == 4 and analysis.revision.drawing_index_present
    assert analysis.title_block_template is not None
    assert analysis.title_block_human_review_required
    assert analysis.keynotes[0].legend is not None
    assert analysis.keynotes[0].occurrences[0].resolved
    statuses = {i.status for i in analysis.validation.issues}
    assert PresenceStatus.DUPLICATE_SHEET in statuses and PresenceStatus.MISSING_SHEET in statuses
    assert any(not r.resolved and r.target_sheet_number == "E7.01" for r in analysis.graph.edges)
    assert svc.search("p1", "SWBD-1")[0].sheet_number == "E3.01"
    sheet = analysis.sheets[1]
    reviewed = svc.review_metadata(
        "p1", sheet.sheet_revision_id, {"sheet_title": "Confirmed Floor Plan"}, "reviewer"
    )
    assert "sheet_title" in reviewed.human_confirmed_fields
    ocr = svc.request_ocr("p1", sheet.sheet_revision_id)
    assert ocr.successful and ocr.blocks and ocr.warnings
    assert not svc.search("another-project", "SWBD-1")
    answer = DrawingQuestionService(svc.repository).answer("p1", "What is Sheet A1.01?")
    assert answer.sufficient and answer.citations
    limitation = DrawingQuestionService(svc.repository).answer(
        "p1", "What graphical design changed?"
    )
    assert limitation.sufficient and limitation.limitations
    assert svc.repository.list_audit("p1")
    assert svc.repository.list_notifications("p1")


def test_revision_comparison_marks_additions_and_unexplained_change(tmp_path):
    one = tmp_path / "one.pdf"
    two = tmp_path / "two.pdf"
    make_set(one, 1)
    make_set(two, 2)
    svc = service(tmp_path)
    old = svc.ingest(project_id="p", file_path=one, set_title="Set", revision_label="1")
    new = svc.ingest(
        project_id="p",
        file_path=two,
        set_title="Set",
        revision_label="2",
        predecessor_revision_id=old.revision.revision_id,
    )
    comparison = svc.compare("p", old.revision.revision_id, new.revision.revision_id)
    assert any(
        c.change_type == "sheet_added" and c.sheet_number == "E7.01" for c in comparison.changes
    )
    assert any(c.human_visual_review_required for c in comparison.changes)


def test_visual_box_validation_and_openapi():
    assert NormalizedBox(x_min=0, y_min=0, x_max=1, y_max=1).x_max == 1
    schema = TestClient(app).get("/openapi.json").json()
    assert "/projects/{project_id}/drawing-search" in schema["paths"]
    assert "/projects/{project_id}/drawing-ask" in schema["paths"]


def test_title_block_template_and_render_crop(tmp_path):
    template, method, review = TitleBlockTemplateRegistry().select("builtin-bottom")
    assert template.id == "builtin-bottom" and method == "user_selected" and not review
    pdf = tmp_path / "render.pdf"
    make_set(pdf)
    renderer = PopplerPageRenderer(tmp_path / "renders")
    full = renderer.render(pdf, 1, "a" * 64, dpi=72)
    if full.reference is not None:
        cropped = renderer.render(
            pdf,
            1,
            "a" * 64,
            dpi=72,
            crop=NormalizedBox(x_min=0.5, y_min=0.5, x_max=1, y_max=1),
        )
        assert cropped.reference and cropped.width < full.width and cropped.height < full.height
