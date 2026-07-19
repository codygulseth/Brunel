import argparse
from config.settings import Settings
from integration_adapters.reference import (
    GenericJsonAdapter,
    InMemoryWriteAdapter,
    LocalFileAdapter,
    TestSecretProvider,
)
from integration_adapters.registry import AdapterRegistry
from integration_adapters.repository import JsonIntegrationRepository
from integration_adapters.service import IntegrationService
from p6_adapter import PrimaveraP6Adapter

COMMANDS = {"integration-adapters", "integration-connections", "integration-health"}


def register_integration_commands(commands):
    for name in COMMANDS:
        p = commands.add_parser(name)
        p.add_argument("--organization-id", required=True)
        p.add_argument("--project-id")


def run_integration_command(args: argparse.Namespace, settings: Settings) -> int:
    registry = AdapterRegistry()
    for adapter in (
        LocalFileAdapter(),
        GenericJsonAdapter(),
        InMemoryWriteAdapter(),
        PrimaveraP6Adapter(),
    ):
        registry.register(adapter)
    service = IntegrationService(
        JsonIntegrationRepository(settings.data_directory / "integrations"),
        registry,
        TestSecretProvider(),
    )
    value = (
        registry.manifests()
        if args.command == "integration-adapters"
        else service.repository.list("connections", args.organization_id, args.project_id)
        if args.command == "integration-connections"
        else service.health(args.organization_id, args.project_id)
    )
    if isinstance(value, tuple):
        for item in value:
            print(item.model_dump_json())
    else:
        print(value.model_dump_json(indent=2))
    return 0
