"""Persistence interfaces; infrastructure implementations belong in subpackages."""

from .interfaces import ProjectRecord, ProjectRepository

__all__ = ["ProjectRecord", "ProjectRepository"]
