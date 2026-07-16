from uuid import uuid4
import pytest
from agents import AgentContext, AgentRegistry, AgentResult
from app.bootstrap import create_application
from config import PRODUCT_DESCRIPTION, PRODUCT_NAME
from config.settings import LoggingSettings, Settings, get_settings
from core.container import Container
from rag import RetrievalQuery


class ExampleAgent:
    name = "example"

    async def run(self, context: AgentContext) -> AgentResult:
        return AgentResult(summary=context.request)


def test_container_resolves_lazy_singleton():
    container = Container()
    calls = []
    container.register(str, lambda _: calls.append("built") or "dependency")
    assert container.resolve(str) == "dependency"
    assert container.resolve(str) == "dependency"
    assert calls == ["built"]


def test_container_reports_unregistered_dependency():
    with pytest.raises(LookupError, match="No dependency registered"):
        Container().resolve(str)


def test_agent_registry_is_extensible_without_central_changes():
    registry = AgentRegistry()
    agent = ExampleAgent()
    registry.register(agent)
    assert registry.names() == ("example",) and registry.get("example") is agent
    with pytest.raises(ValueError, match="already registered"):
        registry.register(agent)


def test_settings_load_environment(monkeypatch):
    monkeypatch.setenv("BRUNEL_ENVIRONMENT", "test")
    monkeypatch.setenv("BRUNEL_LOG_LEVEL", "debug")
    monkeypatch.setenv("BRUNEL_LOG_JSON", "true")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.environment == "test" and settings.logging == LoggingSettings(
        level="DEBUG", json_output=True
    )
    get_settings.cache_clear()


def test_application_bootstraps_without_model_or_external_service():
    settings = Settings(environment="test")
    application = create_application(settings)
    assert application.settings.models.provider == "disabled"
    assert application.agents.names() == ()


def test_product_identity_is_centralized():
    assert PRODUCT_NAME == "Brunel"
    assert PRODUCT_DESCRIPTION.startswith("An elite AI construction copilot")


def test_retrieval_models_require_traceable_project_context():
    query = RetrievalQuery(project_id=uuid4(), text="What changed?", limit=5)
    assert query.limit == 5
    with pytest.raises(ValueError):
        RetrievalQuery(project_id=uuid4(), text="", limit=5)
