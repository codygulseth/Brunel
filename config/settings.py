"""Environment-based settings with no cloud or model provider assumptions."""

import os
from functools import lru_cache
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field


class LoggingSettings(BaseModel):
    model_config = ConfigDict(frozen=True)
    level: str = Field(default="INFO", pattern=r"^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    json_output: bool = False


class ModelSettings(BaseModel):
    model_config = ConfigDict(frozen=True)
    provider: str = "disabled"
    model_name: str | None = None
    base_url: str | None = None


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)
    environment: str = "development"
    data_directory: Path = Path("data")
    logging: LoggingSettings = LoggingSettings()
    models: ModelSettings = ModelSettings()


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load `BRUNEL_*` environment variables once per process."""
    return Settings(
        environment=os.getenv("BRUNEL_ENVIRONMENT", "development"),
        data_directory=Path(os.getenv("BRUNEL_DATA_DIRECTORY", "data")),
        logging=LoggingSettings(
            level=os.getenv("BRUNEL_LOG_LEVEL", "INFO").upper(),
            json_output=_as_bool(os.getenv("BRUNEL_LOG_JSON", "false")),
        ),
        models=ModelSettings(
            provider=os.getenv("BRUNEL_MODEL_PROVIDER", "disabled"),
            model_name=os.getenv("BRUNEL_MODEL_NAME"),
            base_url=os.getenv("BRUNEL_MODEL_BASE_URL"),
        ),
    )
