import argparse
from config.settings import Settings
from enterprise_intelligence.repository import JsonEnterpriseRepository
from enterprise_intelligence.service import EnterpriseIntelligenceService

COMMANDS = {
    "enterprise-portfolio-create",
    "enterprise-portfolios",
    "enterprise-dashboard",
    "enterprise-benchmarks",
}


def register_enterprise_commands(commands):
    for name in COMMANDS:
        p = commands.add_parser(name)
        p.add_argument("--organization-id", required=True)
        if name == "enterprise-portfolio-create":
            p.add_argument("--name", required=True)
            p.add_argument("--principal-id", required=True)
        if name == "enterprise-dashboard":
            p.add_argument("--portfolio-id", required=True)
            p.add_argument("--principal-id", required=True)


def run_enterprise_command(args: argparse.Namespace, settings: Settings) -> int:
    service = EnterpriseIntelligenceService(
        JsonEnterpriseRepository(settings.data_directory / "enterprise-intelligence")
    )
    org = args.organization_id
    if args.command == "enterprise-portfolio-create":
        value = service.create_portfolio(org, args.name, (args.principal_id,), args.principal_id)
    elif args.command == "enterprise-portfolios":
        value = service.repository.list("portfolios", org)
    elif args.command == "enterprise-dashboard":
        value = service.dashboard(org, args.portfolio_id, args.principal_id)
    else:
        value = service.repository.list("benchmarks", org)
    if isinstance(value, tuple):
        for item in value:
            print(item.model_dump_json())
    else:
        print(value.model_dump_json(indent=2))
    return 0
