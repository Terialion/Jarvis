"""Plugin discovery — scan scope directories for .claude-plugin/plugin.json."""

from __future__ import annotations

import os
from pathlib import Path

from .schema import PluginManifest

SCOPE_PROJECT = "project"
SCOPE_USER = "user"
SCOPE_SYSTEM = "system"


def _scan_dir(root: Path, max_depth: int = 3) -> list[Path]:
    """Scan a directory for .claude-plugin/plugin.json files up to max_depth levels."""
    results: list[Path] = []
    try:
        for entry in sorted(root.iterdir()):
            if entry.is_dir() and not entry.name.startswith("."):
                candidate = entry / ".claude-plugin" / "plugin.json"
                if candidate.exists():
                    results.append(candidate)
            if entry.is_dir() and max_depth > 0:
                results.extend(_scan_dir(entry, max_depth - 1))
    except (PermissionError, FileNotFoundError, OSError):
        pass
    return results


def discover_plugins(
    *,
    project_root: str | Path | None = None,
    user_plugins_dir: str | Path | None = None,
    env_dirs: str | None = None,
) -> list[PluginManifest]:
    """Discover all plugins across three scopes.

    Priority: project wins over user over system (by insertion order).
    """
    manifests: dict[str, PluginManifest] = {}

    def _load(path: Path) -> None:
        try:
            m = PluginManifest.from_json(path)
            if m.name not in manifests:
                manifests[m.name] = m
        except Exception:
            pass  # Skip broken manifests

    # System scope (lowest priority) — env dirs
    if env_dirs:
        for d in env_dirs.split(os.pathsep):
            d = d.strip()
            if d:
                for p in _scan_dir(Path(d).expanduser().resolve()):
                    _load(p)

    # User scope
    user_dir = Path(user_plugins_dir or "~/.jarvis/plugins").expanduser().resolve()
    if user_dir.exists():
        for p in _scan_dir(user_dir):
            _load(p)

    # Project scope (highest priority — loaded last so it overwrites)
    if project_root:
        proj = Path(project_root).resolve()
        for p in _scan_dir(proj):
            m = None
            try:
                m = PluginManifest.from_json(p)
            except Exception:
                pass
            if m is not None:
                manifests[m.name] = m  # Always overwrite — project wins

    return list(manifests.values())


class PluginDiscovery:
    """Cached plugin discovery with invalidation."""

    def __init__(
        self,
        *,
        project_root: str | Path | None = None,
        user_plugins_dir: str | Path | None = None,
    ):
        self.project_root = Path(project_root).resolve() if project_root else None
        self.user_plugins_dir = (
            Path(user_plugins_dir).expanduser().resolve()
            if user_plugins_dir
            else Path.home() / ".jarvis" / "plugins"
        )
        self._env_dirs = os.environ.get("JARVIS_PLUGIN_DIRS", "")
        self._cache: list[PluginManifest] | None = None

    def discover(self) -> list[PluginManifest]:
        if self._cache is None:
            self._cache = discover_plugins(
                project_root=self.project_root,
                user_plugins_dir=self.user_plugins_dir,
                env_dirs=self._env_dirs,
            )
        return list(self._cache)

    def invalidate(self) -> None:
        self._cache = None
