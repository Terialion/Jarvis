"""Load plugin components: commands, agents, hooks, MCP configs."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


class ComponentLoader:
    """Load individual plugin components from their source directories."""

    def load_commands(self, commands_dir: Path) -> list[dict[str, Any]]:
        """Load slash command definitions from a commands/ directory."""
        if not commands_dir.is_dir():
            return []
        commands: list[dict[str, Any]] = []
        for md_file in sorted(commands_dir.glob("*.md")):
            try:
                frontmatter = self._parse_frontmatter(md_file)
                name = frontmatter.get("name") or md_file.stem
                commands.append({
                    "name": name,
                    "description": frontmatter.get("description", ""),
                    "path": str(md_file),
                    "frontmatter": frontmatter,
                })
            except Exception:
                continue
        return commands

    def load_agents(self, agents_dir: Path) -> list[dict[str, Any]]:
        """Load agent definitions from an agents/ directory."""
        if not agents_dir.is_dir():
            return []
        agents: list[dict[str, Any]] = []
        for md_file in sorted(agents_dir.glob("*.md")):
            try:
                frontmatter = self._parse_frontmatter(md_file)
                agents.append({
                    "name": frontmatter.get("name") or md_file.stem,
                    "description": frontmatter.get("description", ""),
                    "capabilities": frontmatter.get("capabilities", []),
                    "path": str(md_file),
                })
            except Exception:
                continue
        return agents

    def load_hooks(self, hooks_path: Path) -> dict[str, Any]:
        """Load hook configuration from hooks.json."""
        raw = json.loads(hooks_path.read_text(encoding="utf-8"))
        return {
            "path": str(hooks_path),
            "description": raw.get("description", ""),
            "hooks": raw.get("hooks", {}),
        }

    def load_mcp_config(self, mcp_path: Path) -> dict[str, Any]:
        """Load MCP server configuration from .mcp.json."""
        raw = json.loads(mcp_path.read_text(encoding="utf-8"))
        return {
            "path": str(mcp_path),
            "mcpServers": raw.get("mcpServers", {}),
            "description": raw.get("description", ""),
        }

    @staticmethod
    def _parse_frontmatter(md_path: Path) -> dict[str, Any]:
        """Extract YAML frontmatter from a markdown file."""
        text = md_path.read_text(encoding="utf-8")
        m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
        if not m:
            return {}
        try:
            import yaml
            return yaml.safe_load(m.group(1)) or {}
        except Exception:
            return {}
