"""CLI adapter for meeting/action workflows."""

from datetime import date
from pathlib import Path

from config import get_settings
from meeting_tracking.models import (
    ActionStatus,
    MeetingType,
    MinutesStatus,
    RecordType,
    ReviewStatus,
)
from meeting_tracking.repository import JsonMeetingRepository
from meeting_tracking.service import MeetingTrackingService
from storage import JsonDocumentRepository

COMMANDS = {
    "meeting-create",
    "meeting-series-create",
    "meeting-record-ingest",
    "meeting-analyze",
    "meeting-candidates",
    "meeting-candidate-confirm",
    "meeting-candidate-reject",
    "action-list",
    "action-show",
    "action-assign",
    "action-transition",
    "action-complete",
    "decision-list",
    "decision-confirm",
    "meeting-minutes-draft",
    "meeting-minutes-issue",
    "meeting-record-compare",
    "action-dashboard",
    "meeting-search",
}


def register_meeting_commands(commands):
    p = commands.add_parser("meeting-create")
    p.add_argument("--project-id", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--date", required=True, type=date.fromisoformat)
    p.add_argument("--type", default="other", choices=[x.value for x in MeetingType])
    p.add_argument("--number")
    p.add_argument("--series-id")
    p = commands.add_parser("meeting-series-create")
    p.add_argument("--project-id", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--type", required=True, choices=[x.value for x in MeetingType])
    p.add_argument("--recurrence")
    p = commands.add_parser("meeting-record-ingest")
    p.add_argument("--project-id", required=True)
    p.add_argument("--meeting-id", required=True)
    p.add_argument("--file", required=True, type=Path)
    p.add_argument("--record-type", required=True, choices=[x.value for x in RecordType])
    p.add_argument("--predecessor-revision-id")
    p = commands.add_parser("meeting-analyze")
    p.add_argument("--project-id", required=True)
    p.add_argument("--record-revision-id", required=True)
    p = commands.add_parser("meeting-candidates")
    p.add_argument("--project-id", required=True)
    p.add_argument("--meeting-id", required=True)
    for name, status in (
        ("meeting-candidate-confirm", "confirmed"),
        ("meeting-candidate-reject", "rejected"),
    ):
        p = commands.add_parser(name)
        p.set_defaults(review_status=status)
        p.add_argument("--project-id", required=True)
        p.add_argument("--candidate-id", required=True)
        p.add_argument("--owner-name")
        p.add_argument("--description")
    p = commands.add_parser("action-list")
    p.add_argument("--project-id", required=True)
    p.add_argument("--status", choices=[x.value for x in ActionStatus])
    p = commands.add_parser("action-show")
    p.add_argument("--project-id", required=True)
    p.add_argument("--action-id", required=True)
    p = commands.add_parser("action-assign")
    p.add_argument("--project-id", required=True)
    p.add_argument("--action-id", required=True)
    p.add_argument("--owner-id", required=True)
    p.add_argument("--owner-name", required=True)
    p = commands.add_parser("action-transition")
    p.add_argument("--project-id", required=True)
    p.add_argument("--action-id", required=True)
    p.add_argument("--status", required=True, choices=[x.value for x in ActionStatus])
    p.add_argument("--reason")
    p = commands.add_parser("action-complete")
    p.add_argument("--project-id", required=True)
    p.add_argument("--action-id", required=True)
    p.add_argument("--resolution", required=True)
    p = commands.add_parser("decision-list")
    p.add_argument("--project-id", required=True)
    p = commands.add_parser("decision-confirm")
    p.add_argument("--project-id", required=True)
    p.add_argument("--decision-id", required=True)
    p = commands.add_parser("meeting-minutes-draft")
    p.add_argument("--project-id", required=True)
    p.add_argument("--meeting-id", required=True)
    p.add_argument("--output", type=Path)
    p = commands.add_parser("meeting-minutes-issue")
    p.add_argument("--project-id", required=True)
    p.add_argument("--minutes-id", required=True)
    p = commands.add_parser("meeting-record-compare")
    p.add_argument("--project-id", required=True)
    p.add_argument("--old-record-revision-id", required=True)
    p.add_argument("--new-record-revision-id", required=True)
    p = commands.add_parser("action-dashboard")
    p.add_argument("--project-id", required=True)
    p = commands.add_parser("meeting-search")
    p.add_argument("--project-id", required=True)
    p.add_argument("--query", required=True)


def run_meeting_command(args, settings=None):
    settings = settings or get_settings()
    root = settings.data_directory
    service = MeetingTrackingService(
        JsonDocumentRepository(root / "ingested"), JsonMeetingRepository(root / "meeting-tracking")
    )
    c = args.command
    if c == "meeting-create":
        value = service.create_meeting(
            args.project_id,
            args.title,
            args.date,
            meeting_type=MeetingType(args.type),
            meeting_number=args.number,
            series_id=args.series_id,
        )
    elif c == "meeting-series-create":
        value = service.create_series(
            args.project_id, args.name, MeetingType(args.type), recurrence=args.recurrence
        )
    elif c == "meeting-record-ingest":
        value = service.ingest_record(
            args.project_id,
            args.meeting_id,
            args.file,
            RecordType(args.record_type),
            predecessor_revision_id=args.predecessor_revision_id,
        )
    elif c == "meeting-analyze":
        value = service.analyze(args.project_id, args.record_revision_id)
    elif c == "meeting-candidates":
        value = tuple(
            x
            for x in service.repository.list("candidates", args.project_id)
            if x.meeting_id == args.meeting_id
        )
    elif c.startswith("meeting-candidate-"):
        value = service.review_candidate(
            args.project_id,
            args.candidate_id,
            ReviewStatus(args.review_status),
            "local-user",
            description=args.description,
            owner_name=args.owner_name,
        )
    elif c == "action-list":
        value = tuple(
            x
            for x in service.repository.list("actions", args.project_id)
            if not args.status or x.status == ActionStatus(args.status)
        )
    elif c == "action-show":
        value = service._action(args.project_id, args.action_id)
    elif c == "action-assign":
        value = service.assign_action(
            args.project_id, args.action_id, args.owner_id, args.owner_name, "local-user"
        )
    elif c == "action-transition":
        value = service.transition_action(
            args.project_id,
            args.action_id,
            ActionStatus(args.status),
            "local-user",
            reason=args.reason,
        )
    elif c == "action-complete":
        value = service.transition_action(
            args.project_id,
            args.action_id,
            ActionStatus.COMPLETED,
            "local-user",
            resolution=args.resolution,
        )
    elif c == "decision-list":
        value = service.repository.list("decisions", args.project_id)
    elif c == "decision-confirm":
        value = service.confirm_decision(args.project_id, args.decision_id, "local-user")
    elif c == "meeting-minutes-draft":
        value = service.draft_minutes(args.project_id, args.meeting_id, "local-user")
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(value.markdown, encoding="utf-8")
    elif c == "meeting-minutes-issue":
        value = service.transition_minutes(
            args.project_id, args.minutes_id, MinutesStatus.ISSUED, "local-user"
        )
    elif c == "meeting-record-compare":
        value = service.compare_records(
            args.project_id, args.old_record_revision_id, args.new_record_revision_id
        )
    elif c == "action-dashboard":
        value = service.dashboard(args.project_id)
    else:
        value = service.search(args.project_id, args.query)
    if isinstance(value, tuple):
        print("\n".join(x.model_dump_json() for x in value))
    else:
        print(value.model_dump_json(indent=2))
    return 0
