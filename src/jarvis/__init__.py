"""Jarvis canonical package namespace."""

from __future__ import annotations

import importlib
import importlib.machinery
import os
import sys

# Ensure ``src`` is reachable as a namespace package so ``import src.jarvis``
# works in production (conftest.py does the same for tests).
_src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_parent_of_src = os.path.dirname(_src_dir)
for _p in (_src_dir, _parent_of_src):
    if _p not in sys.path:
        sys.path.insert(0, _p)


class _AliasLoader:
    """Loader that returns the already-loaded ``jarvis.*`` module so
    ``src.jarvis.*`` imports don't re-execute package init code."""

    def __init__(self, real_mod):
        self._real_mod = real_mod

    def create_module(self, spec):
        return self._real_mod

    def exec_module(self, module):
        pass  # already initialised


class _AliasFinder:
    """Meta-path finder that redirects ``src.jarvis.*`` → ``jarvis.*``.

    Without this, ``src.jarvis.agent.loop`` and ``jarvis.agent.loop`` are
    *different* module objects loaded from the same files, which breaks
    monkeypatching, isinstance checks, and anything else that relies on
    module identity."""

    @staticmethod
    def find_spec(fullname, path=None, target=None):
        if not fullname.startswith("src.jarvis"):
            return None
        real_name = "jarvis" + fullname[len("src.jarvis"):]
        real_mod = importlib.import_module(real_name)
        is_pkg = hasattr(real_mod, "__path__")
        spec = importlib.machinery.ModuleSpec(
            fullname, _AliasLoader(real_mod), is_package=is_pkg,
        )
        if is_pkg:
            spec.submodule_search_locations = list(real_mod.__path__)
        return spec


if not any(isinstance(f, _AliasFinder) for f in sys.meta_path):
    sys.meta_path.insert(0, _AliasFinder)

from .runtime_bootstrap import Jarvis, bootstrap

__all__ = ["Jarvis", "bootstrap"]

