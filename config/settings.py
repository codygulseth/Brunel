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


class RevisionSettings(BaseModel):
    model_config = ConfigDict(frozen=True)
    alignment_similarity_threshold: float = Field(default=0.55, ge=0, le=1)
    ambiguous_match_threshold: float = Field(default=0.08, ge=0, le=1)
    minimum_content_similarity: float = Field(default=0.35, ge=0, le=1)
    maximum_block_size: int = Field(default=2_000, ge=100, le=20_000)
    include_formatting_changes: bool = False
    maximum_excerpt_length: int = Field(default=500, ge=50, le=4_000)
    minimum_severity: str = "low"
    report_output_directory: Path = Path("reports")
    rules_version: str = "construction-rules-v1"


class WorkflowSettings(BaseModel):
    model_config = ConfigDict(frozen=True)
    automatic_register_generation: bool = False
    admission_policy_version: str = "change-admission-v1"
    default_priority: str = "medium"
    due_soon_days: int = Field(default=7, ge=1, le=90)
    automatic_regeneration: bool = False
    notification_outbox_enabled: bool = True
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8001, ge=1, le=65535)
    api_page_limit: int = Field(default=50, ge=1, le=200)
    legacy_compatibility: bool = True


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)
    environment: str = "development"
    data_directory: Path = Path("data")
    logging: LoggingSettings = LoggingSettings()
    models: ModelSettings = ModelSettings()
    retrieval: RetrievalSettings = RetrievalSettings()
    answers: AnswerSettings = AnswerSettings()
    revisions: RevisionSettings = RevisionSettings()
    workflow: WorkflowSettings = WorkflowSettings()


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
        revisions=RevisionSettings(
            alignment_similarity_threshold=float(
                os.getenv("BRUNEL_REVISION_ALIGNMENT_THRESHOLD", "0.55")
            ),
            ambiguous_match_threshold=float(
                os.getenv("BRUNEL_REVISION_AMBIGUOUS_THRESHOLD", "0.08")
            ),
            minimum_content_similarity=float(
                os.getenv("BRUNEL_REVISION_MINIMUM_SIMILARITY", "0.35")
            ),
            maximum_block_size=int(os.getenv("BRUNEL_REVISION_MAXIMUM_BLOCK_SIZE", "2000")),
            include_formatting_changes=_as_bool(
                os.getenv("BRUNEL_REVISION_INCLUDE_FORMATTING", "false")
            ),
            maximum_excerpt_length=int(os.getenv("BRUNEL_REVISION_MAXIMUM_EXCERPT_LENGTH", "500")),
            minimum_severity=os.getenv("BRUNEL_REVISION_MINIMUM_SEVERITY", "low"),
            report_output_directory=Path(os.getenv("BRUNEL_REPORT_OUTPUT_DIRECTORY", "reports")),
            rules_version=os.getenv("BRUNEL_REVISION_RULES_VERSION", "construction-rules-v1"),
        ),
        workflow=WorkflowSettings(
            automatic_register_generation=_as_bool(
                os.getenv("BRUNEL_AUTO_REGISTER_GENERATION", "false")
            ),
            admission_policy_version=os.getenv(
                "BRUNEL_ADMISSION_POLICY_VERSION", "change-admission-v1"
            ),
            default_priority=os.getenv("BRUNEL_DEFAULT_REVIEW_PRIORITY", "medium"),
            due_soon_days=int(os.getenv("BRUNEL_DUE_SOON_DAYS", "7")),
            automatic_regeneration=_as_bool(os.getenv("BRUNEL_AUTO_REGENERATION", "false")),
            notification_outbox_enabled=_as_bool(os.getenv("BRUNEL_NOTIFICATION_OUTBOX", "true")),
            api_host=os.getenv("BRUNEL_API_HOST", "127.0.0.1"),
            api_port=int(os.getenv("BRUNEL_API_PORT", "8001")),
            api_page_limit=int(os.getenv("BRUNEL_API_PAGE_LIMIT", "50")),
            legacy_compatibility=_as_bool(os.getenv("BRUNEL_LEGACY_COMPATIBILITY", "true")),
        ),
    )
