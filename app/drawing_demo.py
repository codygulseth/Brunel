"""Generate and analyze two fully synthetic drawing-set revisions."""

from pathlib import Path
from tempfile import TemporaryDirectory
from reportlab.pdfgen.canvas import Canvas
from drawing_intelligence.rendering import PopplerPageRenderer
from drawing_intelligence.repository import JsonDrawingRepository
from drawing_intelligence.service import DrawingIntelligenceService
from storage import JsonDocumentRepository


def _pdf(path: Path, second: bool) -> None:
    sheets = [
        (
            "G0.01",
            "Cover Sheet and Drawing Index",
            [
                "DRAWING INDEX",
                "G0.01 - Cover Sheet and Drawing Index",
                "A1.01 - Level 1 Floor Plan",
                "A5.01 - Wall Sections",
                "S1.01 - Foundation Plan",
                "M2.01 - Mechanical Floor Plan",
                "E2.01 - Electrical Power Plan",
                "E3.01 - Electrical One-Line Diagram",
                "E6.01 - Electrical Schedules",
            ],
        ),
        ("A1.01", "Level 1 Floor Plan", ["ROOM 105", "SEE SECTION 2/A5.01"]),
        ("A5.01", "Wall Sections", []),
        ("S1.01", "Foundation Plan", []),
        ("M2.01", "Mechanical Floor Plan", ["REFER TO A1.01 FOR ROOM LAYOUT"]),
        (
            "E2.01",
            "Electrical Power Plan",
            ["SEE ONE-LINE DIAGRAM E3.01", "FOR PANEL SCHEDULE SEE E6.01"],
        ),
        ("E3.01", "Electrical One-Line Diagram", ["SWBD-1", "SEE DETAIL 4/E6.01", "SEE E7.01"]),
        ("E6.01", "Electrical Schedules", []),
    ]
    if second:
        sheets = [s for s in sheets if s[0] != "E2.01"]
        sheets.append(("E2.02", "Revised Electrical Power Plan", ["SEE E3.01"]))
        sheets.append(("E7.01", "Electrical Details", ["DETAIL 4"]))
        sheets = [
            (n, "Electrical One-Line and Riser Diagram" if n == "E3.01" else t, lines)
            for n, t, lines in sheets
        ]
    c = Canvas(str(path), pagesize=(792, 612))
    for number, title, lines in sheets:
        c.drawString(40, 560, f"SHEET: {number}")
        c.drawString(40, 540, f"SHEET TITLE: {title}")
        for i, line in enumerate(lines):
            c.drawString(40, 500 - i * 18, line)
        c.rect(500, 40, 250, 100)
        c.showPage()
    c.save()


def main() -> int:
    with TemporaryDirectory() as temp:
        root = Path(temp)
        one = root / "revision-1.pdf"
        two = root / "revision-2.pdf"
        _pdf(one, False)
        _pdf(two, True)
        service = DrawingIntelligenceService(
            JsonDocumentRepository(root / "documents"),
            JsonDrawingRepository(root / "drawing"),
            renderer=PopplerPageRenderer(root / "renders"),
        )
        old = service.ingest(
            project_id="synthetic-demo",
            file_path=one,
            set_title="Synthetic Drawing Set",
            revision_label="1",
        )
        new = service.ingest(
            project_id="synthetic-demo",
            file_path=two,
            set_title="Synthetic Drawing Set",
            revision_label="2",
            predecessor_revision_id=old.revision.revision_id,
        )
        comparison = service.compare(
            "synthetic-demo", old.revision.revision_id, new.revision.revision_id
        )
        print(
            f"Revision 1: {len(old.sheets)} sheets, {len(old.references)} references, {len(old.validation.issues)} issues"
        )
        print(
            f"Revision 2: {len(new.sheets)} sheets, {len(new.references)} references, {len(new.validation.issues)} issues"
        )
        print(f"Comparison: {len(comparison.changes)} changes; visual meaning was not inferred")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
