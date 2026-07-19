import argparse
from config.settings import Settings
from contract_intelligence.models import Evidence
from contract_intelligence.repository import JsonContractRepository
from contract_intelligence.service import ContractIntelligenceService

COMMANDS = {
    "contract-ingest",
    "contract-list",
    "contract-clauses",
    "contract-dashboard",
    "contract-search",
}


def register_contract_commands(commands):
    for name in COMMANDS:
        p = commands.add_parser(name)
        p.add_argument("--project-id", required=True)
        if name == "contract-ingest":
            p.add_argument("--revision-id", required=True)
            p.add_argument("--title", required=True)
            p.add_argument("--text", required=True)
        if name == "contract-clauses":
            p.add_argument("--document-id", required=True)
            p.add_argument("--text", required=True)
        if name == "contract-search":
            p.add_argument("--query", required=True)


def run_contract_command(args: argparse.Namespace, settings: Settings) -> int:
    service = ContractIntelligenceService(
        JsonContractRepository(settings.data_directory / "contract-intelligence")
    )
    p = args.project_id
    if args.command == "contract-ingest":
        value = service.ingest_contract(
            p,
            args.revision_id,
            "other",
            args.title,
            (
                Evidence(
                    record_type="document_revision",
                    record_id=args.revision_id,
                    citation={"revision_id": args.revision_id},
                    exact_text=args.text,
                ),
            ),
        )
    elif args.command == "contract-list":
        value = service.repository.list("documents", p)
    elif args.command == "contract-clauses":
        value = service.extract_clauses(
            p,
            args.document_id,
            (
                Evidence(
                    record_type="document_revision",
                    record_id=args.document_id,
                    citation={"document_id": args.document_id},
                    exact_text=args.text,
                ),
            ),
        )
    elif args.command == "contract-dashboard":
        value = service.dashboard(p)
    else:
        value = service.search(p, args.query)
    if isinstance(value, tuple):
        for item in value:
            print(item.model_dump_json())
    else:
        print(value.model_dump_json(indent=2))
    return 0
