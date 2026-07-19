import argparse
from datetime import date
from pathlib import Path
from config.settings import Settings
from field_intelligence.models import ReportStatus
from field_intelligence.qa import FieldQuestionService
from field_intelligence.repository import JsonFieldRepository
from field_intelligence.service import FieldIntelligenceService

COMMANDS = {
    "daily-report-create",
    "daily-report-ingest",
    "daily-report-analyze",
    "daily-observations",
    "daily-observation-review",
    "daily-report-draft",
    "daily-report-issue",
    "field-dashboard",
    "weekly-field-summary",
    "field-search",
    "field-ask",
}


def register_field_commands(commands):
    p = commands.add_parser("daily-report-create")
    p.add_argument("--project-id", required=True)
    p.add_argument("--date", required=True, type=date.fromisoformat)
    p = commands.add_parser("daily-report-ingest")
    p.add_argument("--project-id", required=True)
    p.add_argument("--date", required=True, type=date.fromisoformat)
    p.add_argument("--file", required=True, type=Path)
    p = commands.add_parser("daily-report-analyze")
    p.add_argument("--project-id", required=True)
    p.add_argument("--revision-id", required=True)
    p = commands.add_parser("daily-observations")
    p.add_argument("--project-id", required=True)
    p.add_argument("--report-id", required=True)
    p = commands.add_parser("daily-observation-review")
    p.add_argument("--project-id", required=True)
    p.add_argument("--observation-id", required=True)
    p.add_argument("--decision", required=True)
    p = commands.add_parser("daily-report-draft")
    p.add_argument("--project-id", required=True)
    p.add_argument("--report-id", required=True)
    p.add_argument("--output", type=Path)
    p = commands.add_parser("daily-report-issue")
    p.add_argument("--project-id", required=True)
    p.add_argument("--report-id", required=True)
    p = commands.add_parser("field-dashboard")
    p.add_argument("--project-id", required=True)
    p = commands.add_parser("weekly-field-summary")
    p.add_argument("--project-id", required=True)
    p.add_argument("--week-start", required=True, type=date.fromisoformat)
    p = commands.add_parser("field-search")
    p.add_argument("--project-id", required=True)
    p.add_argument("--query", required=True)
    p = commands.add_parser("field-ask")
    p.add_argument("--project-id", required=True)
    p.add_argument("--question", required=True)


def run_field_command(args: argparse.Namespace, settings: Settings) -> int:
    s = FieldIntelligenceService(
        JsonFieldRepository(settings.data_directory / "field-intelligence")
    )
    p = args.project_id
    try:
        if args.command == "daily-report-create":
            print(s.create_report(p, args.date)[0].model_dump_json(indent=2))
        elif args.command == "daily-report-ingest":
            print(s.ingest(p, args.date, args.file)[1].model_dump_json(indent=2))
        elif args.command == "daily-report-analyze":
            for x in s.analyze(p, args.revision_id):
                print(x.model_dump_json())
        elif args.command == "daily-observations":
            for x in s.repository.list("observations", p):
                if x.report_id == args.report_id:
                    print(x.model_dump_json())
        elif args.command == "daily-observation-review":
            print(
                s.review_observation(
                    p, args.observation_id, args.decision, "cli-user"
                ).model_dump_json(indent=2)
            )
        elif args.command == "daily-report-draft":
            text = s.draft(p, args.report_id)
            if args.output:
                args.output.write_text(text, encoding="utf-8")
            else:
                print(text)
        elif args.command == "daily-report-issue":
            report = s._report(p, args.report_id)
            if report.status == ReportStatus.DRAFT:
                s.transition(p, args.report_id, ReportStatus.UNDER_REVIEW, "cli-user")
                s.transition(p, args.report_id, ReportStatus.APPROVED, "cli-user")
            print(
                s.transition(
                    p, args.report_id, ReportStatus.ISSUED_INTERNAL, "cli-user"
                ).model_dump_json(indent=2)
            )
        elif args.command == "field-dashboard":
            print(s.dashboard(p).model_dump_json(indent=2))
        elif args.command == "weekly-field-summary":
            print(s.weekly_summary(p, args.week_start).model_dump_json(indent=2))
        elif args.command == "field-search":
            for x in s.search(p, args.query):
                print(x.model_dump_json())
        elif args.command == "field-ask":
            print(FieldQuestionService(s).answer(p, args.question).model_dump_json(indent=2))
    except (ValueError, OSError) as exc:
        print(f"Field command failed: {exc}")
        return 1
    return 0
