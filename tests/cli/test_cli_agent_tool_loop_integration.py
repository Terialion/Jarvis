"""Tests for CLI -> AgentToolLoop integration.

Verifies that _handle_natural_language in jarvis/cli.py properly routes
through AgentToolLoop for work requests, and stays in chat path for
non-work requests.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# Dispatcher-level tests (no CLI dependency)
# ---------------------------------------------------------------------------


class TestDispatcherRoutesWorkModesToAgentToolLoop:
    """Test dispatch_natural_language routes work modes through run_agent_tool_loop."""

    def _dispatch(self, *, mode, tool_loop_mock=None, task_flow_mock=None):
        from jarvis.core.cli_response.dispatcher import dispatch_natural_language

        task_flow = task_flow_mock or MagicMock(return_value="task_flow_result")
        kwargs = dict(
            user_input="test input",
            route_after_safety={"response_mode": mode},
            run_existing_task_flow=task_flow,
            run_skill_admin=MagicMock(return_value="skills"),
            run_repo_inspection=MagicMock(return_value={}),
            run_coding_loop=MagicMock(return_value={}),
        )
        if tool_loop_mock is not None:
            kwargs["run_agent_tool_loop"] = tool_loop_mock
        return dispatch_natural_language(**kwargs)

    @pytest.mark.parametrize("mode", [
        "agent_tool_loop",
        "file_listing",
        "workspace_status",
        "skill_management",
        "repo_inspection",
        "executor_action",
        "coding_loop",
        "url_summary",
        "search_pipeline",
    ])
    def test_work_modes_call_tool_loop(self, mode):
        """All work modes should call run_agent_tool_loop when provided."""
        mock_loop = MagicMock(return_value=("loop_response", False, "1_rounds"))
        result = self._dispatch(mode=mode, tool_loop_mock=mock_loop)
        mock_loop.assert_called_once_with("test input")
        assert result[0] == "loop_response"
        assert result[2] == mode
        assert "agent_tool_loop" in result[3]

    @pytest.mark.parametrize("mode", [
        "agent_tool_loop",
        "file_listing",
        "coding_loop",
        "executor_action",
    ])
    def test_no_task_flow_when_tool_loop_available(self, mode):
        """Legacy task flow should NOT be called when agent_tool_loop is available."""
        task_flow_mock = MagicMock(return_value="task_result")
        mock_loop = MagicMock(return_value=("loop_response", False, "done"))
        self._dispatch(mode=mode, tool_loop_mock=mock_loop, task_flow_mock=task_flow_mock)
        task_flow_mock.assert_not_called()

    def test_chat_modes_do_not_call_tool_loop(self):
        """Chat modes should not call run_agent_tool_loop."""
        mock_loop = MagicMock(return_value=("loop_response", False, "done"))
        result = self._dispatch(mode="chat_answer", tool_loop_mock=mock_loop)
        mock_loop.assert_not_called()
        assert result[2] == "chat_answer"

    def test_joke_mode_does_not_call_tool_loop(self):
        """Joke mode should not call run_agent_tool_loop."""
        mock_loop = MagicMock(return_value=("loop_response", False, "done"))
        result = self._dispatch(mode="joke_answer", tool_loop_mock=mock_loop)
        mock_loop.assert_not_called()
        assert result[2] == "joke_answer"

    def test_plan_mode_does_not_call_tool_loop(self):
        """Plan mode should not call run_agent_tool_loop."""
        mock_loop = MagicMock(return_value=("loop_response", False, "done"))
        result = self._dispatch(mode="plan_answer", tool_loop_mock=mock_loop)
        mock_loop.assert_not_called()
        assert result[2] == "plan_answer"

    def test_safety_refusal_does_not_call_tool_loop(self):
        """Safety refusal should not enter tool loop."""
        mock_loop = MagicMock(return_value=("loop_response", False, "done"))
        result = self._dispatch(mode="refusal_or_safety_message", tool_loop_mock=mock_loop)
        mock_loop.assert_not_called()
        assert result[2] == "refusal_or_safety_message"

    @pytest.mark.parametrize("mode", [
        "file_listing",
        "workspace_status",
        "repo_inspection",
        "coding_loop",
        "executor_action",
        "url_summary",
        "search_pipeline",
    ])
    def test_legacy_fallback_without_tool_loop(self, mode):
        """Without run_agent_tool_loop, work modes should fall back to existing task flow."""
        task_flow_mock = MagicMock(return_value="task_result")
        # Do NOT pass run_agent_tool_loop
        result = self._dispatch(mode=mode, tool_loop_mock=None, task_flow_mock=task_flow_mock)
        task_flow_mock.assert_called_once_with("test input")
        assert result[0] == "task_result"

    def test_safety_refusal_without_tool_loop(self):
        """Safety refusal should return refusal even without tool loop."""
        result = self._dispatch(mode="refusal_or_safety_message", tool_loop_mock=None)
        assert result[2] == "refusal_or_safety_message"


# ---------------------------------------------------------------------------
# CLI-level tests (mock _handle_natural_language internals)
# ---------------------------------------------------------------------------


class TestHandleNaturalLanguageRoutesToAgentToolLoop:
    """Test _handle_natural_language in jarvis/cli.py routes through AgentToolLoop."""

    @pytest.fixture()
    def state(self):
        from jarvis.cli import ShellState
        s = ShellState(api_base="http://127.0.0.1:8765")
        s.mode = "edit"
        return s

    def _call_hnl(self, state, user_input, response_mode="file_listing"):
        """Call _handle_natural_language with mocks for trace and build."""
        from jarvis.cli import _handle_natural_language
        with patch("jarvis.cli._detect_intent_route") as mock_detect, \
             patch("jarvis.cli._apply_route_safety") as mock_safety, \
             patch("jarvis.cli._is_library_project_request", return_value=False), \
             patch("jarvis.cli._append_intent_route_trace"), \
             patch("src.jarvis.core.cli_response.tool_loop_adapter.build_default_tool_loop") as mock_build, \
             patch("src.jarvis.core.cli_response.tool_loop_adapter.execute_agent_tool_loop") as mock_exec:
            mock_loop = MagicMock()
            mock_build.return_value = mock_loop
            mock_exec.return_value = ("tool_loop_result", False, "1_rounds_chat")

            # _detect_intent_route returns route dict
            route = {"response_mode": response_mode, "confidence": 0.9}
            mock_detect.return_value = route
            mock_safety.return_value = route

            result = _handle_natural_language(state, user_input)
            return result, mock_exec

    def test_workspace_dir_calls_tool_loop(self, state):
        """'我现在的目录是什么' should trigger AgentToolLoop."""
        result, mock_exec = self._call_hnl(state, "我现在的目录是什么")
        mock_exec.assert_called()

    def test_chat_joke_no_tool_call(self, state):
        """'给我讲个笑话' should NOT call execute_agent_tool_loop (chat path)."""
        result, mock_exec = self._call_hnl(state, "给我讲个笑话", response_mode="joke_answer")
        mock_exec.assert_not_called()

    def test_dir_listing_calls_tool_loop(self, state):
        """'列一下当前目录' should trigger AgentToolLoop."""
        result, mock_exec = self._call_hnl(state, "列一下当前目录")
        mock_exec.assert_called()

    def test_safety_env_no_tool_loop(self, state):
        """'读取 .env' should return safety refusal, not execute tools."""
        result, mock_exec = self._call_hnl(
            state, "读取 .env", response_mode="refusal_or_safety_message"
        )
        mock_exec.assert_not_called()

    def test_shell_pytest_calls_tool_loop(self, state):
        """'运行 pytest' should trigger AgentToolLoop."""
        result, mock_exec = self._call_hnl(state, "运行 pytest")
        mock_exec.assert_called()

    def test_skill_list_calls_tool_loop(self, state):
        """'查看skill' should trigger AgentToolLoop."""
        result, mock_exec = self._call_hnl(state, "查看skill")
        mock_exec.assert_called()

    def test_multi_step_calls_tool_loop(self, state):
        """'先列当前目录，再读取 README' should trigger AgentToolLoop."""
        result, mock_exec = self._call_hnl(state, "先列当前目录，再读取 README")
        mock_exec.assert_called()

    def test_tool_loop_reused_across_calls(self, state):
        """AgentToolLoop should be built once and reused."""
        from jarvis.cli import _handle_natural_language
        with patch("jarvis.cli._detect_intent_route") as mock_detect, \
             patch("jarvis.cli._apply_route_safety") as mock_safety, \
             patch("jarvis.cli._is_library_project_request", return_value=False), \
             patch("jarvis.cli._append_intent_route_trace"), \
             patch("src.jarvis.core.cli_response.tool_loop_adapter.build_default_tool_loop") as mock_build, \
             patch("src.jarvis.core.cli_response.tool_loop_adapter.execute_agent_tool_loop") as mock_exec:
            mock_loop = MagicMock()
            mock_build.return_value = mock_loop
            mock_exec.return_value = ("tool_loop_result", False, "done")
            route = {"response_mode": "file_listing", "confidence": 0.9}
            mock_detect.return_value = route
            mock_safety.return_value = route

            _handle_natural_language(state, "列一下当前目录")
            _handle_natural_language(state, "查看skill")

            # build_default_tool_loop should only be called once (cached on state)
            mock_build.assert_called_once()


# ---------------------------------------------------------------------------
# Contract tests: CLI -> AgentToolLoop interface
# ---------------------------------------------------------------------------


class TestCLIToAgentToolLoopContract:
    """Verify the contract between CLI and AgentToolLoop."""

    def test_execute_agent_tool_loop_returns_tuple(self):
        """execute_agent_tool_loop must return (str, bool, str)."""
        from jarvis.core.cli_response.tool_loop_adapter import (
            build_default_tool_loop,
            execute_agent_tool_loop,
        )

        loop = build_default_tool_loop(auto_approve=False)
        result = execute_agent_tool_loop(
            "你好",
            tool_loop=loop,
        )
        assert isinstance(result, tuple)
        assert len(result) == 3
        assert isinstance(result[0], str)  # response_text
        assert isinstance(result[1], bool)  # is_dangerous
        assert isinstance(result[2], str)  # summary

    def test_chat_path_zero_tool_calls(self):
        """Chat path should produce 0 tool calls."""
        from jarvis.core.cli_response.tool_loop_adapter import (
            build_default_tool_loop,
        )
        from jarvis.core.tools.schema import ToolContext

        loop = build_default_tool_loop(auto_approve=False)
        loop_result = loop.execute("你好", ToolContext(permission_mode="read_only"))
        assert loop_result.total_tool_calls == 0

    def test_work_path_forces_tool_runtime(self):
        """Work path for '列一下当前目录' must go through AgentToolLoop."""
        from jarvis.core.cli_response.tool_loop_adapter import (
            build_default_tool_loop,
        )
        from jarvis.core.tools.schema import ToolContext

        loop = build_default_tool_loop(auto_approve=False)
        loop_result = loop.execute("列一下当前目录", ToolContext(permission_mode="read_only"))
        # It's a work request — no safety refusal
        assert "SAFETY" not in loop_result.response or loop_result.error != "safety_refusal"

    def test_safety_refusal_stops_before_llm(self):
        """Safety refusal must stop before LLM is consulted."""
        from jarvis.core.cli_response.tool_loop_adapter import (
            build_default_tool_loop,
        )
        from jarvis.core.tools.schema import ToolContext

        loop = build_default_tool_loop(auto_approve=False)
        result = loop.execute("读取 .env", ToolContext(permission_mode="read_only"))
        assert result.error == "safety_refusal"
        assert result.total_tool_calls == 0

    def test_shell_run_needs_approval(self):
        """shell.run must require approval."""
        from jarvis.core.cli_response.tool_loop_adapter import (
            build_default_tool_loop,
        )
        from jarvis.core.tools.schema import ToolContext, ToolCall

        loop = build_default_tool_loop(auto_approve=False)
        call = ToolCall(tool_name="shell.run", arguments={"command": "pytest"})
        tr = loop.runtime.run(call, ToolContext(permission_mode="workspace_write"))
        assert tr.requires_approval is True
        assert tr.ok is False

    def test_workspace_status_no_approval(self):
        """workspace.status should not require approval."""
        from jarvis.core.cli_response.tool_loop_adapter import (
            build_default_tool_loop,
        )
        from jarvis.core.tools.schema import ToolContext, ToolCall

        loop = build_default_tool_loop(auto_approve=False)
        call = ToolCall(tool_name="workspace.status", arguments={})
        tr = loop.runtime.run(call, ToolContext(permission_mode="read_only"))
        assert tr.ok is True
        assert tr.requires_approval is False

    def test_patch_apply_needs_approval(self):
        """patch.apply must require approval."""
        from jarvis.core.cli_response.tool_loop_adapter import (
            build_default_tool_loop,
        )
        from jarvis.core.tools.schema import ToolContext, ToolCall

        loop = build_default_tool_loop(auto_approve=False)
        call = ToolCall(tool_name="patch.apply", arguments={"file_path": "/tmp/test.py", "content": "x=1"})
        tr = loop.runtime.run(call, ToolContext(permission_mode="workspace_write"))
        assert tr.requires_approval is True
        assert tr.ok is False

    def test_env_read_blocked_by_handler(self):
        """Reading .env must be blocked at the handler level."""
        from jarvis.core.cli_response.tool_loop_adapter import (
            build_default_tool_loop,
        )
        from jarvis.core.tools.schema import ToolContext, ToolCall

        loop = build_default_tool_loop(auto_approve=True)
        call = ToolCall(tool_name="workspace.read_file", arguments={"path": ".env"})
        tr = loop.runtime.run(call, ToolContext(permission_mode="workspace_write"))
        assert tr.ok is False
        assert "safety" in (tr.error or "").lower() or "sensitive" in (tr.error or "").lower()

    def test_unknown_tool_rejected(self):
        """Unknown tool should be rejected by ToolRuntime."""
        from jarvis.core.cli_response.tool_loop_adapter import (
            build_default_tool_loop,
        )
        from jarvis.core.tools.schema import ToolContext, ToolCall

        loop = build_default_tool_loop(auto_approve=False)
        call = ToolCall(tool_name="nonexistent.tool", arguments={})
        tr = loop.runtime.run(call, ToolContext(permission_mode="read_only"))
        assert tr.ok is False
        assert "not_found" in (tr.error or "").lower() or "not registered" in (tr.error or "").lower()
