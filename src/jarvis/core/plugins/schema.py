"""Plugin manifest (plugin.json) schema — mirrors Claude Code format."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


_NAME_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")


@dataclass
class PluginAuthor:
    name: str
    email: str | None = None
    url: str | None = None

    @classmethod
    def from_dict(cls, d: dict | None) -> PluginAuthor | None:
        if not d:
            return None
        return cls(
            name=str(d.get("name", "")),
            email=d.get("email"),
            url=d.get("url"),
        )


@dataclass
class PluginManifest:
    """Represents a .claude-plugin/plugin.json file."""
    name: str
    version: str = "0.1.0"
    description: str = ""
    author: PluginAuthor | None = None
    homepage: str | None = None
    repository: str | None = None
    license: str | None = None
    keywords: list[str] = field(default_factory=list)

    # Component paths — all relative to plugin root, starting with ./
    commands: str | list[str] = "./commands"
    agents: str | list[str] = "./agents"
    skills: str | list[str] = "./skills"
    hooks: str = "./hooks/hooks.json"
    mcpServers: str = "./.mcp.json"

    # Runtime — set by loader
    _root: Path | None = field(default=None, repr=False)

    @property
    def root(self) -> Path:
        if self._root is None:
            raise RuntimeError("PluginManifest._root not set by loader")
        return self._root

    @classmethod
    def from_json(cls, path: Path) -> PluginManifest:
        """Load and validate a plugin.json file."""
        if not path.exists():
            raise FileNotFoundError(f"plugin.json not found: {path}")

        data = json.loads(path.read_text(encoding="utf-8"))
        name = str(data.get("name", "")).strip()
        if not name:
            raise ValueError(f"plugin.json missing required 'name' field: {path}")

        if not _NAME_RE.match(name):
            raise ValueError(
                f"Invalid plugin name '{name}': must be kebab-case, "
                f"start with a letter"
            )

        # Validate component paths: must be relative, start with ./, no ..
        def _check_path(val: str, field_name: str) -> None:
            if not val.startswith("./"):
                raise ValueError(
                    f"Plugin '{name}' {field_name} path must start with './': '{val}'"
                )
            if ".." in val:
                raise ValueError(
                    f"Plugin '{name}' {field_name} path must not contain '..': '{val}'"
                )

        for path_field in ("commands", "agents", "skills", "hooks", "mcpServers"):
            val = data.get(path_field)
            if isinstance(val, str):
                _check_path(val, path_field)
            elif isinstance(val, list):
                for v in val:
                    _check_path(str(v), path_field)

        manifest = cls(
            name=name,
            version=str(data.get("version", "0.1.0")),
            description=str(data.get("description", "")),
            author=PluginAuthor.from_dict(data.get("author")),
            homepage=data.get("homepage"),
            repository=data.get("repository"),
            license=data.get("license"),
            keywords=list(data.get("keywords", []) or []),
            commands=data.get("commands", "./commands"),
            agents=data.get("agents", "./agents"),
            skills=data.get("skills", "./skills"),
            hooks=str(data.get("hooks", "./hooks/hooks.json")),
            mcpServers=str(data.get("mcpServers", "./.mcp.json")),
            _root=path.parent.parent.resolve(),  # .claude-plugin/ → plugin root
        )
        return manifest

    def resolve_path(self, rel: str) -> Path:
        """Resolve a plugin-relative path to absolute."""
        return (self.root / rel).resolve()

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "name": self.name,
            "version": self.version,
            "description": self.description,
        }
        if self.author:
            d["author"] = {"name": self.author.name}
            if self.author.email:
                d["author"]["email"] = self.author.email
        if self.homepage:
            d["homepage"] = self.homepage
        if self.keywords:
            d["keywords"] = self.keywords
        return d
