# mypy: disable-error-code=no-untyped-def
"""CLI adapter for revision-review workflows."""

import argparse
from datetime import date

from change_workflow.dashboard import ProjectChangeDashboardService
from change_workflow.models import (
    ActorReference,
    ChangeDisposition,
    ChangeStatus,
    NoteType,
    RelationshipType,
    ReviewerReference,
    WorkflowType,
)
from change_workflow.repository import JsonChangeWorkflowRepository
from change_workflow.service import ProjectChangeService
from change_workflow.staleness import ChangeRegenerationService
from config.settings import Settings
from revision_intelligence.repository import JsonComparisonRepository
from revision_intelligence.service import RevisionComparisonService
from storage import JsonDocumentRepository

COMMANDS = {
    "change-register-generate",
    "change-list",
    "change-show",
    "change-assign",
    "change-unassign",
    "change-transition",
    "change-disposition",
    "change-note",
    "change-link",
    "change-unlink",
    "change-create-related",
    "change-resolve",
    "change-dashboard",
    "comparison-stale-check",
}


def register_change_commands(commands) -> None:
    generate = commands.add_parser("change-register-generate")
    generate.add_argument("--project-id", required=True)
    generate.add_argument("--comparison-id", required=True)
    listing = commands.add_parser("change-list")
    listing.add_argument("--project-id", required=True)
    listing.add_argument("--status", choices=[x.value for x in ChangeStatus])
    show = commands.add_parser("change-show")
    show.add_argument("--project-id", required=True)
    show.add_argument("--change-id", required=True)
    assign = commands.add_parser("change-assign")
    _change_ids(assign)
    assign.add_argument("--assignee-id", required=True)
    assign.add_argument("--assignee-name", required=True)
    assign.add_argument("--due-date", type=date.fromisoformat)
    assign.add_argument("--discipline")
    assign.add_argument("--note")
    unassign = commands.add_parser("change-unassign")
    _change_ids(unassign)
    unassign.add_argument("--reason")
    transition = commands.add_parser("change-transition")
    _change_ids(transition)
    transition.add_argument("--status", choices=[x.value for x in ChangeStatus], required=True)
    transition.add_argument("--reason")
    disposition = commands.add_parser("change-disposition")
    _change_ids(disposition)
    disposition.add_argument(
        "--disposition", choices=[x.value for x in ChangeDisposition], required=True
    )
    disposition.add_argument("--note", required=True)
    note = commands.add_parser("change-note")
    _change_ids(note)
    note.add_argument("--text", required=True)
    note.add_argument("--type", choices=[x.value for x in NoteType], default="general")
    link = commands.add_parser("change-link")
    _change_ids(link)
    link.add_argument("--type", choices=[x.value for x in WorkflowType], required=True)
    link.add_argument("--reference", required=True)
    link.add_argument(
        "--relationship", choices=[x.value for x in RelationshipType], default="related_to"
    )
    link.add_argument("--url")
    unlink = commands.add_parser("change-unlink")
    _change_ids(unlink)
    unlink.add_argument("--link-id", required=True)
    related = commands.add_parser("change-create-related")
    _change_ids(related)
    related.add_argument("--type", choices=[x.value for x in WorkflowType], required=True)
    resolve = commands.add_parser("change-resolve")
    _change_ids(resolve)
    resolve.add_argument("--summary", required=True)
    dashboard = commands.add_parser("change-dashboard")
    dashboard.add_argument("--project-id", required=True)
    stale = commands.add_parser("comparison-stale-check")
    stale.add_argument("--project-id", required=True)
    stale.add_argument("--comparison-id", required=True)


def _change_ids(parser) -> None:
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--change-id", required=True)


def run_change_command(args: argparse.Namespace, settings: Settings) -> int:
    repository = JsonChangeWorkflowRepository(settings.data_directory / "change-workflow")
    service = ProjectChangeService(repository)
    actor = ActorReference(id="cli-user", display_name="CLI User")
    if args.command == "change-register-generate":
        comparison = JsonComparisonRepository(
            settings.data_directory / "revision-intelligence"
        ).get(args.comparison_id)
        if comparison is None or comparison.project_id != args.project_id:
            print("Comparison not found in requested project.")
            return 1
        result = service.generate_register(comparison, actor)
        print(result.model_dump_json(indent=2))
        return 0
    if args.command == "change-list":
        items = repository.list_changes(args.project_id)
        if args.status:
            items = tuple(i for i in items if i.status.value == args.status)
        for item in items:
            print(f"{item.id}\t{item.priority.value}\t{item.status.value}\t{item.title}")
        return 0
    if args.command == "change-show":
        print(service.get(args.project_id, args.change_id).model_dump_json(indent=2))
        return 0
    if args.command == "change-assign":
        item = service.assign(
            args.project_id,
            args.change_id,
            ReviewerReference(
                id=args.assignee_id, display_name=args.assignee_name, discipline=args.discipline
            ),
            actor,
            due_date=args.due_date,
            note=args.note,
        )
        print(f"Assigned {item.id} to {args.assignee_name}.")
        return 0
    if args.command == "change-unassign":
        service.unassign(args.project_id, args.change_id, actor, reason=args.reason)
        print(f"Unassigned {args.change_id}.")
        return 0
    if args.command == "change-transition":
        service.transition(
            args.project_id, args.change_id, ChangeStatus(args.status), actor, reason=args.reason
        )
        print(f"Transitioned {args.change_id} to {args.status}.")
        return 0
    if args.command == "change-disposition":
        service.disposition(
            args.project_id, args.change_id, ChangeDisposition(args.disposition), actor, args.note
        )
        print(f"Disposition recorded: {args.disposition}.")
        return 0
    if args.command == "change-note":
        service.add_note(args.project_id, args.change_id, args.text, actor, NoteType(args.type))
        print("Note added.")
        return 0
    if args.command == "change-link":
        service.add_link(
            args.project_id,
            args.change_id,
            WorkflowType(args.type),
            args.reference,
            RelationshipType(args.relationship),
            actor,
            url=args.url,
        )
        print("Workflow link added.")
        return 0
    if args.command == "change-unlink":
        service.remove_link(args.project_id, args.change_id, args.link_id, actor)
        print(f"Removed link {args.link_id}.")
        return 0
    if args.command == "change-create-related":
        related_item = service.create_related_item(
            args.project_id, args.change_id, WorkflowType(args.type), actor
        )
        print(f"Related item: {related_item.id}")
        return 0
    if args.command == "change-resolve":
        service.transition(
            args.project_id, args.change_id, ChangeStatus.RESOLVED, actor, resolution=args.summary
        )
        print("Change resolved.")
        return 0
    if args.command == "change-dashboard":
        print(
            ProjectChangeDashboardService(repository, settings.workflow.due_soon_days)
            .build(args.project_id)
            .model_dump_json(indent=2)
        )
        return 0
    if args.command == "comparison-stale-check":
        comparison_repository = JsonComparisonRepository(
            settings.data_directory / "revision-intelligence"
        )
        comparison = comparison_repository.get(args.comparison_id)
        if comparison is None or comparison.project_id != args.project_id:
            print("Comparison not found in requested project.")
            return 1
        comparison_service = RevisionComparisonService(
            JsonDocumentRepository(settings.data_directory / "ingested"),
            comparison_repository,
        )
        assessment = ChangeRegenerationService(comparison_service, service).assess(comparison)
        print(assessment.model_dump_json(indent=2))
        return 0
    return 1
