"""Skill registry, discovery, and metadata index export."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any

from .lifecycle import SkillLifecycleManager
from .loader import SkillLoader, SkillParseError
from .schema import SkillSpec


class SkillRegistry:
    # Cross-instance cache: skill specs only change on install/uninstall,
    # which invalidates this cache explicitly.
    _specs_cache: dict[str, Any] | None = None
    _cache_mtime: float = 0.0
    _cache_config_path: str | None = None
    _load_lock: threading.Lock = threading.Lock()

    def __init__(
        self,
        *,
        builtin_root: str | Path | None = None,
        extra_dirs: list[str | Path] | None = None,
        project_root: str | Path | None = None,
        loader: SkillLoader | None = None,
        lifecycle: SkillLifecycleManager | None = None,
        plugin_skill_dirs: list[str | Path] | None = None,
    ) -> None:
        self.loader = loader or SkillLoader()
        self.project_root = Path(project_root or Path.cwd()).resolve()
        self.builtin_root = Path(builtin_root or Path(__file__).resolve().parent / "builtin").resolve()
        self.extra_dirs = [Path(p).resolve() for p in list(extra_dirs or [])]
        self.plugin_skill_dirs = [Path(p).resolve() for p in list(plugin_skill_dirs or [])]
        self.lifecycle = lifecycle or SkillLifecycleManager(project_root=self.project_root, loader=self.loader)
        self._cache: dict[str, SkillSpec] | None = None
        self._discovery_roots: list[dict[str, str]] = []
        self._warnings: list[dict[str, Any]] = []
        self._duplicates: dict[str, list[str]] = {}

    def list_skills(self) -> list[SkillSpec]:
        specs = self._load_specs()
        return [specs[name] for name in sorted(specs.keys()) if self._is_prompt_enabled(specs[name])]

    def list_discovered_skills(self) -> list[SkillSpec]:
        specs = self._load_specs()
        return [specs[name] for name in sorted(specs.keys())]

    def get(self, name: str) -> SkillSpec:
        key = str(name or "").strip()
        specs = self._load_specs()
        if key not in specs:
            raise KeyError(key)
        return specs[key]

    def get_loadable(self, name: str) -> SkillSpec:
        spec = self.get(name)
        state = self.lifecycle.lifecycle_state_for(spec)
        if state.get("quarantined"):
            raise PermissionError("skill_quarantined")
        if not state.get("enabled"):
            raise PermissionError("skill_disabled")
        return spec

    def get_runnable(self, name: str) -> SkillSpec:
        return self.get_loadable(name)

    def load_body(self, name: str) -> str:
        spec = self.get(name)
        return self.loader.load_body(spec.path)

    def export_index(self, *, include_inactive: bool = False) -> list[dict[str, Any]]:
        specs = self.list_discovered_skills() if include_inactive else self.list_skills()
        states = self.lifecycle.lifecycle_state_batch(specs)
        rows: list[dict[str, Any]] = []
        for spec, state in zip(specs, states):
            row = spec.to_index_row()
            row.update(state)
            row["duplicate_status"] = "shadowed" if self._duplicates.get(spec.name) else "primary"
            rows.append(row)
        return rows

    def available_names(self) -> list[str]:
        return [spec.name for spec in self.list_skills()]

    def warnings(self) -> list[dict[str, Any]]:
        self._load_specs()
        return list(self._warnings)

    def snapshot(self) -> dict[str, Any]:
        items = self.export_index()
        return {
            "ok": True,
            "data": {
                "count": len(items),
                "items": items,
                "warnings": self.warnings(),
                "discovery": {
                    "roots": list(self._discovery_roots),
                    "precedence": [row["source"] for row in self._discovery_roots],
                },
                "lifecycle_error": self.lifecycle.lifecycle_error(),
            },
        }

    def _load_specs(self) -> dict[str, SkillSpec]:
        # Cross-instance cache: skill specs only change on install/uninstall.
        # Use the lifecycle config mtime as the cache key to detect changes.
        # Thread-safe: double-checked locking — only one thread runs the
        # expensive rglob+parse at a time; others wait on _load_lock.
        config_path = str(self.lifecycle.store.config_path)
        config_mtime = self.lifecycle.store.config_path.stat().st_mtime if self.lifecycle.store.config_path.exists() else 0.0
        if (SkillRegistry._specs_cache is not None
                and SkillRegistry._cache_config_path == config_path
                and SkillRegistry._cache_mtime >= config_mtime):
            self._cache = SkillRegistry._specs_cache
            self._warnings = SkillRegistry._specs_cache.get("__warnings__", [])
            self._discovery_roots = SkillRegistry._specs_cache.get("__discovery_roots__", [])
            self._duplicates = SkillRegistry._specs_cache.get("__duplicates__", {})
            return {k: v for k, v in self._cache.items() if not k.startswith("__")}
        with SkillRegistry._load_lock:
            # Re-check cache after acquiring lock — another thread may have
            # filled it while we were waiting.
            if (SkillRegistry._specs_cache is not None
                    and SkillRegistry._cache_config_path == config_path
                    and SkillRegistry._cache_mtime >= config_mtime):
                self._cache = SkillRegistry._specs_cache
                self._warnings = SkillRegistry._specs_cache.get("__warnings__", [])
                self._discovery_roots = SkillRegistry._specs_cache.get("__discovery_roots__", [])
                self._duplicates = SkillRegistry._specs_cache.get("__duplicates__", {})
                return {k: v for k, v in self._cache.items() if not k.startswith("__")}
            return self._load_specs_uncached()

    def _load_specs_uncached(self) -> dict[str, SkillSpec]:
        _t_total = time.perf_counter()
        specs: dict[str, SkillSpec] = {}
        self._warnings = []
        self._discovery_roots = []
        self._duplicates = {}
        roots = self._iter_roots()
        # Pre-compute root paths for _is_within_allowed_roots to avoid
        # re-reading lifecycle config on every inner-loop call.
        _root_paths = [root for _, root in roots]
        _t_roots = time.perf_counter()
        _root_timings: list[tuple[str, float, int]] = []
        for source, root in roots:
            self._discovery_roots.append({"source": source, "path": str(root)})
            if not root.exists():
                continue
            try:
                from ..core.debug_log import debug_log, is_debug_enabled
                if is_debug_enabled():
                    debug_log("skills", f"_load_specs_uncached entering root: {source} path={root}")
            except Exception:
                pass
            _t_root = time.perf_counter()
            _n_dirs = 0
            for skill_dir in self._iter_skill_dirs(root):
                _n_dirs += 1
                if not self._is_within_allowed_roots(skill_dir, _roots=_root_paths):
                    continue
                try:
                    spec = self.loader.parse_skill_dir(skill_dir, source=source)
                except SkillParseError as exc:
                    self._warnings.append(
                        {
                            "code": "invalid_skill_dir",
                            "source": source,
                            "path": str(skill_dir),
                            "message": str(exc),
                        }
                    )
                    continue
                if spec.name in specs:
                    self._duplicates.setdefault(spec.name, []).append(spec.path)
                    self._warnings.append(
                        {
                            "code": "duplicate_skill_name",
                            "skill_name": spec.name,
                            "kept": specs[spec.name].path,
                            "ignored": spec.path,
                            "source": source,
                        }
                    )
                    continue
                specs[spec.name] = spec
            _elapsed = time.perf_counter() - _t_root
            _root_timings.append((source, _elapsed, _n_dirs))
            if _elapsed > 1.0:
                try:
                    from ..core.debug_log import debug_log, is_debug_enabled
                    if is_debug_enabled():
                        debug_log("skills", f"slow root: {source} elapsed={_elapsed:.1f}s dirs={_n_dirs}")
                except Exception:
                    pass
        _t_scan = time.perf_counter()
        self._cache = specs
        # Write through to cross-instance cache
        cached: dict[str, Any] = dict(specs)
        cached["__warnings__"] = list(self._warnings)
        cached["__discovery_roots__"] = list(self._discovery_roots)
        cached["__duplicates__"] = dict(self._duplicates)
        SkillRegistry._specs_cache = cached
        SkillRegistry._cache_mtime = (
            self.lifecycle.store.config_path.stat().st_mtime
            if self.lifecycle.store.config_path.exists()
            else 0.0
        )
        SkillRegistry._cache_config_path = str(self.lifecycle.store.config_path)
        _t_end = time.perf_counter()
        try:
            from ..core.debug_log import debug_log, is_debug_enabled
            if is_debug_enabled():
                debug_log("skills",
                    f"_load_specs_uncached: total={_t_end-_t_total:.2f}s "
                    f"roots={_t_roots-_t_total:.2f}s scan={_t_scan-_t_roots:.2f}s "
                    f"writeback={_t_end-_t_scan:.3f}s specs={len(specs)} "
                    f"thread={threading.current_thread().name}"
                )
        except Exception:
            pass
        return specs

    def _iter_roots(self) -> list[tuple[str, Path]]:
        env_dirs = []
        raw_env = os.getenv("JARVIS_SKILL_DIRS", "")
        if raw_env.strip():
            env_dirs = [Path(part).expanduser().resolve() for part in raw_env.split(os.pathsep) if part.strip()]
        roots: list[tuple[str, Path]] = []
        for source in sorted(self.lifecycle.store.list_sources(), key=lambda item: (-item.priority, item.name.lower())):
            if not source.enabled:
                continue
            roots.append((f"source:{source.name}", Path(source.uri_or_path).expanduser().resolve()))
        roots.append(("user", (self.project_root / ".jarvis" / "skills").resolve()))
        roots.extend(("env", path) for path in env_dirs)
        roots.append(("project", (self.project_root / "skills").resolve()))
        roots.extend(("extra", path) for path in self.extra_dirs)
        roots.extend(("plugin", path) for path in self.plugin_skill_dirs)
        roots.append(("home", (self.project_root / ".jarvis" / "skills").resolve()))
        roots.append(("builtin", self.builtin_root))
        for sub_root in self._discover_skill_roots():
            roots.append(sub_root)
        return roots

    def _discover_skill_roots(self) -> list[tuple[str, Path]]:
        """Scan immediate subdirectories of project_root for known skill paths."""
        discovered: list[tuple[str, Path]] = []
        seen: set[str] = set()
        skill_dir_names = {"skills", ".codex/skills", ".agents/skills", "optional-skills"}
        try:
            for entry in sorted(self.project_root.iterdir()):
                if not entry.is_dir() or entry.name.startswith("."):
                    continue
                for name in skill_dir_names:
                    candidate = entry / name
                    try:
                        if candidate.is_dir() and any(candidate.rglob("SKILL.md")):
                            key = str(candidate.resolve())
                            if key not in seen:
                                seen.add(key)
                                discovered.append((f"discovered:{entry.name}", candidate.resolve()))
                    except (OSError, PermissionError):
                        pass
        except (OSError, PermissionError):
            pass
        return discovered

    _SKIP_DIRS = frozenset({
        ".git", "node_modules", "__pycache__", ".venv", "venv", ".pytest_cache",
        ".tox", ".mypy_cache", ".ruff_cache", "dist", "build", ".eggs",
        "__MACOSX", ".DS_Store",
    })
    _MAX_DEPTH = 6

    @staticmethod
    def _iter_skill_dirs(root: Path) -> list[Path]:
        if (root / "SKILL.md").exists():
            return [root]
        out: list[Path] = []
        try:
            for sk_md in root.rglob("SKILL.md"):
                skill_dir = sk_md.parent
                # Skip ignored directories anywhere in the path
                parts = set(skill_dir.relative_to(root).parts)
                if parts & SkillRegistry._SKIP_DIRS:
                    continue
                if len(skill_dir.relative_to(root).parts) > SkillRegistry._MAX_DEPTH:
                    continue
                out.append(skill_dir.resolve())
        except (OSError, PermissionError):
            pass
        return sorted(out)

    def _is_within_allowed_roots(self, path: Path, *, _roots: list[Path] | None = None) -> bool:
        roots = _roots if _roots is not None else [root for _, root in self._iter_roots()]
        resolved = path.resolve()
        for root in roots:
            try:
                resolved.relative_to(root)
                return True
            except ValueError:
                continue
        return False

    def lifecycle_state(self, name: str) -> dict[str, Any]:
        return self.lifecycle.lifecycle_state_for(self.get(name))

    def check_skill(self, name: str) -> dict[str, Any]:
        spec = self.get(name)
        duplicate_status = "shadowed" if self._duplicates.get(spec.name) else "primary"
        return self.lifecycle.check_skill(spec, duplicate_status=duplicate_status)

    def _is_prompt_enabled(self, spec: SkillSpec) -> bool:
        state = self.lifecycle.lifecycle_state_for(spec)
        return bool(state.get("enabled")) and not bool(state.get("quarantined"))
