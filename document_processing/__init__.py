"""Brunel contracts for document intake, parsing, normalization, and chunking."""

from .interfaces import DocumentParser, ParsedDocument, SourceDocument

__all__ = ["DocumentParser", "ParsedDocument", "SourceDocument"]
