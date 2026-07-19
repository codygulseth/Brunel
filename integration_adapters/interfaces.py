from abc import ABC, abstractmethod
from typing import Any
from .models import AdapterManifest, Capability


class AdapterError(RuntimeError):
    def __init__(self, category: str, message: str):
        super().__init__(message)
        self.category = category


class IntegrationAdapter(ABC):
    @property
    @abstractmethod
    def manifest(self) -> AdapterManifest: ...
    def require(self, capability: Capability) -> None:
        if capability not in self.manifest.supported_operations:
            raise AdapterError("unsupported_capability", f"Adapter does not support {capability}")

    @abstractmethod
    def test_connection(
        self, configuration: dict[str, str], secret: object | None
    ) -> dict[str, Any]: ...
    def import_records(
        self, scope: dict[str, str], cursor: str | None
    ) -> tuple[tuple[dict[str, Any], ...], str | None]:
        self.require(Capability.IMPORT_RECORDS)
        raise AdapterError("unsupported_capability", "Import not implemented")

    def execute_approved_export(
        self, payload: dict[str, Any], idempotency_key: str, expected_version: str | None
    ) -> dict[str, Any]:
        self.require(Capability.EXECUTE_APPROVED_EXPORT)
        raise AdapterError("unsupported_capability", "Export not implemented")

    def retrieve_external_record(self, record_id: str) -> dict[str, Any]:
        self.require(Capability.RETRIEVE_EXTERNAL_RECORD)
        raise AdapterError("unsupported_capability", "Retrieval not implemented")

    def validate_export_payload(
        self, payload: dict[str, Any], configuration: dict[str, str]
    ) -> tuple[str, ...]:
        """Return adapter-specific validation errors without mutating external state."""
        return ()

    def validate_export_context(
        self, proposal: object, connection: object, repository: object
    ) -> tuple[str, ...]:
        """Validate durable mapping or revision state immediately before execution."""
        return ()


class SecretProvider(ABC):
    @abstractmethod
    def resolve(self, reference_id: str) -> object | None: ...
