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
    api_key: str | None = Field(default=None, repr=False)
    temperature: float = Field(default=0.1, ge=0, le=2)
    structured_output_retry_limit: int = Field(default=1, ge=0, le=3)


class RetrievalSettings(BaseModel):
    model_config = ConfigDict(frozen=True)
    top_k: int = Field(default=5, ge=1, le=100)
    minimum_relevance: float = Field(default=0.08, ge=0, le=1)
    citation_excerpt_length: int = Field(default=320, ge=50, le=2_000)
    maximum_evidence_chunks: int = Field(default=8, ge=1, le=100)


class AnswerSettings(BaseModel):
    model_config = ConfigDict(frozen=True)
    provider: str = "extractive"


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)
    environment: str = "development"
    data_directory: Path = Path("data")
    logging: LoggingSettings = LoggingSettings()
    models: ModelSettings = ModelSettings()
    retrieval: RetrievalSettings = RetrievalSettings()
    answers: AnswerSettings = AnswerSettings()


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
            api_key=os.getenv("BRUNEL_MODEL_API_KEY"),
            temperature=float(os.getenv("BRUNEL_MODEL_TEMPERATURE", "0.1")),
            structured_output_retry_limit=int(
                os.getenv("BRUNEL_STRUCTURED_OUTPUT_RETRY_LIMIT", "1")
            ),
        ),
        retrieval=RetrievalSettings(
            top_k=int(os.getenv("BRUNEL_RETRIEVAL_TOP_K", "5")),
            minimum_relevance=float(os.getenv("BRUNEL_MINIMUM_RELEVANCE", "0.08")),
            citation_excerpt_length=int(os.getenv("BRUNEL_CITATION_EXCERPT_LENGTH", "320")),
            maximum_evidence_chunks=int(os.getenv("BRUNEL_MAXIMUM_EVIDENCE_CHUNKS", "8")),
        ),
        answers=AnswerSettings(provider=os.getenv("BRUNEL_ANSWER_PROVIDER", "extractive")),
    )
