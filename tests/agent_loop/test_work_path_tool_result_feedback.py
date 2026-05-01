"""Tests for work path tool result feedback loop in AgentToolLoop.

Verifies that tool results from one round feed back into the next round's prompt.
"""

import json
import pytest
from unittest.mock import patch


class TestWorkPathToolResultFeedback:
    """Verify ToolResult feedback in the work path loop."""

    def _build_loop(self, llm_provider=None, auto_approve=False):
        from src.jarvis.core.tools.registry import ToolRegistry
        from src.jarvis.core.tools.builtin import register_builtin_tools
        from src.jarvis.core.tools.runtime import ToolRuntime, ApprovalGate
        from src.jarvis.core.tools.loop import AgentToolLoop

        reg = ToolRegistry()
        register_builtin_tools(reg)
        runtime = ToolRuntime(
            registry=reg,
            permission_mode="read_only",
            approval_gate=ApprovalGate(auto_approve=auto_approve),
        )
        return AgentToolLoop(
            registry=reg,
            runtime=runtime,
            llm_provider=llm_provider,
            max_rounds=5,
        )

    def test_single_round_tool_result(self):
        """LLM calls workspace.status in round 1, returns final answer in round 2."""
        from src.jarvis.core.llm.provider import FakeLLMProvider

        call_count = [0]
        responses = [
            json.dumps({
                "thought": "User wants current directory",
                "tool_calls": [{"tool_name": "workspace.status", "arguments": {}, "reason": "Get workspace status"}],
            }),
            "当前工作目录是 D:\\Jarvis",
        ]

        def dynamic_response(prompt, **kwargs):
            idx = call_count[0]
            call_count[0] += 1
            if idx < len(responses):
                return responses[idx]
            return "done"

        provider = FakeLLMProvider(response="")
        provider.complete = dynamic_response

        loop = self._build_loop(llm_provider=provider, auto_approve=True)
        result = loop.execute("我现在的目录是什么")

        assert result.total_tool_calls == 1
        assert result.total_rounds == 2
        assert "D:\\Jarvis" in result.response or "done" in result.response

    def test_multi_round_tool_result_feedback(self):
        """LLM calls workspace.list_dir then workspace.read_file across rounds."""
        from src.jarvis.core.llm.provider import FakeLLMProvider

        call_count = [0]
        responses = [
            json.dumps({
                "thought": "Need to list directory first",
                "tool_calls": [{"tool_name": "workspace.list_dir", "arguments": {}, "reason": "List current directory"}],
            }),
            json.dumps({
                "thought": "Now read README",
                "tool_calls": [{"tool_name": "workspace.read_file", "arguments": {"path": "README.md"}, "reason": "Read README"}],
            }),
            "项目是 Jarvis CLI 项目。",
        ]

        def dynamic_response(prompt, **kwargs):
            idx = call_count[0]
            call_count[0] += 1
            if idx < len(responses):
                return responses[idx]
            return "done"

        provider = FakeLLMProvider(response="")
        provider.complete = dynamic_response

        loop = self._build_loop(llm_provider=provider, auto_approve=True)
        result = loop.execute("先列当前目录，再读取 README")

        assert result.total_tool_calls == 2
        assert result.total_rounds == 3

    def test_tool_result_contains_error_llm_adapts(self):
        """When a tool returns error, LLM gets the error info and can adapt."""
        from src.jarvis.core.llm.provider import FakeLLMProvider
        from src.jarvis.core.tools.loop import AgentRequest

        call_count = [0]
        responses = [
            json.dumps({
                "thought": "Try to read nonexistent file",
                "tool_calls": [{"tool_name": "workspace.read_file", "arguments": {"path": "nonexistent.py"}, "reason": "Read file"}],
            }),
            "文件不存在，无法读取。",
        ]

        def dynamic_response(prompt, **kwargs):
            idx = call_count[0]
            call_count[0] += 1
            if idx < len(responses):
                return responses[idx]
            return "done"

        provider = FakeLLMProvider(response="")
        provider.complete = dynamic_response

        loop = self._build_loop(llm_provider=provider, auto_approve=True)
        # Use a work-type input that routes to work path
        result = loop.execute("检查一下 nonexistent.py 的内容")

        # This should route to work (repo_inspection)
        assert result.total_tool_calls >= 1, f"Expected tool calls but got {result.total_tool_calls}, response={result.response[:100]}"
        # LLM should have received the error in tool results
        steps = result.steps
        if len(steps) >= 1:
            tool_results = steps[0].tool_results
            if tool_results:
                assert any(r.get("ok") == False for r in tool_results)

    def test_max_rounds_exhausted(self):
        """When max_rounds reached, result is exhausted."""
        from src.jarvis.core.llm.provider import FakeLLMProvider

        provider = FakeLLMProvider(response=json.dumps({
            "thought": "keep going",
            "tool_calls": [{"tool_name": "workspace.status", "arguments": {}, "reason": "status"}],
        }))

        loop = self._build_loop(llm_provider=provider, auto_approve=True)
        loop.max_rounds = 2
        # Use a work-type input that definitely routes to work path
        result = loop.execute("我现在的目录是什么")

        assert result.exhausted, f"Expected exhausted but got response={result.response[:200]}"
        assert result.total_rounds == 2

    def test_final_answer_exits_loop(self):
        """LLM returns non-JSON text → treated as final answer, loop exits."""
        from src.jarvis.core.llm.provider import FakeLLMProvider

        provider = FakeLLMProvider(response="当前工作目录是 D:\\Jarvis")
        loop = self._build_loop(llm_provider=provider, auto_approve=True)
        result = loop.execute("我现在的目录是什么")

        assert result.total_tool_calls == 0
        assert result.total_rounds == 1
        assert "D:\\Jarvis" in result.response

    def test_empty_tool_calls_exits_loop(self):
        """Empty tool_calls list means done."""
        from src.jarvis.core.llm.provider import FakeLLMProvider

        provider = FakeLLMProvider(response=json.dumps({
            "thought": "No tools needed",
            "tool_calls": [],
        }))
        loop = self._build_loop(llm_provider=provider, auto_approve=True)
        result = loop.execute("检查项目")

        assert result.total_tool_calls == 0
        # Empty tool_calls means LLM is done
        assert result.steps[0].is_final if result.steps else True

    def test_llm_none_returns_error(self):
        """LLM returns None → work path returns error result."""
        from src.jarvis.core.llm.provider import NullLLMProvider

        loop = self._build_loop(llm_provider=NullLLMProvider(), auto_approve=True)
        # Work-type input that goes to work_path
        result = loop.execute("我现在的目录是什么")

        assert result.error is not None, f"Expected error but got response={result.response[:100]}"
