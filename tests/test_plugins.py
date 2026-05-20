"""Tests for plugin packaging — manifest, discovery, component loading."""
import json
from pathlib import Path

import pytest


class TestPluginManifest:
    """Test PluginManifest parsing and validation."""

    def test_minimal_manifest(self):
        from jarvis.core.plugins.schema import PluginManifest
        m = PluginManifest(name="my-plugin")
        assert m.name == "my-plugin"
        assert m.version == "0.1.0"

    def test_from_json_minimal(self, tmp_path: Path):
        from jarvis.core.plugins.schema import PluginManifest

        plugin_root = tmp_path / "my-plugin"
        claude_dir = plugin_root / ".claude-plugin"
        claude_dir.mkdir(parents=True)
        manifest_path = claude_dir / "plugin.json"
        manifest_path.write_text(json.dumps({"name": "my-plugin"}))

        m = PluginManifest.from_json(manifest_path)
        assert m.name == "my-plugin"
        assert m.root == plugin_root

    def test_from_json_invalid_name(self, tmp_path: Path):
        from jarvis.core.plugins.schema import PluginManifest

        manifest_path = tmp_path / "plugin.json"
        manifest_path.write_text(json.dumps({"name": "Invalid Name!"}))

        with pytest.raises(ValueError):
            PluginManifest.from_json(manifest_path)

    def test_from_json_missing_name(self, tmp_path: Path):
        from jarvis.core.plugins.schema import PluginManifest

        manifest_path = tmp_path / "plugin.json"
        manifest_path.write_text(json.dumps({"version": "1.0.0"}))

        with pytest.raises(ValueError):
            PluginManifest.from_json(manifest_path)

    def test_resolve_path(self, tmp_path: Path):
        from jarvis.core.plugins.schema import PluginManifest

        plugin_root = tmp_path / "my-plugin"
        claude_dir = plugin_root / ".claude-plugin"
        claude_dir.mkdir(parents=True)
        manifest_path = claude_dir / "plugin.json"
        manifest_path.write_text(json.dumps({"name": "my-plugin"}))

        m = PluginManifest.from_json(manifest_path)
        resolved = m.resolve_path("./skills")
        assert resolved == plugin_root / "skills"
        assert resolved.is_absolute()


class TestPluginDiscovery:
    """Test plugin discovery across scopes."""

    def test_discover_project_plugin(self, tmp_path: Path):
        from jarvis.core.plugins.discovery import discover_plugins

        plugin_root = tmp_path / "test-plugin"
        claude_dir = plugin_root / ".claude-plugin"
        claude_dir.mkdir(parents=True)
        (claude_dir / "plugin.json").write_text(
            json.dumps({"name": "test-plugin"})
        )

        plugins = discover_plugins(project_root=tmp_path)
        names = [p.name for p in plugins]
        assert "test-plugin" in names

    def test_empty_project(self, tmp_path: Path):
        from jarvis.core.plugins.discovery import discover_plugins
        plugins = discover_plugins(project_root=tmp_path)
        assert len(plugins) == 0

    def test_discover_multiple_plugins(self, tmp_path: Path):
        from jarvis.core.plugins.discovery import discover_plugins

        for name in ["plugin-a", "plugin-b"]:
            root = tmp_path / name / ".claude-plugin"
            root.mkdir(parents=True)
            (root / "plugin.json").write_text(json.dumps({"name": name}))

        plugins = discover_plugins(project_root=tmp_path)
        names = [p.name for p in plugins]
        assert "plugin-a" in names
        assert "plugin-b" in names

    def test_discover_skips_hidden_dirs(self, tmp_path: Path):
        from jarvis.core.plugins.discovery import discover_plugins

        hidden = tmp_path / ".hidden" / ".claude-plugin"
        hidden.mkdir(parents=True)
        (hidden / "plugin.json").write_text(json.dumps({"name": "hidden-plugin"}))

        plugins = discover_plugins(project_root=tmp_path)
        names = [p.name for p in plugins]
        assert "hidden-plugin" not in names


class TestComponentLoader:
    """Test loading commands, agents, hooks, MCP from plugin dirs."""

    def test_load_commands(self, tmp_path: Path):
        from jarvis.core.plugins.loader import ComponentLoader

        cmds_dir = tmp_path / "commands"
        cmds_dir.mkdir()
        (cmds_dir / "lint.md").write_text(
            "---\nname: lint\ndescription: Run linter\n---\n\n# Lint\n\nRun linting."
        )

        loader = ComponentLoader()
        commands = loader.load_commands(cmds_dir)
        assert len(commands) == 1
        assert commands[0]["name"] == "lint"
        assert commands[0]["description"] == "Run linter"

    def test_load_commands_empty_dir(self, tmp_path: Path):
        from jarvis.core.plugins.loader import ComponentLoader

        cmds_dir = tmp_path / "commands"
        cmds_dir.mkdir()
        loader = ComponentLoader()
        assert loader.load_commands(cmds_dir) == []

    def test_load_commands_nonexistent(self, tmp_path: Path):
        from jarvis.core.plugins.loader import ComponentLoader

        loader = ComponentLoader()
        assert loader.load_commands(tmp_path / "nonexistent") == []

    def test_load_agents(self, tmp_path: Path):
        from jarvis.core.plugins.loader import ComponentLoader

        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "reviewer.md").write_text(
            "---\nname: reviewer\ndescription: Code reviewer\ncapabilities:\n  - read\n  - grep\n---\n\n# Reviewer"
        )

        loader = ComponentLoader()
        agents = loader.load_agents(agents_dir)
        assert len(agents) == 1
        assert agents[0]["name"] == "reviewer"
        assert "read" in agents[0]["capabilities"]

    def test_load_hooks(self, tmp_path: Path):
        from jarvis.core.plugins.loader import ComponentLoader

        hooks_path = tmp_path / "hooks.json"
        hooks_path.write_text(json.dumps({
            "description": "Test hooks",
            "hooks": {
                "pre_tool_use": [{"matcher": "bash:*"}],
            },
        }))

        loader = ComponentLoader()
        config = loader.load_hooks(hooks_path)
        assert config["description"] == "Test hooks"
        assert "pre_tool_use" in config["hooks"]

    def test_load_mcp_config(self, tmp_path: Path):
        from jarvis.core.plugins.loader import ComponentLoader

        mcp_path = tmp_path / ".mcp.json"
        mcp_path.write_text(json.dumps({
            "mcpServers": {
                "test-server": {
                    "command": "python",
                    "args": ["-m", "test_mcp_server"],
                },
            },
        }))

        loader = ComponentLoader()
        config = loader.load_mcp_config(mcp_path)
        assert "test-server" in config["mcpServers"]


class TestPluginRegistryIntegration:
    """Test PluginRegistry loads and queries components."""

    def test_load_all_discovers_plugins(self, tmp_path: Path):
        from jarvis.core.plugins.registry import PluginRegistry

        plugin_root = tmp_path / "my-plugin" / ".claude-plugin"
        plugin_root.mkdir(parents=True)
        (plugin_root / "plugin.json").write_text(json.dumps({"name": "my-plugin"}))

        reg = PluginRegistry(project_root=tmp_path)
        count = reg.load_all()
        assert count >= 1
        assert reg.get_plugin("my-plugin") is not None

    def test_load_commands_with_plugin_tag(self, tmp_path: Path):
        from jarvis.core.plugins.registry import PluginRegistry

        plugin_root = tmp_path / "my-plugin" / ".claude-plugin"
        plugin_root.mkdir(parents=True)
        cmds_dir = tmp_path / "my-plugin" / "commands"
        cmds_dir.mkdir(parents=True)
        (cmds_dir / "lint.md").write_text(
            "---\nname: lint\ndescription: Lint code\n---\n\n# Lint"
        )
        (plugin_root / "plugin.json").write_text(json.dumps({"name": "my-plugin"}))

        reg = PluginRegistry(project_root=tmp_path)
        reg.load_all()
        commands = reg.list_commands()
        assert len(commands) >= 1
        assert commands[0]["plugin"] == "my-plugin"

    def test_list_skill_dirs(self, tmp_path: Path):
        from jarvis.core.plugins.registry import PluginRegistry

        plugin_root = tmp_path / "my-plugin" / ".claude-plugin"
        plugin_root.mkdir(parents=True)
        skills_dir = tmp_path / "my-plugin" / "skills"
        skills_dir.mkdir(parents=True)
        (plugin_root / "plugin.json").write_text(json.dumps({"name": "my-plugin"}))

        reg = PluginRegistry(project_root=tmp_path)
        reg.load_all()
        skill_dirs = reg.list_skill_dirs()
        assert len(skill_dirs) >= 1

    def test_get_plugin_nonexistent(self, tmp_path: Path):
        from jarvis.core.plugins.registry import PluginRegistry

        reg = PluginRegistry(project_root=tmp_path)
        assert reg.get_plugin("nonexistent") is None


class TestSkillRegistryPluginDirs:
    """Test SkillRegistry integration with plugin_skill_dirs."""

    def test_plugin_dirs_in_roots(self, tmp_path: Path):
        from jarvis.skills.registry import SkillRegistry

        plugin_dir = tmp_path / "plugin-skills"
        plugin_dir.mkdir()
        (plugin_dir / "SKILL.md").write_text("# Plugin Skill")

        reg = SkillRegistry(project_root=tmp_path, plugin_skill_dirs=[plugin_dir])
        roots = reg._iter_roots()
        plugin_roots = [r for r in roots if r[0] == "plugin"]
        assert len(plugin_roots) >= 1
        assert any(plugin_dir.resolve() == r[1] for r in plugin_roots)

    def test_empty_plugin_dirs(self, tmp_path: Path):
        from jarvis.skills.registry import SkillRegistry

        reg = SkillRegistry(project_root=tmp_path, plugin_skill_dirs=[])
        roots = reg._iter_roots()
        plugin_roots = [r for r in roots if r[0] == "plugin"]
        assert len(plugin_roots) == 0


class TestHookRegistryPluginHooks:
    """Test HookRegistry plugin hook registration."""

    def test_register_plugin_hooks(self):
        from jarvis.core.hooks.registry import HookRegistry

        reg = HookRegistry()
        configs = [{
            "path": "/tmp/plugin/hooks.json",
            "description": "Test",
            "hooks": {
                "pre_tool_use": [{"matcher": "bash:*"}],
                "post_tool_use": [{"matcher": "*"}],
            },
        }]
        count = reg.register_plugin_hooks(configs)
        assert count == 2
        assert len(reg.list_plugin_hooks()) == 1

    def test_register_empty_hooks(self):
        from jarvis.core.hooks.registry import HookRegistry

        reg = HookRegistry()
        count = reg.register_plugin_hooks([])
        assert count == 0
