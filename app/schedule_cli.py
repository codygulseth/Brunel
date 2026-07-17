"""CLI adapter for Schedule Intelligence."""

import argparse
from datetime import date, timedelta
from pathlib import Path
from config.settings import Settings
from schedule_intelligence.models import ScheduleType
from schedule_intelligence.reporting import comparison_markdown, register_markdown
from schedule_intelligence.qa import ScheduleQuestionService
from schedule_intelligence.repository import JsonScheduleRepository
from schedule_intelligence.service import ScheduleIntelligenceService

COMMANDS = {
    "schedule-import",
    "schedule-list",
    "schedule-show",
    "schedule-analyze",
    "schedule-quality",
    "schedule-activities",
    "schedule-activity-show",
    "schedule-lineage-review",
    "schedule-compare",
    "schedule-lookahead",
    "schedule-dashboard",
    "schedule-synchronization-proposals",
    "schedule-synchronization-review",
    "schedule-search",
    "schedule-ask",
}


def register_schedule_commands(commands):
    p = commands.add_parser("schedule-import")
    p.add_argument("--project-id", required=True)
    p.add_argument("--file", required=True, type=Path)
    p.add_argument("--name", required=True)
    p.add_argument("--type", choices=[x.value for x in ScheduleType], default="update")
    p.add_argument("--revision")
    p.add_argument("--predecessor-revision-id")
    p.add_argument("--calendar-day-fallback", action="store_true")
    p = commands.add_parser("schedule-list")
    p.add_argument("--project-id", required=True)
    for name in (
        "schedule-show",
        "schedule-analyze",
        "schedule-quality",
        "schedule-activities",
        "schedule-lookahead",
    ):
        p = commands.add_parser(name)
        p.add_argument("--project-id", required=True)
        p.add_argument("--revision-id", required=True)
        if name == "schedule-lookahead":
            p.add_argument("--weeks", type=int, default=6)
            p.add_argument(
                "--date-field", choices=("planned", "forecast", "early"), default="planned"
            )
    p = commands.add_parser("schedule-activity-show")
    p.add_argument("--project-id", required=True)
    p.add_argument("--activity-revision-id", required=True)
    p = commands.add_parser("schedule-lineage-review")
    p.add_argument("--project-id", required=True)
    p.add_argument("--lineage-id", required=True)
    p.add_argument("--decision", required=True)
    p = commands.add_parser("schedule-compare")
    p.add_argument("--project-id", required=True)
    p.add_argument("--old-revision-id", required=True)
    p.add_argument("--new-revision-id", required=True)
    p.add_argument("--output", type=Path)
    p = commands.add_parser("schedule-dashboard")
    p.add_argument("--project-id", required=True)
    p.add_argument("--revision-id")
    p = commands.add_parser("schedule-synchronization-proposals")
    p.add_argument("--project-id", required=True)
    p = commands.add_parser("schedule-synchronization-review")
    p.add_argument("--project-id", required=True)
    p.add_argument("--proposal-id", required=True)
    p.add_argument("--decision", required=True)
    p = commands.add_parser("schedule-search")
    p.add_argument("--project-id", required=True)
    p.add_argument("--query", required=True)
    p.add_argument("--revision-id")
    p = commands.add_parser("schedule-ask")
    p.add_argument("--project-id", required=True)
    p.add_argument("--question", required=True)


def run_schedule_command(args: argparse.Namespace, settings: Settings) -> int:
    service = ScheduleIntelligenceService(
        JsonScheduleRepository(settings.data_directory / "schedule-intelligence")
    )
    project = args.project_id
    try:
        if args.command == "schedule-import":
            print(
                service.import_schedule(
                    project,
                    args.file,
                    args.name,
                    ScheduleType(args.type),
                    revision_label=args.revision,
                    predecessor_revision_id=args.predecessor_revision_id,
                    calendar_fallback=args.calendar_day_fallback,
                ).model_dump_json(indent=2)
            )
        elif args.command == "schedule-list":
            for x in service.repository.list("schedules", project):
                print(f"{x.id}\t{x.name}\t{x.current_revision_id}")
        elif args.command == "schedule-show":
            print(
                service.repository.get("revisions", args.revision_id, project).model_dump_json(
                    indent=2
                )
            )
        elif args.command in {"schedule-analyze", "schedule-quality"}:
            print(service.assess_quality(project, args.revision_id).model_dump_json(indent=2))
        elif args.command == "schedule-activities":
            print(register_markdown(service.activities(project, args.revision_id)))
        elif args.command == "schedule-activity-show":
            print(
                service.repository.get(
                    "activities", args.activity_revision_id, project
                ).model_dump_json(indent=2)
            )
        elif args.command == "schedule-lineage-review":
            print(
                service.review_lineage(
                    project, args.lineage_id, args.decision, "cli-user"
                ).model_dump_json(indent=2)
            )
        elif args.command == "schedule-compare":
            rendered = comparison_markdown(
                service.compare(project, args.old_revision_id, args.new_revision_id)
            )
            if args.output:
                args.output.write_text(rendered, encoding="utf-8")
            else:
                print(rendered)
        elif args.command == "schedule-lookahead":
            print(
                register_markdown(
                    service.lookahead(
                        project,
                        args.revision_id,
                        date.today(),
                        date.today() + timedelta(weeks=args.weeks),
                        args.date_field,
                    )
                )
            )
        elif args.command == "schedule-dashboard":
            print(service.dashboard(project, args.revision_id).model_dump_json(indent=2))
        elif args.command == "schedule-synchronization-proposals":
            for x in service.repository.list("proposals", project):
                print(x.model_dump_json())
        elif args.command == "schedule-synchronization-review":
            print(
                service.review_proposal(
                    project, args.proposal_id, args.decision, "cli-user"
                ).model_dump_json(indent=2)
            )
        elif args.command == "schedule-search":
            print(register_markdown(service.search(project, args.query, args.revision_id)))
        elif args.command == "schedule-ask":
            print(
                ScheduleQuestionService(service)
                .answer(project, args.question)
                .model_dump_json(indent=2)
            )
    except (ValueError, OSError, AttributeError) as exc:
        print(f"Schedule command failed: {exc}")
        return 1
    return 0
