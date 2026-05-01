"""Tests for builtin tool specifications."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.jarvis.core.tools.schema import ToolContext
from src.jarvis.core.tools.registry import ToolRegistry
from src.jarvis.core.tools.builtin import BUILTIN_TOOL_SPECS, register_builtin_tools


def _make_registry() -> ToolRegistry:
    reg = ToolRegistry()
    register_builtin_tools(reg)
    return reg


class TestBuiltinToolSpecs:
    def test_all_specs_have_required_fields(self):
        """Every builtin spec must have name, description, schema, risk, permissions."""
        for spec in BUILTIN_TOOL_SPECS:
            assert spec.name, f"{spec.name}: missing name"
            assert spec.description, f"{spec.name}: missing description"
            assert isinstance(spec.input_schema, dict), f"{spec.name}: input_schema not dict"
            assert isinstance(spec.output_schema, dict), f"{spec.name}: output_schema not dict"
            assert spec.risk_level in {"low", "medium", "high", "blocked"}, f"{spec.name}: invalid risk_level"
            assert isinstance(spec.permissions, set), f"{spec.name}: permissions not set"

    def test_minimum_tool_count(self):
        """At least 11 tools must be registered."""
        reg = _make_registry()
        assert len(reg) >= 11

    def test_shell_run_requires_approval(self):
        spec = next(s for s in BUILTIN_TOOL_SPECS if s.name == "shell.run")
        assert spec.requires_approval is True
        assert "shell" in spec.permissions

    def test_patch_apply_requires_approval(self):
        spec = next(s for s in BUILTIN_TOOL_SPECS if s.name == "patch.apply")
        assert spec.requires_approval is True
        assert "write" in spec.permissions

    def test_workspace_list_dir_no_approval(self):
        spec = next(s for s in BUILTIN_TOOL_SPECS if s.name == "workspace.list_dir")
        assert spec.requires_approval is False
        assert spec.risk_level == "low"

    def test_workspace_status_no_approval(self):
        spec = next(s for s in BUILTIN_TOOL_SPECS if s.name == "workspace.status")
        assert spec.requires_approval is False
        assert spec.risk_level == "low"

    def test_web_search_requires_network(self):
        spec = next(s for s in BUILTIN_TOOL_SPECS if s.name == "web.search")
        assert "network" in spec.permissions

    def test_web_fetch_requires_network(self):
        spec = next(s for s in BUILTIN_TOOL_SPECS if s.name == "web.fetch")
        assert "network" in spec.permissions

    def test_skill_invoke_no_trust_from_md(self):
        """skill.invoke must require approval regardless of SKILL.md."""
        spec = next(s for s in BUILTIN_TOOL_SPECS if s.name == "skill.invoke")
        assert spec.requires_approval is True

    def test_read_file_refuses_env(self):
        """workspace.read_file must refuse .env files."""
        ctx = ToolContext(workspace_root=str(ROOT))
        spec = next(s for s in BUILTIN_TOOL_SPECS if s.name == "workspace.read_file")
        result = spec.handler({"path": ".env"}, ctx)
        assert result.ok is False
        assert "safety_refusal" in result.error

    def test_read_file_refuses_ssh_key(self):
        """workspace.read_file must refuse SSH private keys."""
        ctx = ToolContext(workspace_root=str(ROOT))
        spec = next(s for s in BUILTIN_TOOL_SPECS if s.name == "workspace.read_file")
        result = spec.handler({"path": "~/.ssh/id_rsa"}, ctx)
        assert result.ok is False
        assert "safety_refusal" in result.error

    def test_read_file_refuses_token(self):
        """workspace.read_file must refuse token files."""
        ctx = ToolContext(workspace_root=str(ROOT))
        spec = next(s for s in BUILTIN_TOOL_SPECS if s.name == "workspace.read_file")
        result = spec.handler({"path": "/tmp/token"}, ctx)
        assert result.ok is False

    def test_all_tools_have_handlers(self):
        """Every builtin tool must have a handler."""
        for spec in BUILTIN_TOOL_SPECS:
            assert spec.handler is not None, f"{spec.name}: missing handler"

    def test_llm_summary_excludes_all_handlers(self):
        """LLM summary must not expose any handler."""
        for spec in BUILTIN_TOOL_SPECS:
            summary = spec.to_llm_summary()
            assert "handler" not in summary, f"{spec.name}: handler leaked to LLM summary"
