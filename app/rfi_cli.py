"""CLI adapter for canonical RFI workflows."""

import argparse
from datetime import date
from pathlib import Path
from typing import Any

from change_workflow.models import ActorReference, ReviewerReference
from change_workflow.repository import JsonChangeWorkflowRepository
from config.settings import Settings
from rfi.models import RFIResponseType, RFIReviewDecision, RFIStatus
from rfi.numbering import ProjectRFINumberingService
from rfi.repository import JsonRFIRepository
from rfi.reporting import RFILogService, RFIRenderer
from rfi.service import RFIService
from storage import JsonDocumentRepository

COMMANDS = {
    "rfi-draft",
    "rfi-create",
    "rfi-list",
    "rfi-show",
    "rfi-submit-review",
    "rfi-review",
    "rfi-issue",
    "rfi-response",
    "rfi-close",
    "rfi-log",
    "rfi-dashboard",
    "rfi-export",
    "rfi-demo",
}


def register_rfi_commands(commands: Any) -> None:
    draft = commands.add_parser("rfi-draft")
    draft.add_argument("--project-id", required=True)
    draft.add_argument("--change-id", required=True)
    draft.add_argument("--instructions")
    draft.add_argument("--responsible-party")
    draft.add_argument("--required-date", type=date.fromisoformat)
    create = commands.add_parser("rfi-create")
    create.add_argument("--project-id", required=True)
    create.add_argument("--subject", required=True)
    create.add_argument("--question", required=True)
    create.add_argument("--background", default="")
    create.add_argument("--responsible-party")
    create.add_argument("--required-date", type=date.fromisoformat)
    listing = commands.add_parser("rfi-list")
    listing.add_argument("--project-id", required=True)
    listing.add_argument("--status", choices=[x.value for x in RFIStatus])
    show = commands.add_parser("rfi-show")
    _ids(show)
    submit = commands.add_parser("rfi-submit-review")
    _ids(submit)
    submit.add_argument("--reviewer-id", required=True)
    submit.add_argument("--reviewer-name", default="Reviewer")
    review = commands.add_parser("rfi-review")
    _ids(review)
    review.add_argument("--reviewer-id", required=True)
    review.add_argument("--reviewer-name", default="Reviewer")
    review.add_argument("--decision", choices=[x.value for x in RFIReviewDecision], required=True)
    review.add_argument("--comments")
    issue = commands.add_parser("rfi-issue")
    _ids(issue)
    response = commands.add_parser("rfi-response")
    _ids(response)
    response.add_argument("--response-file", type=Path, required=True)
    response.add_argument("--responding-party", required=True)
    response.add_argument("--type", choices=[x.value for x in RFIResponseType], default="official")
    close = commands.add_parser("rfi-close")
    _ids(close)
    close.add_argument("--resolution", required=True)
    log = commands.add_parser("rfi-log")
    log.add_argument("--project-id", required=True)
    dashboard = commands.add_parser("rfi-dashboard")
    dashboard.add_argument("--project-id", required=True)
    export = commands.add_parser("rfi-export")
    _ids(export)
    export.add_argument("--format", choices=("markdown", "json"), default="markdown")
    export.add_argument("--output", type=Path, required=True)
    demo = commands.add_parser("rfi-demo")
    demo.add_argument("--project-id", default="synthetic-rfi-demo")


def _ids(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--rfi-id", required=True)


def run_rfi_command(args: argparse.Namespace, settings: Settings) -> int:
    if args.command == "rfi-demo":
        from app.rfi_demo import run_synthetic_rfi_demo

        import json

        print(
            json.dumps(run_synthetic_rfi_demo(settings.data_directory, args.project_id), indent=2)
        )
        return 0
    repo = JsonRFIRepository(settings.data_directory / "rfi")
    service = RFIService(
        repo,
        JsonChangeWorkflowRepository(settings.data_directory / "change-workflow"),
        numbering=ProjectRFINumberingService(
            repo, settings.rfi.numbering_prefix, settings.rfi.numbering_digits
        ),
        duplicate_threshold=settings.rfi.duplicate_similarity_threshold,
        assign_number_at_creation=settings.rfi.assign_number_at_creation,
        documents=JsonDocumentRepository(settings.data_directory / "ingested"),
    )
    actor = ActorReference(id="cli-user", display_name="CLI User")
    if args.command == "rfi-draft":
        result = service.draft_from_change(
            args.project_id,
            args.change_id,
            actor,
            instructions=args.instructions,
            responsible_party=args.responsible_party,
            required_date=args.required_date,
        )
        print(result.model_dump_json(indent=2))
        return 0
    if args.command == "rfi-create":
        item = service.create(
            project_id=args.project_id,
            subject=args.subject,
            question=args.question,
            background=args.background,
            actor=actor,
            responsible_party=args.responsible_party,
            required_date=args.required_date,
        )
        print(f"Created {item.number} ({item.id}).")
        return 0
    if args.command == "rfi-list":
        items = RFILogService(repo).list(
            args.project_id, status=RFIStatus(args.status) if args.status else None
        )
        [print(f"{x.number}\t{x.status.value}\t{x.subject}\t{x.id}") for x in items]
        return 0
    if args.command == "rfi-show":
        print(service.get(args.project_id, args.rfi_id).model_dump_json(indent=2))
        return 0
    if args.command == "rfi-submit-review":
        reviewer = ReviewerReference(id=args.reviewer_id, display_name=args.reviewer_name)
        service.assign_reviewer(args.project_id, args.rfi_id, reviewer, actor)
        service.transition(args.project_id, args.rfi_id, RFIStatus.PENDING_INTERNAL_REVIEW, actor)
        print("Submitted for review.")
        return 0
    if args.command == "rfi-review":
        service.review(
            args.project_id,
            args.rfi_id,
            RFIReviewDecision(args.decision),
            ReviewerReference(id=args.reviewer_id, display_name=args.reviewer_name),
            actor,
            args.comments,
        )
        print(f"Review decision: {args.decision}.")
        return 0
    if args.command == "rfi-issue":
        service.transition(args.project_id, args.rfi_id, RFIStatus.ISSUED, actor)
        print("RFI issued internally.")
        return 0
    if args.command == "rfi-response":
        text = args.response_file.resolve().read_text(encoding="utf-8")
        service.record_response(
            args.project_id,
            args.rfi_id,
            actor,
            text=text,
            responding_party=args.responding_party,
            response_type=RFIResponseType(args.type),
        )
        print("Response recorded.")
        return 0
    if args.command == "rfi-close":
        item = service.get(args.project_id, args.rfi_id)
        service.transition(
            args.project_id, args.rfi_id, RFIStatus.CLOSED, actor, resolution=args.resolution
        )
        print(f"Closed {item.number}.")
        return 0
    if args.command == "rfi-log":
        [
            print(f"{x.number}\t{x.status.value}\t{x.subject}")
            for x in RFILogService(repo).list(args.project_id)
        ]
        return 0
    if args.command == "rfi-dashboard":
        print(RFILogService(repo).dashboard(args.project_id).model_dump_json(indent=2))
        return 0
    if args.command == "rfi-export":
        item = service.record_export(args.project_id, args.rfi_id, actor, args.format)
        content = (
            item.model_dump_json(indent=2)
            if args.format == "json"
            else RFIRenderer().markdown(item)
        )
        target = args.output.resolve()
        root = Path.cwd().resolve()
        if target != root and root not in target.parents:
            raise ValueError("Export path must stay within workspace")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        print(f"Exported {target}")
        return 0
    return 1
