import os
from pathlib import Path
from typing import Any
from pydantic import BaseModel
from .models import (
    AuditEvent,
    BenchmarkDefinition,
    BenchmarkResult,
    ComparableSelection,
    DataQualityAssessment,
    EnterpriseEntity,
    EntityMatchCandidate,
    Lesson,
    MetricRecord,
    NotificationRequest,
    Portfolio,
    TaxonomyMapping,
)


class JsonEnterpriseRepository:
    TYPES: dict[str, type[BaseModel]] = {
        "portfolios": Portfolio,
        "taxonomy": TaxonomyMapping,
        "entities": EnterpriseEntity,
        "entity_matches": EntityMatchCandidate,
        "lessons": Lesson,
        "metrics": MetricRecord,
        "benchmark_definitions": BenchmarkDefinition,
        "benchmarks": BenchmarkResult,
        "comparables": ComparableSelection,
        "quality": DataQualityAssessment,
        "audit": AuditEvent,
        "outbox": NotificationRequest,
    }

    def __init__(self, root: Path):
        self.root = root.expanduser().resolve()

    def save(self, category: str, identifier: str, value: BaseModel) -> None:
        if not identifier.replace("-", "").replace("_", "").isalnum():
            raise ValueError("Unsafe enterprise record identifier")
        path = self.root / category / f"{identifier}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        temp.write_text(value.model_dump_json(indent=2), encoding="utf-8")
        os.replace(temp, path)

    def get(self, category: str, identifier: str, organization_id: str) -> Any | None:
        path = self.root / category / f"{identifier}.json"
        if not path.exists():
            return None
        value = self.TYPES[category].model_validate_json(path.read_text(encoding="utf-8"))
        return value if value.organization_id == organization_id else None

    def list(self, category: str, organization_id: str) -> tuple[Any, ...]:
        folder = self.root / category
        if not folder.exists():
            return ()
        result = []
        for path in sorted(folder.glob("*.json")):
            value = self.TYPES[category].model_validate_json(path.read_text(encoding="utf-8"))
            if value.organization_id == organization_id:
                result.append(value)
        return tuple(result)
