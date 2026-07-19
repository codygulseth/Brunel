import argparse
from config.settings import Settings
from commissioning_intelligence.repository import JsonCommissioningRepository
from commissioning_intelligence.service import CommissioningService

COMMANDS = {
    "commissioning-system-create",
    "commissioning-systems",
    "commissioning-readiness",
    "commissioning-dashboard",
    "turnover-dashboard",
    "commissioning-search",
}


def register_commissioning_commands(commands):
    for name in COMMANDS:
        parser = commands.add_parser(name)
        parser.add_argument("--project-id", required=True)
        if name == "commissioning-system-create":
            parser.add_argument("--name", required=True)
        if name == "commissioning-readiness":
            parser.add_argument("--system-id", required=True)
            parser.add_argument("--purpose", default="startup")
        if name == "commissioning-search":
            parser.add_argument("--query", required=True)


def run_commissioning_command(args: argparse.Namespace, settings: Settings) -> int:
    service = CommissioningService(
        JsonCommissioningRepository(settings.data_directory / "commissioning-intelligence")
    )
    if args.command == "commissioning-system-create":
        value = service.create_system(args.project_id, args.name)
    elif args.command == "commissioning-systems":
        value = service.repository.list("systems", args.project_id)
    elif args.command == "commissioning-readiness":
        value = service.assess_readiness(args.project_id, args.system_id, args.purpose)
    elif args.command == "commissioning-dashboard":
        value = service.commissioning_dashboard(args.project_id)
    elif args.command == "turnover-dashboard":
        value = service.turnover_dashboard(args.project_id)
    else:
        value = service.search(args.project_id, args.query)
    if isinstance(value, tuple):
        for item in value:
            print(item.model_dump_json())
    else:
        print(value.model_dump_json(indent=2))
    return 0
