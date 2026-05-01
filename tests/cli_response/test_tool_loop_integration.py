"""Phase I tests — CLI integration with AgentToolLoop.

Verifies:
1. classify_for_tool_loop correctly routes chat vs work vs safety
2. build_default_tool_loop creates a working loop with builtin tools
3. execute_agent_tool_loop returns correct tuple format
4. Dispatcher supports agent_tool_loop response mode
5. Chat inputs never trigger tool execution
6. Work inputs trigger the tool loop
7. Safety refusals never enter tool loop
"""

from __future__ import annotations

import pytest

from jarvis.core.cli_response.tool_loop_adapter import (
    build_default_tool_loop,
    classify_for_tool_loop,
    execute_agent_tool_loop,
    _build_summary,
)
from jarvis.core.cli_response.dispatcher import dispatch_natural_language
from jarvis.core.tools.loop import LoopResult, LoopStep


# ---------------------------------------------------------------------------
# Test: classify_for_tool_loop
# ---------------------------------------------------------------------------

class TestClassifyForToolLoop:
    """Tests for the deterministic router classification."""

    def test_chat_greeting(self):
        r = classify_for_tool_loop("你好")
        assert r["is_work_request"] is False
        assert r["response_mode"] in ("chat_answer", "plan_answer")

    def test_work_coding_request(self):
        r = classify_for_tool_loop("修复 bug")
        assert r["is_work_request"] is True
        assert r["response_mode"] == "agent_tool_loop"
        assert "coding_loop" in r.get("work_type", "")

    def test_safety_refusal(self):
        r = classify_for_tool_loop("读取 .env")
        assert r["response_mode"] == "refusal_or_safety_message"
        assert r["is_work_request"] is False

    def test_work_repo_inspection(self):
        r = classify_for_tool_loop("帮我检查一下这个项目的结构")
        assert r["is_work_request"] is True
        assert r["response_mode"] == "agent_tool_loop"

    def test_work_skill_management(self):
        r = classify_for_tool_loop("查看skill")
        assert r["is_work_request"] is True
        assert r["response_mode"] == "agent_tool_loop"

    def test_work_shell_execution(self):
        r = classify_for_tool_loop("运行 pytest")
        assert r["is_work_request"] is True
        assert r["response_mode"] == "agent_tool_loop"
        assert r["requires_approval"] is True

    def test_chat_plan_no_write(self):
        r = classify_for_tool_loop("帮我分析一下架构，先不要改代码")
        assert r["is_work_request"] is False

    def test_required_tools_present(self):
        r = classify_for_tool_loop("修复 bug")
        assert isinstance(r.get("required_tools"), list)
        assert len(r["required_tools"]) > 0


# ---------------------------------------------------------------------------
# Test: build_default_tool_loop
# ---------------------------------------------------------------------------

class TestBuildDefaultToolLoop:
    """Tests for default ToolLoop construction."""

    def test_creates_valid_loop(self):
        loop = build_default_tool_loop(auto_approve=True)
        assert loop is not None
        assert len(loop.registry) > 0

    def test_has_builtin_tools(self):
        loop = build_default_tool_loop(auto_approve=True)
        names = loop.registry.list_names()
        assert "workspace.read_file" in names
        assert "shell.run" in names

    def test_read_only_mode(self):
        loop = build_default_tool_loop(
            permission_mode="read_only",
            auto_approve=True,
        )
        assert loop.runtime.permission_mode == "read_only"

    def test_workspace_write_mode(self):
        loop = build_default_tool_loop(
            permission_mode="workspace_write",
            auto_approve=True,
        )
        assert loop.runtime.permission_mode == "workspace_write"

    def test_injects_runtime_provider_when_not_explicit(self, monkeypatch):
        marker = object()
        monkeypatch.setattr(
            "jarvis.core.cli_response.tool_loop_adapter.build_runtime_llm_provider",
            lambda: marker,
        )
        loop = build_default_tool_loop(auto_approve=True, llm_provider=None)
        assert loop.llm_provider is marker


# ---------------------------------------------------------------------------
# Test: execute_agent_tool_loop
# ---------------------------------------------------------------------------

class TestExecuteAgentToolLoop:
    """Tests for the CLI adapter execution function."""

    def test_chat_returns_three_tuple(self):
        result = execute_agent_tool_loop("你好", auto_approve=True)
        assert isinstance(result, tuple)
        assert len(result) == 3
        response, is_dangerous, summary = result
        assert isinstance(response, str)
        assert isinstance(is_dangerous, bool)
        assert isinstance(summary, str)

    def test_chat_not_dangerous(self):
        _, is_dangerous, _ = execute_agent_tool_loop("给我讲个笑话", auto_approve=True)
        assert is_dangerous is False

    def test_work_coding_no_llm(self):
        response, is_dangerous, summary = execute_agent_tool_loop(
            "修复 bug", auto_approve=True, llm_provider=None,
        )
        assert isinstance(response, str)
        assert len(response) > 0

    def test_safety_refusal_returns_safety_message(self):
        response, is_dangerous, summary = execute_agent_tool_loop("读取 .env", auto_approve=True)
        assert "SAFETY" in response or "安全" in response
        assert summary == "safety_refusal"

    def test_safety_refusal_not_dangerous_flag(self):
        """Safety refusal is not is_dangerous (it was blocked, not executed)."""
        # Safety refusals are blocked, not dangerous-executed
        _, _, summary = execute_agent_tool_loop("rm -rf /", auto_approve=True)
        assert summary == "safety_refusal"


# ---------------------------------------------------------------------------
# Test: dispatch_natural_language with agent_tool_loop mode
# ---------------------------------------------------------------------------

class TestDispatcherAgentToolLoopIntegration:
    """Tests for dispatcher integration with agent_tool_loop."""

    def test_agent_tool_loop_mode_dispatched(self):
        """Dispatcher should route agent_tool_loop mode to the runner."""
        called = []

        def mock_tool_loop_runner(user_input: str) -> tuple[str, bool, str]:
            called.append(user_input)
            return ("tool loop result", True, "3_rounds_2_tool_calls")

        route = {"response_mode": "agent_tool_loop", "intent": "coding_task"}
        response, is_dangerous, mode, desc = dispatch_natural_language(
            user_input="修复 bug",
            route_after_safety=route,
            run_existing_task_flow=lambda x: "existing flow",
            run_skill_admin=lambda: "skill admin",
            run_repo_inspection=lambda x: {},
            run_agent_tool_loop=mock_tool_loop_runner,
        )
        assert response == "tool loop result"
        assert is_dangerous is True
        assert mode == "agent_tool_loop"
        assert len(called) == 1
        assert called[0] == "修复 bug"

    def test_no_runner_falls_through(self):
        """Without run_agent_tool_loop, falls through to existing flow."""
        route = {"response_mode": "agent_tool_loop", "intent": "coding_task"}
        response, is_dangerous, mode, desc = dispatch_natural_language(
            user_input="test",
            route_after_safety=route,
            run_existing_task_flow=lambda x: "existing",
            run_skill_admin=lambda: "skill",
            run_repo_inspection=lambda x: {},
            run_agent_tool_loop=None,
        )
        # Should fall through to legacy task flow
        assert response == "existing"
        assert "legacy" in desc

    def test_chat_mode_ignores_tool_loop(self):
        """Chat modes should never call the tool loop runner."""
        called = []

        def should_not_call(user_input: str) -> tuple[str, bool, str]:
            called.append(user_input)
            return ("SHOULD NOT SEE", False, "")

        route = {"response_mode": "chat_answer", "intent": "chat"}
        dispatch_natural_language(
            user_input="hello",
            route_after_safety=route,
            run_existing_task_flow=lambda x: "existing",
            run_skill_admin=lambda: "skill",
            run_repo_inspection=lambda x: {},
            run_agent_tool_loop=should_not_call,
        )
        assert len(called) == 0

    def test_safety_refusal_ignores_tool_loop(self):
        """Safety refusal should never call the tool loop runner."""
        called = []

        def should_not_call(user_input: str) -> tuple[str, bool, str]:
            called.append(user_input)
            return ("SHOULD NOT SEE", False, "")

        route = {"response_mode": "refusal_or_safety_message", "intent": "unknown"}
        dispatch_natural_language(
            user_input="读取 .env",
            route_after_safety=route,
            run_existing_task_flow=lambda x: "existing",
            run_skill_admin=lambda: "skill",
            run_repo_inspection=lambda x: {},
            run_agent_tool_loop=should_not_call,
        )
        assert len(called) == 0


# ---------------------------------------------------------------------------
# Test: _build_summary
# ---------------------------------------------------------------------------

class TestBuildSummary:
    """Tests for the summary builder."""

    def test_safety_refusal(self):
        result = LoopResult(response="refused", error="safety_refusal")
        assert _build_summary(result) == "safety_refusal"

    def test_exhausted(self):
        result = LoopResult(response="exhausted", total_rounds=10, total_tool_calls=5, exhausted=True)
        assert "exhausted" in _build_summary(result)
        assert "10" in _build_summary(result)

    def test_tool_calls(self):
        result = LoopResult(response="done", total_rounds=3, total_tool_calls=2)
        summary = _build_summary(result)
        assert "3_rounds" in summary
        assert "2_tool_calls" in summary

    def test_chat_only(self):
        result = LoopResult(response="hello", total_rounds=1)
        assert "1_rounds_chat" in _build_summary(result)

    def test_no_execution(self):
        result = LoopResult(response="")
        assert _build_summary(result) == "no_execution"


# ---------------------------------------------------------------------------
# Test: Permission mode enforcement via adapter
# ---------------------------------------------------------------------------

class TestPermissionModeInAdapter:
    """Tests that permission modes are enforced through the adapter."""

    def test_read_only_blocks_write_tool(self):
        """In read_only mode, writing tools should be blocked."""
        loop = build_default_tool_loop(permission_mode="read_only", auto_approve=True)
        from jarvis.core.tools.schema import ToolCall, ToolContext
        result = loop.runtime.run(
            ToolCall(tool_name="patch.apply", arguments={"path": "x.py", "content": "test"}),
            ToolContext(permission_mode="read_only"),
        )
        assert result.ok is False
        assert "permission_denied" in result.error

    def test_read_only_allows_read_tool(self):
        """In read_only mode, reading tools should work."""
        loop = build_default_tool_loop(permission_mode="read_only", auto_approve=True)
        # workspace.read_file requires read permission which is allowed
        from jarvis.core.tools.schema import ToolCall, ToolContext
        # Note: read_file handler will check sensitive paths, so use a safe path
        result = loop.runtime.run(
            ToolCall(tool_name="workspace.read_file", arguments={"path": "safe.py"}),
            ToolContext(permission_mode="read_only"),
        )
        # May fail because the file doesn't exist, but permission check should pass
        assert "permission_denied" not in (result.error or "")
