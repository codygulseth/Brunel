"""Canonical, vendor-neutral integration adapter framework."""

from .registry import AdapterRegistry
from .repository import JsonIntegrationRepository
from .service import IntegrationService

__all__ = ["AdapterRegistry", "IntegrationService", "JsonIntegrationRepository"]
