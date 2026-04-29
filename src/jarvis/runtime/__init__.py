"""Compatibility re-export layer for canonical runtime imports.

This namespace lets callers migrate from ``jarvis_runtime`` to
``src.jarvis.runtime`` without breaking existing imports during P12.
"""

from jarvis_runtime import *  # noqa: F401,F403
from jarvis_runtime import __all__ as _legacy_all

__all__ = list(_legacy_all)

