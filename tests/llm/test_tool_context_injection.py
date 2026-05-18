"""Phase G1 tests — LLM Tool Context injection.

Verifies:
1. build_intent_classification_prompt accepts optional tool_context
2. Chat requests have NO tool context injected
3. Work requests include tool context
4. build_work_execution_prompt includes tool schemas without handlers
5. build_tool_context_section produces valid lightweight context
"""

from __future__ import annotations

import json

import pytest

from jarvis.core.tools.registry import ToolRegistry
from jarvis.core.tools.schema import ToolSpec
from jarvis.core.llm.prompt_builder import (
    build_intent_classification_prompt,
    build_work_execution_prompt,
    build_tool_context_section,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(ToolSpec(
        name="workspace.read_file",
        description="Read file contents",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string", "description": "File path"}},
            "required": ["path"],
        },
        output_schema={"type": "object"},
        risk_level="low",
        requires_approval=False,
        permissions={"read"},
    ))
    reg.register(ToolSpec(
        name="shell.run",
        description="Execute shell commands",
        input_schema={
            "type": "object",
            "properties": {"command": {"type": "string", "description": "Shell command"}},
            "required": ["command"],
        },
        output_schema={"type": "object"},
        risk_level="high",
        requires_approval=True,
        permissions={"shell"},
        handler=lambda ctx: None,  # Handler exists but should NOT be in context
    ))
    return reg


# ---------------------------------------------------------------------------
# Test: build_intent_classification_prompt with tool_context
# ---------------------------------------------------------------------------

class TestIntentClassificationPromptToolContext:
    """Tests for tool context injection in intent classification prompt."""

    def test_no_tool_context_by_default(self):
        """Without tool_context, prompt should NOT contain tool listings."""
        prompt = build_intent_classification_prompt(
            instructions=None,
            user_input="hello",
            envelope={"language": "zh"},
            examples=[],
        )
        assert "可用工具列表" not in prompt
        assert "workspace.read_file" not in prompt
        assert "shell.run" not in prompt

    def test_tool_context_included_when_provided(self):
        """With tool_context, prompt should contain tool listings."""
        reg = _make_registry()
        tc = reg.to_llm_tool_context()
        prompt = build_intent_classification_prompt(
            instructions=None,
            user_input="fix the bug",
            envelope={"language": "zh"},
            examples=[],
            tool_context=tc,
        )
        assert "可用工具列表" in prompt
        assert "workspace.read_file" in prompt
        assert "shell.run" in prompt

    def test_tool_context_excludes_handlers(self):
        """Tool context must NEVER include handler functions."""
        reg = _make_registry()
        tc = reg.to_llm_tool_context()
        prompt = build_intent_classification_prompt(
            instructions=None,
            user_input="test",
            envelope={"language": "en"},
            examples=[],
            tool_context=tc,
        )
        assert "handler" not in prompt
        assert "lambda" not in prompt
        assert "Callable" not in prompt

    def test_tool_context_includes_risk_and_approval(self):
        """Tool context should include risk_level and requires_approval."""
        reg = _make_registry()
        tc = reg.to_llm_tool_context()
        prompt = build_intent_classification_prompt(
            instructions=None,
            user_input="test",
            envelope={"language": "en"},
            examples=[],
            tool_context=tc,
        )
        assert "risk_level" in prompt
        assert "requires_approval" in prompt
        assert "high" in prompt  # shell.run risk
        assert "True" in prompt or "true" in prompt  # shell.run approval

    def test_tool_context_preserves_classification_structure(self):
        """Tool context should not break the prompt's classification structure."""
        reg = _make_registry()
        tc = reg.to_llm_tool_context()
        prompt = build_intent_classification_prompt(
            instructions=None,
            user_input="test",
            envelope={"language": "en"},
            examples=[],
            tool_context=tc,
        )
        # Core sections must still be present
        assert "response_mode" in prompt
        assert "分类判断原则" in prompt
        assert "输出 schema" in prompt
        assert "安全约束" in prompt


# ---------------------------------------------------------------------------
# Test: build_work_execution_prompt
# ---------------------------------------------------------------------------

class TestWorkExecutionPrompt:
    """Tests for work-path execution prompt."""

    def test_includes_tool_context(self):
        """Work execution prompt must include tool schemas."""
        reg = _make_registry()
        tc = reg.to_llm_tool_context()
        prompt = build_work_execution_prompt(
            instructions=None,
            user_input="fix the bug in parser.py",
            tool_context=tc,
        )
        assert "workspace.read_file" in prompt
        assert "shell.run" in prompt
        assert "Available Tools" in tc  # from registry output

    def test_excludes_handlers(self):
        """Work execution prompt must NOT include handler references."""
        reg = _make_registry()
        tc = reg.to_llm_tool_context()
        prompt = build_work_execution_prompt(
            instructions=None,
            user_input="test",
            tool_context=tc,
        )
        assert "handler" not in prompt.lower()
        assert "lambda" not in prompt

    def test_includes_user_input(self):
        """Prompt must include the original user request."""
        prompt = build_work_execution_prompt(
            instructions=None,
            user_input="帮我修复 bug",
            tool_context="no tools",
        )
        assert "帮我修复 bug" in prompt

    def test_includes_agent_request_when_provided(self):
        """Prompt should include routing info when agent_request is provided."""
        ar = {"is_work_request": True, "work_type": "agent_tool_loop", "required_tools": ["workspace.read_file"]}
        prompt = build_work_execution_prompt(
            instructions=None,
            user_input="test",
            tool_context="tools here",
            agent_request=ar,
        )
        assert "路由信息" in prompt
        assert "agent_tool_loop" in prompt
        assert "workspace.read_file" in prompt

    def test_includes_tool_results_for_multi_round(self):
        """Prompt should include previous tool results for multi-round."""
        results = [
            {"tool_name": "workspace.read_file", "ok": True, "output": "file contents here"},
            {"tool_name": "shell.run", "ok": False, "error": "command failed"},
        ]
        prompt = build_work_execution_prompt(
            instructions=None,
            user_input="continue",
            tool_context="tools",
            tool_results=results,
        )
        assert "上一步工具执行结果" in prompt
        assert "workspace.read_file" in prompt
        assert "command failed" in prompt

    def test_no_tool_results_section_by_default(self):
        """Without tool_results, prompt should NOT have results section."""
        prompt = build_work_execution_prompt(
            instructions=None,
            user_input="test",
            tool_context="tools",
        )
        assert "上一步工具执行结果" not in prompt

    def test_includes_safety_constraints(self):
        """Work execution prompt must include safety constraints."""
        prompt = build_work_execution_prompt(
            instructions=None,
            user_input="test",
            tool_context="tools",
        )
        assert "safety" in prompt.lower() or "安全" in prompt
        assert "approval" in prompt.lower() or "approval" in prompt

    def test_includes_json_only_tool_plan_contract(self):
        """Work prompt should force JSON-only tool-plan output contract."""
        prompt = build_work_execution_prompt(
            instructions=None,
            user_input="list files",
            tool_context="tools",
        )
        assert "single JSON object only" in prompt
        assert "No markdown" in prompt
        assert "Top-level keys MUST include: thought, tool_calls" in prompt
        assert "Do NOT use provider-native tool_calls" in prompt


# ---------------------------------------------------------------------------
# Test: build_tool_context_section (lightweight)
# ---------------------------------------------------------------------------

class TestToolContextSectionLightweight:
    """Tests for lightweight tool context builder."""

    def test_empty_list(self):
        result = build_tool_context_section(tool_names=[], tool_descriptions={})
        assert "No tools available" in result

    def test_basic_listing(self):
        result = build_tool_context_section(
            tool_names=["web.search", "web.fetch"],
            tool_descriptions={"web.search": "Search the web", "web.fetch": "Fetch URL"},
        )
        assert "web.search" in result
        assert "web.fetch" in result
        assert "Search the web" in result
        assert "Available Tools" in result

    def test_sorted_alphabetically(self):
        result = build_tool_context_section(
            tool_names=["shell.run", "patch.apply", "workspace.read_file"],
            tool_descriptions={n: n for n in ["shell.run", "patch.apply", "workspace.read_file"]},
        )
        # Verify alphabetical order
        pos_patch = result.index("patch.apply")
        pos_shell = result.index("shell.run")
        pos_workspace = result.index("workspace.read_file")
        assert pos_patch < pos_shell < pos_workspace

    def test_missing_description(self):
        result = build_tool_context_section(
            tool_names=["unknown_tool"],
            tool_descriptions={},
        )
        assert "unknown_tool" in result
        assert "No description" in result
