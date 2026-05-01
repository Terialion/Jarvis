"""Tests for the core ToolRegistry."""

import sys
from pathlib import Path

import pytest

# Ensure src is in path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.jarvis.core.tools.schema import ToolCall, ToolContext, ToolResult, ToolSpec
from src.jarvis.core.tools.registry import ToolRegistry
from src.jarvis.core.tools.builtin import BUILTIN_TOOL_SPECS, register_builtin_tools


class TestToolRegistry:
    def test_empty_registry(self):
        reg = ToolRegistry()
        assert len(reg) == 0
        assert reg.list_names() == []

    def test_register_and_get(self):
        reg = ToolRegistry()
        spec = ToolSpec(
            name="test.tool",
            description="A test tool",
            input_schema={"type": "object", "properties": {}},
            output_schema={"type": "object"},
            risk_level="low",
            requires_approval=False,
            permissions={"read"},
        )
        reg.register(spec)
        assert reg.has("test.tool")
        assert len(reg) == 1
        got = reg.get("test.tool")
        assert got is not None
        assert got.name == "test.tool"

    def test_register_requires_name(self):
        reg = ToolRegistry()
        spec = ToolSpec(
            name="",
            description="empty name",
            input_schema={},
            output_schema={},
            risk_level="low",
            requires_approval=False,
            permissions=set(),
        )
        with pytest.raises(ValueError, match="non-empty name"):
            reg.register(spec)

    def test_get_nonexistent_returns_none(self):
        reg = ToolRegistry()
        assert reg.get("nonexistent") is None

    def test_list_all(self):
        reg = ToolRegistry()
        for i in range(3):
            reg.register(ToolSpec(
                name=f"tool.{i}",
                description=f"Tool {i}",
                input_schema={},
                output_schema={},
                risk_level="low",
                requires_approval=False,
                permissions=set(),
            ))
        assert len(reg.list_all()) == 3

    def test_list_names_sorted(self):
        reg = ToolRegistry()
        reg.register(ToolSpec(name="c", description="", input_schema={}, output_schema={}, risk_level="low", requires_approval=False, permissions=set()))
        reg.register(ToolSpec(name="a", description="", input_schema={}, output_schema={}, risk_level="low", requires_approval=False, permissions=set()))
        reg.register(ToolSpec(name="b", description="", input_schema={}, output_schema={}, risk_level="low", requires_approval=False, permissions=set()))
        assert reg.list_names() == ["a", "b", "c"]


class TestToolSpec:
    def test_to_llm_summary_excludes_handler(self):
        handler = lambda args, ctx: ToolResult(tool_name="test", ok=True)
        spec = ToolSpec(
            name="test.tool",
            description="A test tool",
            input_schema={"type": "object", "properties": {"x": {"type": "string"}}},
            output_schema={"type": "object"},
            risk_level="medium",
            requires_approval=True,
            permissions={"write", "shell"},
            handler=handler,
        )
        summary = spec.to_llm_summary()
        assert "handler" not in summary
        assert summary["name"] == "test.tool"
        assert summary["requires_approval"] is True
        assert "shell" in summary["permissions"]

    def test_to_dict_excludes_handler(self):
        spec = ToolSpec(
            name="test",
            description="test",
            input_schema={},
            output_schema={},
            risk_level="low",
            requires_approval=False,
            permissions=set(),
        )
        d = spec.to_dict()
        assert "handler" not in d


class TestToolCall:
    def test_tool_call_creation(self):
        call = ToolCall(tool_name="workspace.list_dir", arguments={"path": "."}, reason="User asked for listing")
        assert call.tool_name == "workspace.list_dir"
        assert call.arguments == {"path": "."}
        assert call.reason == "User asked for listing"

    def test_tool_call_to_dict(self):
        call = ToolCall(tool_name="shell.run", arguments={"command": "pytest"})
        d = call.to_dict()
        assert d["tool_name"] == "shell.run"


class TestToolResult:
    def test_success_result(self):
        r = ToolResult(tool_name="test", ok=True, output={"key": "value"})
        assert r.ok is True
        assert r.error is None

    def test_error_result(self):
        r = ToolResult(tool_name="test", ok=False, error="something failed")
        assert r.ok is False
        assert r.error == "something failed"

    def test_result_to_dict(self):
        r = ToolResult(tool_name="test", ok=True, output="hello", risk_level="low", metadata={"k": "v"})
        d = r.to_dict()
        assert d["ok"] is True
        assert d["output"] == "hello"
        assert d["metadata"]["k"] == "v"


class TestLLMToolContext:
    def test_empty_registry_context(self):
        reg = ToolRegistry()
        ctx = reg.to_llm_tool_context()
        assert "No tools available" in ctx

    def test_registry_llm_context_contains_tool_info(self):
        reg = ToolRegistry()
        reg.register(ToolSpec(
            name="test.read",
            description="Read a test file",
            input_schema={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
            output_schema={"type": "object"},
            risk_level="medium",
            requires_approval=False,
            permissions={"repo_read"},
        ))
        ctx = reg.to_llm_tool_context()
        assert "test.read" in ctx
        assert "Read a test file" in ctx
        assert "risk_level: medium" in ctx
        assert "repo_read" in ctx
        # Must NOT contain handler
        assert "handler" not in ctx

    def test_registry_llm_json(self):
        reg = ToolRegistry()
        reg.register(ToolSpec(
            name="a", description="desc", input_schema={}, output_schema={}, risk_level="low", requires_approval=False, permissions=set(),
        ))
        json_list = reg.to_llm_json()
        assert len(json_list) == 1
        assert json_list[0]["name"] == "a"
        assert "handler" not in json_list[0]
