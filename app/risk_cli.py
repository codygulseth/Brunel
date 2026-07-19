import argparse
from config.settings import Settings
from risk_intelligence.models import Evidence
from risk_intelligence.qa import RiskQuestionService
from risk_intelligence.repository import JsonRiskRepository
from risk_intelligence.service import RiskIntelligenceService

COMMANDS = {"risk-generate", "risk-list", "risk-review", "risk-dashboard", "risk-ask"}


def register_risk_commands(commands):
    for name in COMMANDS:
        p = commands.add_parser(name)
        p.add_argument("--project-id", required=True)
        if name == "risk-generate":
            p.add_argument("--record-id", required=True)
            p.add_argument("--excerpt", required=True)
        if name == "risk-review":
            p.add_argument("--risk-id", required=True)
            p.add_argument("--decision", required=True)
        if name == "risk-ask":
            p.add_argument("--question", required=True)


def run_risk_command(args: argparse.Namespace, settings: Settings) -> int:
    service = RiskIntelligenceService(
        JsonRiskRepository(settings.data_directory / "risk-intelligence")
    )
    if args.command == "risk-generate":
        value = service.generate(
            args.project_id,
            (
                Evidence(
                    record_type="cli",
                    record_id=args.record_id,
                    citation={"source": "cli"},
                    excerpt=args.excerpt,
                ),
            ),
        )
    elif args.command == "risk-list":
        value = service.repository.list("risks", args.project_id)
    elif args.command == "risk-review":
        value = service.review(args.project_id, args.risk_id, args.decision, "cli-user")
    elif args.command == "risk-dashboard":
        value = service.dashboard(args.project_id)
    else:
        value = RiskQuestionService(service).answer(args.project_id, args.question)
    if isinstance(value, tuple):
        [print(x.model_dump_json()) for x in value]
    else:
        print(value.model_dump_json(indent=2))
    return 0
