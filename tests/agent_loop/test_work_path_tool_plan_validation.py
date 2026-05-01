"""Tests for tool_plan JSON validation in the work path.

Verifies that:
- Valid JSON tool calls are executed
- Invalid JSON is treated as final text answer
- Empty tool_calls means completion
- Missing tool_name is rejected
- Code fences are properly stripped
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from src.jarvis.core.tools.registry import ToolRegistry
from src.jarvis.core.tools.builtin import register_builtin_tools
from src.jarvis.core.tools.runtime import ToolRuntime, ApprovalGate
from src.jarvis.core.tools.loop import AgentToolLoop
from src.jarvis.core.tools.schema import ToolContext
from src.jarvis.core.llm.provider import FakeLLMProvider


def _build_loop(
    llm_provider=None,
    auto_approve: bool = True,
    max_rounds: int = 5,
) -> AgentToolLoop:
    """Helper to build a standard AgentToolLoop."""
    reg = ToolRegistry()
    register_builtin_tools(reg)
    runtime = ToolRuntime(
        registry=reg,
        permission_mode="workspace_write",
        approval_gate=ApprovalGate(auto_approve=auto_approve),
    )
    return AgentToolLoop(
        registry=reg,
        runtime=runtime,
        llm_provider=llm_provider,
        max_rounds=max_rounds,
    )


def _tool_plan_json(tool_name: str, arguments: dict | None = None, reason: str = "") -> str:
    """Build a valid tool_plan JSON."""
    plan = {
        "thought": f"Calling {tool_name}",
        "tool_calls": [
            {
                "tool_name": tool_name,
                "arguments": arguments or {},
                "reason": reason or f"Need {tool_name}",
            }
        ],
    }
    return json.dumps(plan, ensure_ascii=False)


# ---------------------------------------------------------------------------
# JSON validation tests
# ---------------------------------------------------------------------------

class TestToolPlanValidation:
    """Tests for parsing and validating LLM tool_plan output."""

    def test_valid_json_tool_calls_executed(self):
        """Valid JSON with correct tool_name executes successfully."""
        provider = FakeLLMProvider(response=_tool_plan_json("workspace.status"))
        loop = _build_loop(llm_provider=provider)
        result = loop.execute("我现在的目录是什么")

        assert result.total_tool_calls >= 1
        # Should have a step with tool_calls
        tool_steps = [s for s in result.steps if s.tool_calls]
        assert len(tool_steps) >= 1

    def test_invalid_json_returns_as_text(self):
        """Non-JSON response is treated as final text answer."""
        provider = FakeLLMProvider(response="这是我的最终回答，不需要调用工具。")
        loop = _build_loop(llm_provider=provider)
        result = loop.execute("解释什么是 CLI")

        assert result.total_tool_calls == 0
        assert result.response == "这是我的最终回答，不需要调用工具。"
        # Should be marked as final
        final_steps = [s for s in result.steps if s.is_final]
        assert len(final_steps) >= 1

    def test_empty_tool_calls_means_done(self):
        """JSON with tool_calls=[] means LLM is done."""
        response = json.dumps({
            "thought": "我已经知道答案了",
            "tool_calls": [],
        }, ensure_ascii=False)
        provider = FakeLLMProvider(response=response)
        loop = _build_loop(llm_provider=provider)
        result = loop.execute("告诉我一件事")

        assert result.total_tool_calls == 0
        assert "已经知道答案" in result.response

    def test_missing_tool_name_error(self):
        """JSON with tool_calls entry missing tool_name -> tool_not_found."""
        response = json.dumps({
            "thought": "Try something",
            "tool_calls": [{"arguments": {}, "reason": "test"}],
        }, ensure_ascii=False)
        provider = FakeLLMProvider(response=response)
        loop = _build_loop(llm_provider=provider)
        # Use exact work-path matching pattern
        result = loop.execute("我现在的目录是什么")

        assert result.total_tool_calls >= 1
        # Missing tool_name results in empty string -> tool_not_found
        tool_results = []
        for s in result.steps:
            tool_results.extend(s.tool_results)
        assert any("tool_not_found" in str(r) for r in tool_results)

    def test_code_fence_stripped(self):
        """LLM response wrapped in ```json...``` is parsed correctly."""
        inner = _tool_plan_json("workspace.status")
        response = f"```json\n{inner}\n```"
        provider = FakeLLMProvider(response=response)
        loop = _build_loop(llm_provider=provider)
        result = loop.execute("我现在的目录是什么")

        # Should successfully parse the JSON inside code fences
        assert result.total_tool_calls >= 1
        tool_steps = [s for s in result.steps if s.tool_calls]
        assert len(tool_steps) >= 1

    def test_code_fence_no_lang_stripped(self):
        """LLM response wrapped in ``` ... ``` (no language tag) is parsed."""
        inner = _tool_plan_json("workspace.status")
        response = f"```\n{inner}\n```"
        provider = FakeLLMProvider(response=response)
        loop = _build_loop(llm_provider=provider)
        result = loop.execute("我现在的目录是什么")

        assert result.total_tool_calls >= 1

    def test_plain_json_no_fences(self):
        """Plain JSON without fences is also parsed."""
        provider = FakeLLMProvider(response=_tool_plan_json("workspace.status"))
        loop = _build_loop(llm_provider=provider)
        result = loop.execute("我现在的目录是什么")

        assert result.total_tool_calls >= 1

    def test_json_list_not_dict_treated_as_text(self):
        """JSON that is a list (not dict) is treated as final text."""
        response = json.dumps([{"tool_name": "workspace.status"}])
        provider = FakeLLMProvider(response=response)
        loop = _build_loop(llm_provider=provider)
        result = loop.execute("测试")

        # A JSON list is not a dict, so _parse_llm_response returns None
        # It's treated as final text
        assert result.total_tool_calls == 0

    def test_malformed_json_returns_parse_error(self):
        """Malformed JSON tool-plan-looking output should return parse_error diagnostics."""
        provider = FakeLLMProvider(response='{"thought": "test", "tool_calls": [broken}')
        loop = _build_loop(llm_provider=provider)
        result = loop.execute("运行 pytest")

        assert result.total_tool_calls == 0
        assert "parse_error" in result.response
        assert "content_preview=" in result.response

    def test_text_wrapped_json_object_can_be_extracted(self):
        """A JSON object wrapped with short text should still be parsed."""
        inner = _tool_plan_json("workspace.status")
        provider = FakeLLMProvider(response=f"Plan:\n{inner}\nThanks")
        loop = _build_loop(llm_provider=provider)
        result = loop.execute("列一下当前目录")

        assert result.total_tool_calls >= 1


class TestParseLLMResponseUnit:
    """Unit tests for AgentToolLoop._parse_llm_response()."""

    def test_parse_valid_json(self):
        raw = '{"thought": "test", "tool_calls": [{"tool_name": "x"}]}'
        result = AgentToolLoop._parse_llm_response(raw)
        assert result is not None
        assert result["tool_calls"][0]["tool_name"] == "x"

    def test_parse_none_for_non_json(self):
        raw = "This is just plain text"
        result = AgentToolLoop._parse_llm_response(raw)
        assert result is None

    def test_parse_strips_code_fence_json(self):
        raw = '```json\n{"tool_calls": []}\n```'
        result = AgentToolLoop._parse_llm_response(raw)
        assert result is not None
        assert result["tool_calls"] == []

    def test_parse_strips_code_fence_generic(self):
        raw = '```\n{"tool_calls": []}\n```'
        result = AgentToolLoop._parse_llm_response(raw)
        assert result is not None

    def test_parse_list_returns_none(self):
        raw = '[1, 2, 3]'
        result = AgentToolLoop._parse_llm_response(raw)
        assert result is None

    def test_parse_empty_string_returns_none(self):
        result = AgentToolLoop._parse_llm_response("")
        assert result is None
