"""Skill registry, discovery, and metadata index export."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .lifecycle import SkillLifecycleManager
from .loader import SkillLoader, SkillParseError
from .schema import SkillSpec


class SkillRegistry:
    def __init__(
        self,
        *,
        builtin_root: str | Path | None = None,
        extra_dirs: list[str | Path] | None = None,
        project_root: str | Path | None = None,
        loader: SkillLoader | None = None,
        lifecycle: SkillLifecycleManager | None = None,
    ) -> None:
        self.loader = loader or SkillLoader()
        self.project_root = Path(project_root or Path.cwd()).resolve()
        self.builtin_root = Path(builtin_root or Path(__file__).resolve().parent / "builtin").resolve()
        self.extra_dirs = [Path(p).resolve() for p in list(extra_dirs or [])]
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
        rows: list[dict[str, Any]] = []
        for spec in specs:
            row = spec.to_index_row()
            row.update(self.lifecycle.lifecycle_state_for(spec))
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
        if self._cache is not None:
            return self._cache
        specs: dict[str, SkillSpec] = {}
        self._warnings = []
        self._discovery_roots = []
        self._duplicates = {}
        for source, root in self._iter_roots():
            self._discovery_roots.append({"source": source, "path": str(root)})
            if not root.exists():
                continue
            for skill_dir in self._iter_skill_dirs(root):
                if not self._is_within_allowed_roots(skill_dir):
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
        self._cache = specs
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
        roots.append(("home", Path.home().joinpath(".jarvis", "skills").resolve()))
        roots.append(("builtin", self.builtin_root))
        return roots

    @staticmethod
    def _iter_skill_dirs(root: Path) -> list[Path]:
        if (root / "SKILL.md").exists():
            return [root]
        out: list[Path] = []
        for candidate in sorted(root.iterdir() if root.exists() else []):
            if candidate.is_dir() and (candidate / "SKILL.md").exists():
                out.append(candidate.resolve())
        return out

    def _is_within_allowed_roots(self, path: Path) -> bool:
        roots = [root for _, root in self._iter_roots()]
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
