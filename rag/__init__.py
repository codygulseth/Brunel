"""Retrieval contracts; provider and indexing implementations are intentionally deferred."""

from .interfaces import RetrievalQuery, RetrievalResult, Retriever

__all__ = ["RetrievalQuery", "RetrievalResult", "Retriever"]
