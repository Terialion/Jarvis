"""Jarvis canonical package namespace."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_legacy_runtime_symbol(name: str):
    root = Path(__file__).resolve().parents[2]
    runtime_path = root / "jarvis" / "runtime_bootstrap.py"
    spec = importlib.util.spec_from_file_location("jarvis_runtime_bootstrap_legacy", runtime_path)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise ImportError(f"Unable to load legacy runtime module: {runtime_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return getattr(module, name)


bootstrap = _load_legacy_runtime_symbol("bootstrap")
Jarvis = _load_legacy_runtime_symbol("Jarvis")

__all__ = ["Jarvis", "bootstrap"]

