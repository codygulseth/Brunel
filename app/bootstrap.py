"""Brunel composition root.

FastAPI, CLI, and worker entry points should call :func:`create_application`
instead of constructing infrastructure dependencies themselves.
"""

from dataclasses import dataclass

from agents.registry import AgentRegistry
from config.settings import Settings, get_settings
from core.container import Container
from core.logging import configure_logging


@dataclass(frozen=True, slots=True)
class Application:
    """Framework-neutral application context exposed to future adapters."""

    settings: Settings
    container: Container
    agents: AgentRegistry


def create_application(settings: Settings | None = None) -> Application:
    resolved = settings or get_settings()
    configure_logging(resolved.logging)
    container = Container()
    # TODO(storage): register a ProjectRepository implementation when persistence is selected.
    # TODO(api): expose this application context from a FastAPI lifespan function.
    return Application(settings=resolved, container=container, agents=AgentRegistry())
