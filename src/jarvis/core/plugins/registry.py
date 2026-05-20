"""PluginRegistry — loads plugins and registers their components."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .discovery import PluginDiscovery
from .loader import ComponentLoader
from .schema import PluginManifest


class PluginRegistry:
    """Central registry for all plugins and their components."""

    def __init__(
        self,
        *,
        project_root: str | Path | None = None,
        user_plugins_dir: str | Path | None = None,
    ):
        self.discovery = PluginDiscovery(
            project_root=project_root,
            user_plugins_dir=user_plugins_dir,
        )
        self._manifests: dict[str, PluginManifest] = {}
        self._loader = ComponentLoader()
        self._commands: list[dict[str, Any]] = []
        self._agents: list[dict[str, Any]] = []
        self._skill_dirs: list[Path] = []
        self._hooks_configs: list[dict[str, Any]] = []
        self._mcp_configs: list[dict[str, Any]] = []

    @property
    def manifests(self) -> list[PluginManifest]:
        return list(self._manifests.values())

    def load_all(self) -> int:
        """Discover and load all plugins. Returns count of loaded plugins."""
        discovered = self.discovery.discover()
        loaded = 0
        for m in discovered:
            try:
                self._load_plugin(m)
                loaded += 1
            except Exception:
                pass  # Skip broken plugins
        return loaded

    def _load_plugin(self, m: PluginManifest) -> None:
        self._manifests[m.name] = m

        # Load commands
        cmd_paths = [m.commands] if isinstance(m.commands, str) else m.commands
        for p in cmd_paths:
            for cmd in self._loader.load_commands(m.resolve_path(p)):
                cmd["plugin"] = m.name
                self._commands.append(cmd)

        # Load agents
        agent_paths = [m.agents] if isinstance(m.agents, str) else m.agents
        for p in agent_paths:
            for agent in self._loader.load_agents(m.resolve_path(p)):
                agent["plugin"] = m.name
                self._agents.append(agent)

        # Collect skill directories
        skill_paths = [m.skills] if isinstance(m.skills, str) else m.skills
        for p in skill_paths:
            resolved = m.resolve_path(p)
            if resolved.is_dir():
                self._skill_dirs.append(resolved)

        # Load hooks
        hooks_path = m.resolve_path(m.hooks)
        if hooks_path.exists():
            try:
                self._hooks_configs.append(
                    self._loader.load_hooks(hooks_path)
                )
            except Exception:
                pass

        # Load MCP config
        mcp_path = m.resolve_path(m.mcpServers)
        if mcp_path.exists():
            try:
                cfg = self._loader.load_mcp_config(mcp_path)
                cfg["_plugin"] = m.name
                self._mcp_configs.append(cfg)
            except Exception:
                pass

    # ── Queries ───────────────────────────────────────────────────────

    def list_commands(self) -> list[dict[str, Any]]:
        return list(self._commands)

    def list_agents(self) -> list[dict[str, Any]]:
        return list(self._agents)

    def list_skill_dirs(self) -> list[Path]:
        return list(self._skill_dirs)

    def list_hooks_configs(self) -> list[dict[str, Any]]:
        return list(self._hooks_configs)

    def list_mcp_configs(self) -> list[dict[str, Any]]:
        return list(self._mcp_configs)

    def get_plugin(self, name: str) -> PluginManifest | None:
        return self._manifests.get(name)
