"""Brunel revision intelligence public API."""

from .errors import (
    CrossProjectComparisonError,
    DocumentNotFoundError,
    DocumentsNotComparableError,
    InsufficientContentError,
    RevisionIntelligenceError,
)
from .lineage import RevisionLineageService
from .models import ComparisonRequest, DocumentComparison
from .rendering import MarkdownComparisonRenderer
from .service import RevisionComparisonService

__all__ = [
    "ComparisonRequest",
    "CrossProjectComparisonError",
    "DocumentComparison",
    "DocumentNotFoundError",
    "DocumentsNotComparableError",
    "InsufficientContentError",
    "MarkdownComparisonRenderer",
    "RevisionComparisonService",
    "RevisionIntelligenceError",
    "RevisionLineageService",
]
