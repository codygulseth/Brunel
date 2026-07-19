"""Nested ``brunel p6`` commands for Primavera schedule integration."""

import argparse
from datetime import UTC, datetime, timedelta
from pathlib import Path
from config.settings import Settings
from integration_adapters.reference import TestSecretProvider
from integration_adapters.registry import AdapterRegistry
from integration_adapters.repository import JsonIntegrationRepository
from integration_adapters.service import IntegrationService
from schedule_intelligence.repository import JsonScheduleRepository
from schedule_intelligence.service import ScheduleIntelligenceService
from p6_adapter import PrimaveraP6Adapter, PrimaveraP6Service


COMMANDS = {"p6"}


def register_p6_commands(commands):
    root = commands.add_parser("p6")
    sub = root.add_subparsers(dest="p6_command", required=True)
    sub.add_parser("adapter-info")
    p = sub.add_parser("create-connection")
    p.add_argument("--organization-id", required=True)
    p.add_argument("--project-id", required=True)
    p.add_argument("--name", default="Primavera P6")
    p.add_argument(
        "--transport",
        choices=("xer_file", "p6_xml_file", "test_in_memory", "future_api"),
        required=True,
    )
    p.add_argument("--write-enabled", action="store_true")
    p.add_argument("--actor", default="cli-user")
    for name in ("test-connection", "dashboard"):
        p = sub.add_parser(name)
        _scope(p)
    for name in ("discover-projects", "import-xer", "import-xml"):
        p = sub.add_parser(name)
        _scope(p)
        p.add_argument("--file", required=True, type=Path)
        if name.startswith("import"):
            p.add_argument("--schedule-name")
    p = sub.add_parser("map-project")
    _scope(p)
    p.add_argument("--external-project-id", required=True)
    for name in (
        "list-revisions",
        "list-conflicts",
        "list-export-proposals",
        "list-mapping-candidates",
        "generate-sync-proposals",
    ):
        p = sub.add_parser(name)
        p.add_argument("--organization-id", required=True)
        p.add_argument("--project-id", required=True)
    for name in ("show-revision", "schedule-quality"):
        p = sub.add_parser(name)
        p.add_argument("--organization-id", required=True)
        p.add_argument("--project-id", required=True)
        p.add_argument("--revision-id", required=True)
    p = sub.add_parser("compare-revisions")
    p.add_argument("--organization-id", required=True)
    p.add_argument("--project-id", required=True)
    p.add_argument("--old-revision-id", required=True)
    p.add_argument("--new-revision-id", required=True)
    p = sub.add_parser("search")
    p.add_argument("--organization-id", required=True)
    p.add_argument("--project-id", required=True)
    p.add_argument("--query", required=True)
    p.add_argument("--revision-id")
    p = sub.add_parser("show-import")
    p.add_argument("--organization-id", required=True)
    p.add_argument("--project-id", required=True)
    p.add_argument("--import-session-id", required=True)
    for name, decision in (
        ("confirm-activity-mapping", "confirm"),
        ("reject-activity-mapping", "reject"),
    ):
        p = sub.add_parser(name)
        p.add_argument("--organization-id", required=True)
        p.add_argument("--project-id", required=True)
        p.add_argument("--mapping-id", required=True)
        p.add_argument("--actor", default="cli-user")
        p.set_defaults(mapping_decision=decision)
    p = sub.add_parser("review-conflict")
    p.add_argument("--organization-id", required=True)
    p.add_argument("--project-id", required=True)
    p.add_argument("--conflict-id", required=True)
    p.add_argument("--decision", choices=("acknowledged", "resolved", "dismissed"), required=True)
    p.add_argument("--actor", default="cli-user")
    p = sub.add_parser("create-export-proposal")
    _scope(p)
    p.add_argument("--activity-revision-id", required=True)
    p.add_argument("--field", required=True)
    p.add_argument("--value", required=True)
    p.add_argument("--expected-version", required=True)
    p.add_argument("--rationale", required=True)
    p.add_argument("--evidence-reference", required=True)
    for name in ("validate-export", "approve-export", "reject-export", "execute-export"):
        p = sub.add_parser(name)
        p.add_argument("--organization-id", required=True)
        p.add_argument("--project-id", required=True)
        p.add_argument("--proposal-id", required=True)
        p.add_argument("--actor", default="cli-user")
        if name in {"approve-export", "reject-export"}:
            p.add_argument("--rationale", required=True)
    p = sub.add_parser("reconcile-export")
    p.add_argument("--organization-id", required=True)
    p.add_argument("--project-id", required=True)
    p.add_argument("--proposal-id", required=True)
    p.add_argument("--execution-id", required=True)
    p.add_argument("--actor", default="cli-user")
    p = sub.add_parser("ask")
    _scope(p)
    p.add_argument("--question", required=True)


def _scope(parser):
    parser.add_argument("--organization-id", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--connection-id", required=True)
    parser.add_argument("--actor", default="cli-user")


def _services(settings):
    adapter = PrimaveraP6Adapter()
    registry = AdapterRegistry()
    registry.register(adapter)
    integrations = IntegrationService(
        JsonIntegrationRepository(settings.data_directory / "integrations"),
        registry,
        TestSecretProvider(),
    )
    schedules = ScheduleIntelligenceService(
        JsonScheduleRepository(settings.data_directory / "schedule-intelligence")
    )
    return PrimaveraP6Service(integrations, schedules, adapter)


def _print(value):
    if isinstance(value, tuple):
        for item in value:
            _print(item)
    elif hasattr(value, "model_dump_json"):
        print(value.model_dump_json(indent=2))
    else:
        print(value)


def run_p6_command(args: argparse.Namespace, settings: Settings) -> int:
    service = _services(settings)
    command = args.p6_command
    try:
        if command == "adapter-info":
            _print(service.capabilities())
        elif command == "create-connection":
            approvers = (args.actor,) if args.write_enabled else ()
            _print(
                service.integrations.create_connection(
                    args.organization_id,
                    args.project_id,
                    "primavera_p6",
                    args.name,
                    args.actor,
                    configuration={"transport": args.transport},
                    write_enabled=args.write_enabled,
                    external_write_approver_ids=approvers,
                )
            )
        elif command == "test-connection":
            _print(
                service.integrations.test_connection(
                    args.organization_id, args.project_id, args.connection_id, args.actor
                )
            )
        elif command == "discover-projects":
            _print(
                service.discover_projects(
                    args.organization_id, args.project_id, args.connection_id, args.actor, args.file
                )
            )
        elif command == "map-project":
            _print(
                service.map_project(
                    args.organization_id,
                    args.project_id,
                    args.connection_id,
                    args.external_project_id,
                    args.actor,
                )
            )
        elif command in {"import-xer", "import-xml"}:
            _print(
                service.import_schedule(
                    args.organization_id,
                    args.project_id,
                    args.connection_id,
                    args.actor,
                    args.file,
                    name=args.schedule_name,
                )
            )
        elif command == "list-revisions":
            _print(service.revisions(args.project_id))
        elif command == "show-import":
            _print(
                service.integrations.repository.get(
                    "sessions",
                    args.import_session_id,
                    args.organization_id,
                    args.project_id,
                )
            )
        elif command == "show-revision":
            _print(service.schedules.repository.get("revisions", args.revision_id, args.project_id))
        elif command == "compare-revisions":
            _print(service.compare(args.project_id, args.old_revision_id, args.new_revision_id))
        elif command == "schedule-quality":
            _print(service.quality(args.project_id, args.revision_id))
        elif command == "list-conflicts":
            _print(
                service.integrations.repository.list(
                    "conflicts", args.organization_id, args.project_id
                )
            )
        elif command == "review-conflict":
            _print(
                service.integrations.review_conflict(
                    args.organization_id,
                    args.project_id,
                    args.conflict_id,
                    args.decision,
                    args.actor,
                )
            )
        elif command == "list-mapping-candidates":
            connections = service.integrations.repository.list(
                "connections", args.organization_id, args.project_id
            )
            _print(
                tuple(
                    mapping
                    for connection in connections
                    for mapping in service.activity_mapping_candidates(
                        args.organization_id, args.project_id, connection.id
                    )
                )
            )
        elif command in {"confirm-activity-mapping", "reject-activity-mapping"}:
            _print(
                service.review_activity_mapping(
                    args.organization_id,
                    args.project_id,
                    args.mapping_id,
                    args.mapping_decision,
                    args.actor,
                )
            )
        elif command == "generate-sync-proposals":
            _print(service.schedules.repository.list("proposals", args.project_id))
        elif command == "list-export-proposals":
            _print(
                service.integrations.repository.list(
                    "proposals", args.organization_id, args.project_id
                )
            )
        elif command == "create-export-proposal":
            _print(
                service.create_export_proposal(
                    args.organization_id,
                    args.project_id,
                    args.connection_id,
                    args.activity_revision_id,
                    args.field,
                    args.value,
                    ({"reference": args.evidence_reference},),
                    args.rationale,
                    args.actor,
                    args.expected_version,
                )
            )
        elif command == "validate-export":
            _print(
                service.integrations.validate_export(
                    args.organization_id, args.project_id, args.proposal_id, args.actor
                )
            )
        elif command == "approve-export":
            _print(
                service.integrations.approve_export(
                    args.organization_id,
                    args.project_id,
                    args.proposal_id,
                    args.actor,
                    args.rationale,
                    datetime.now(UTC) + timedelta(hours=1),
                )
            )
        elif command == "reject-export":
            _print(
                service.integrations.reject_export(
                    args.organization_id,
                    args.project_id,
                    args.proposal_id,
                    args.actor,
                    args.rationale,
                )
            )
        elif command == "execute-export":
            _print(
                service.integrations.execute_export(
                    args.organization_id, args.project_id, args.proposal_id, args.actor
                )
            )
        elif command == "reconcile-export":
            _print(
                service.integrations.reconcile(
                    args.organization_id,
                    args.project_id,
                    args.proposal_id,
                    args.execution_id,
                    args.actor,
                )
            )
        elif command == "dashboard":
            _print(service.dashboard(args.organization_id, args.project_id, args.connection_id))
        elif command == "search":
            _print(service.search(args.project_id, args.query, args.revision_id))
        elif command == "ask":
            _print(
                service.answer(
                    args.organization_id, args.project_id, args.connection_id, args.question
                )
            )
    except (ValueError, RuntimeError, OSError, PermissionError) as exc:
        print(f"P6 command failed: {exc}")
        return 1
    return 0
