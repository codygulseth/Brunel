"""Typed runtime configuration."""

from .constants import PRODUCT_DESCRIPTION, PRODUCT_NAME
from .settings import Settings, get_settings

__all__ = ["PRODUCT_DESCRIPTION", "PRODUCT_NAME", "Settings", "get_settings"]
