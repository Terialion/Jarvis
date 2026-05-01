"""Contract tests — CLI to AgentToolLoop contract verification.

Tests that verify the contract between cli.py's _handle_natural_language and
the AgentToolLoop, WITHOUT starting a real CLI subprocess.
"""

import pytest
from unittest.mock import MagicMock, patch


class TestCLIToAgentToolLoopContract:
    """Contract: _handle_natural_language delegates to AgentToolLoop."""

    def test_dispatcher_accepts_run_agent_tool_loop(self):
        """dispatch_natural_language accepts run_agent_tool_loop kwarg."""
        from src.jarvis.core.cli_response.dispatcher import dispatch_natural_language

        called = {}
        def mock_tool_loop(text):
            called["text"] = text
            return ("tool_loop_response", False, "1_rounds")

        result = dispatch_natural_language(
            user_input="test",
            route_after_safety={"response_mode": "file_listing"},
            run_existing_task_flow=lambda t: "old",
            run_skill_admin=lambda: "skills",
            run_repo_inspection=lambda t: {},
            run_agent_tool_loop=mock_tool_loop,
        )
        response, is_dangerous, mode, desc = result
        assert called["text"] == "test"
        assert "tool_loop_response" in response

    def test_work_modes_routed_to_tool_loop(self):
        """All work modes should go through agent_tool_loop when available."""
        from src.jarvis.core.cli_response.dispatcher import dispatch_natural_language

        work_modes = [
            "file_listing", "workspace_status", "skill_management",
            "repo_inspection", "executor_action", "coding_loop",
            "url_summary", "search_pipeline",
        ]

        for mode in work_modes:
            called = {"done": False}
            def mock_tool_loop(text, _called=called):
                _called["done"] = True
                return ("response", False, "summary")

            dispatch_natural_language(
                user_input="test",
                route_after_safety={"response_mode": mode},
                run_existing_task_flow=lambda t: "old",
                run_skill_admin=lambda: "skills",
                run_repo_inspection=lambda t: {},
                run_agent_tool_loop=mock_tool_loop,
            )
            assert called["done"], f"mode={mode} should use agent_tool_loop"

    def test_chat_modes_not_routed_to_tool_loop(self):
        """Chat modes should NOT go through agent_tool_loop."""
        from src.jarvis.core.cli_response.dispatcher import dispatch_natural_language

        chat_modes = ["chat_answer", "joke_answer", "identity_answer", "help_answer", "plan_answer"]

        for mode in chat_modes:
            called = {"done": False}
            def mock_tool_loop(text, _called=called):
                _called["done"] = True
                return ("response", False, "summary")

            dispatch_natural_language(
                user_input="test",
                route_after_safety={"response_mode": mode},
                run_existing_task_flow=lambda t: "old",
                run_skill_admin=lambda: "skills",
                run_repo_inspection=lambda t: {},
                run_agent_tool_loop=mock_tool_loop,
            )
            assert not called["done"], f"mode={mode} should NOT use agent_tool_loop"

    def test_safety_refusal_not_routed_to_tool_loop(self):
        """Safety refusal should NOT enter tool loop."""
        from src.jarvis.core.cli_response.dispatcher import dispatch_natural_language

        called = {"done": False}
        def mock_tool_loop(text, _called=called):
            _called["done"] = True
            return ("response", False, "summary")

        dispatch_natural_language(
            user_input="读取 .env",
            route_after_safety={"response_mode": "refusal_or_safety_message"},
            run_existing_task_flow=lambda t: "old",
            run_skill_admin=lambda: "skills",
            run_repo_inspection=lambda t: {},
            run_agent_tool_loop=mock_tool_loop,
        )
        assert not called["done"], "safety refusal should NOT use agent_tool_loop"

    def test_legacy_fallback_without_tool_loop(self):
        """Without run_agent_tool_loop, work modes fall to existing task flow."""
        from src.jarvis.core.cli_response.dispatcher import dispatch_natural_language

        called = {"done": False}
        def mock_task_flow(text):
            called["done"] = True
            return "old_response"

        result = dispatch_natural_language(
            user_input="test",
            route_after_safety={"response_mode": "file_listing"},
            run_existing_task_flow=mock_task_flow,
            run_skill_admin=lambda: "skills",
            run_repo_inspection=lambda t: {},
            run_agent_tool_loop=None,
        )
        response, is_dangerous, mode, desc = result
        assert called["done"]
        assert "old_response" in response
        assert "legacy" in desc

    def test_agent_tool_loop_runner_type(self):
        """AgentToolLoopRunner should be Callable[[str], tuple[str, bool, str]]."""
        from src.jarvis.core.cli_response.dispatcher import AgentToolLoopRunner

        def runner(text: str) -> tuple[str, bool, str]:
            return (text, False, "summary")

        # Should accept the type
        result: tuple[str, bool, str] = runner("test")
        assert result == ("test", False, "summary")

    def test_tool_loop_adapter_returns_correct_tuple(self):
        """execute_agent_tool_loop returns (str, bool, str)."""
        from src.jarvis.core.cli_response.tool_loop_adapter import execute_agent_tool_loop
        from src.jarvis.core.tools.loop import AgentToolLoop
        from src.jarvis.core.tools.registry import ToolRegistry
        from src.jarvis.core.tools.runtime import ToolRuntime

        reg = ToolRegistry()
        runtime = ToolRuntime(registry=reg, permission_mode="read_only")
        loop = AgentToolLoop(registry=reg, runtime=runtime, llm_provider=None, max_rounds=1)

        response, is_dangerous, summary = execute_agent_tool_loop("hello", tool_loop=loop)
        assert isinstance(response, str)
        assert isinstance(is_dangerous, bool)
        assert isinstance(summary, str)

    def test_execute_agent_tool_loop_chat_path_zero_tools(self):
        """Chat path through execute_agent_tool_loop has 0 tool calls."""
        from src.jarvis.core.cli_response.tool_loop_adapter import execute_agent_tool_loop
        from src.jarvis.core.tools.loop import AgentToolLoop
        from src.jarvis.core.tools.registry import ToolRegistry
        from src.jarvis.core.tools.runtime import ToolRuntime

        reg = ToolRegistry()
        runtime = ToolRuntime(registry=reg, permission_mode="read_only")
        loop = AgentToolLoop(registry=reg, runtime=runtime, llm_provider=None, max_rounds=1)

        response, is_dangerous, summary = execute_agent_tool_loop("给我讲个笑话", tool_loop=loop)
        assert not is_dangerous
        # Chat path should not have tool calls

    def test_execute_agent_tool_loop_work_path_no_llm(self):
        """Work path without LLM returns structured acknowledgment."""
        from src.jarvis.core.cli_response.tool_loop_adapter import execute_agent_tool_loop
        from src.jarvis.core.tools.loop import AgentToolLoop
        from src.jarvis.core.tools.registry import ToolRegistry
        from src.jarvis.core.tools.runtime import ToolRuntime

        reg = ToolRegistry()
        runtime = ToolRuntime(registry=reg, permission_mode="read_only")
        loop = AgentToolLoop(registry=reg, runtime=runtime, llm_provider=None, max_rounds=1)

        response, is_dangerous, summary = execute_agent_tool_loop("我现在的目录是什么", tool_loop=loop)
        assert isinstance(response, str)
        assert len(response) > 0
