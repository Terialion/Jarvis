"""Read-only repository inspection package."""

from .inspector import inspect_repo
from .schema import RepoInspectionRequest, RepoInspectionResult

__all__ = ["inspect_repo", "RepoInspectionRequest", "RepoInspectionResult"]
