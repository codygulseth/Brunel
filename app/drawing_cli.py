"""Drawing Intelligence CLI adapter."""

from datetime import date
from pathlib import Path
from config import get_settings
from storage import JsonDocumentRepository
from drawing_intelligence.repository import JsonDrawingRepository
from drawing_intelligence.service import DrawingIntelligenceService
from drawing_intelligence.rendering import PopplerPageRenderer

COMMANDS = {
    "drawing-set-ingest",
    "drawing-set-list",
    "drawing-set-show",
    "drawing-set-analyze",
    "drawing-sheet-list",
    "drawing-sheet-show",
    "drawing-metadata-review",
    "drawing-index-show",
    "drawing-validation",
    "drawing-references",
    "drawing-reference-graph",
    "drawing-sheet-ocr",
    "drawing-set-compare",
    "drawing-search",
}


def register_drawing_commands(commands):
    p = commands.add_parser("drawing-set-ingest")
    p.add_argument("--project-id", required=True)
    p.add_argument("--file", required=True, type=Path)
    p.add_argument("--title")
    p.add_argument("--revision")
    p.add_argument("--issue-date", type=date.fromisoformat)
    p.add_argument("--predecessor-revision-id")
    p.add_argument("--title-block-template-id")
    p = commands.add_parser("drawing-set-list")
    p.add_argument("--project-id", required=True)
    for name in (
        "drawing-set-show",
        "drawing-set-analyze",
        "drawing-sheet-list",
        "drawing-index-show",
        "drawing-validation",
        "drawing-reference-graph",
    ):
        p = commands.add_parser(name)
        p.add_argument("--project-id", required=True)
        p.add_argument("--revision-id", required=True)
        p.add_argument("--discipline")
    for name in ("drawing-sheet-show", "drawing-references", "drawing-sheet-ocr"):
        p = commands.add_parser(name)
        p.add_argument("--project-id", required=True)
        p.add_argument("--sheet-revision-id", required=True)
    p = commands.add_parser("drawing-metadata-review")
    p.add_argument("--project-id", required=True)
    p.add_argument("--sheet-revision-id", required=True)
    p.add_argument("--sheet-number")
    p.add_argument("--sheet-title")
    p.add_argument("--discipline")
    p.add_argument("--reviewer-id", default="local-user")
    p = commands.add_parser("drawing-set-compare")
    p.add_argument("--project-id", required=True)
    p.add_argument("--old-revision-id", required=True)
    p.add_argument("--new-revision-id", required=True)
    p.add_argument("--output", type=Path)
    p = commands.add_parser("drawing-search")
    p.add_argument("--project-id", required=True)
    p.add_argument("--query", required=True)
    p.add_argument("--revision-id")


def run_drawing_command(args, settings=None):
    settings = settings or get_settings()
    root = settings.data_directory
    service = DrawingIntelligenceService(
        JsonDocumentRepository(root / "ingested"),
        JsonDrawingRepository(root / "drawing-intelligence"),
        renderer=PopplerPageRenderer(root / "drawing-intelligence" / "renders"),
    )
    repo = service.repository
    if args.command == "drawing-set-ingest":
        value = service.ingest(
            project_id=args.project_id,
            file_path=args.file,
            set_title=args.title,
            revision_label=args.revision,
            issue_date=args.issue_date,
            predecessor_revision_id=args.predecessor_revision_id,
            title_block_template_id=args.title_block_template_id,
        )
    elif args.command == "drawing-set-list":
        value = [a.revision for a in repo.list_analyses(args.project_id)]
    elif args.command in {"drawing-set-show", "drawing-set-analyze"}:
        value = repo.get_analysis(args.project_id, args.revision_id)
    elif args.command == "drawing-sheet-list":
        value = repo.get_analysis(args.project_id, args.revision_id).sheets
    elif args.command == "drawing-index-show":
        value = repo.get_analysis(args.project_id, args.revision_id).index
    elif args.command == "drawing-validation":
        value = repo.get_analysis(args.project_id, args.revision_id).validation
    elif args.command == "drawing-reference-graph":
        value = repo.get_analysis(args.project_id, args.revision_id).graph
    elif args.command in {"drawing-sheet-show", "drawing-references"}:
        a = service._find_sheet(args.project_id, args.sheet_revision_id)
        value = (
            next(s for s in a.sheets if s.sheet_revision_id == args.sheet_revision_id)
            if args.command == "drawing-sheet-show"
            else [r for r in a.references if r.source_sheet_revision_id == args.sheet_revision_id]
        )
    elif args.command == "drawing-sheet-ocr":
        value = service.request_ocr(args.project_id, args.sheet_revision_id)
    elif args.command == "drawing-metadata-review":
        value = service.review_metadata(
            args.project_id,
            args.sheet_revision_id,
            {
                k: v
                for k, v in {
                    "sheet_number": args.sheet_number,
                    "sheet_title": args.sheet_title,
                    "discipline": args.discipline,
                }.items()
                if v is not None
            },
            args.reviewer_id,
        )
    elif args.command == "drawing-search":
        value = service.search(args.project_id, args.query, revision_id=args.revision_id)
    else:
        value = service.compare(args.project_id, args.old_revision_id, args.new_revision_id)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(value.model_dump_json(indent=2), encoding="utf-8")
    if value is None:
        print("Not found")
        return 1
    print(
        value.model_dump_json(indent=2)
        if hasattr(value, "model_dump_json")
        else "\n".join(x.model_dump_json() for x in value)
        if isinstance(value, (list, tuple))
        else str(value)
    )
    return 0
