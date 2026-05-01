"""Tests for work-path LLM tool selection in AgentToolLoop.

Verifies that:
- LLM can see tool schemas in the prompt
- LLM output (tool_plan JSON) is parsed and executed by ToolRuntime
- ToolResult feeds back to next round
- Safety/approval gates are enforced
"""

from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest

from src.jarvis.core.tools.registry import ToolRegistry
from src.jarvis.core.tools.builtin import register_builtin_tools
from src.jarvis.core.tools.runtime import ToolRuntime, ApprovalGate
from src.jarvis.core.tools.loop import AgentToolLoop, LoopResult
from src.jarvis.core.tools.schema import ToolContext
from src.jarvis.core.llm.provider import FakeLLMProvider, NullLLMProvider


def _build_loop(
    llm_provider=None,
    permission_mode: str = "workspace_write",
    auto_approve: bool = False,
    max_rounds: int = 5,
) -> AgentToolLoop:
    """Helper to build a standard AgentToolLoop with builtin tools."""
    reg = ToolRegistry()
    register_builtin_tools(reg)
    runtime = ToolRuntime(
        registry=reg,
        permission_mode=permission_mode,
        approval_gate=ApprovalGate(auto_approve=auto_approve),
    )
    return AgentToolLoop(
        registry=reg,
        runtime=runtime,
        llm_provider=llm_provider,
        max_rounds=max_rounds,
    )


def _tool_plan_json(tool_name: str, arguments: dict | None = None, reason: str = "") -> str:
    """Build a valid LLM tool_plan JSON string."""
    plan = {
        "thought": f"Calling {tool_name}",
        "tool_calls": [
            {
                "tool_name": tool_name,
                "arguments": arguments or {},
                "reason": reason or f"Need to call {tool_name}",
            }
        ],
    }
    return json.dumps(plan, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Basic tool selection
# ---------------------------------------------------------------------------

class TestWorkPathLLMToolSelection:
    """Tests for LLM selecting and executing tools through work path."""

    def test_work_path_llm_selects_workspace_status(self):
        """LLM returns workspace.status JSON, ToolRuntime executes it."""
        provider = FakeLLMProvider(response=_tool_plan_json("workspace.status"))
        loop = _build_loop(llm_provider=provider, auto_approve=False)
        result = loop.execute("我现在的目录是什么")

        assert result.total_tool_calls >= 1
        # workspace.status does NOT require approval
        # Find the step that made the tool call
        tool_steps = [s for s in result.steps if s.tool_calls]
        assert len(tool_steps) >= 1
        assert any(
            tc.get("tool_name") == "workspace.status"
            for s in tool_steps
            for tc in s.tool_calls
        )

    def test_work_path_llm_selects_skill_list(self):
        """LLM returns skill.list JSON, ToolRuntime executes it."""
        provider = FakeLLMProvider(response=_tool_plan_json("skill.list"))
        loop = _build_loop(llm_provider=provider, auto_approve=False)
        result = loop.execute("查看skill")

        assert result.total_tool_calls >= 1
        tool_steps = [s for s in result.steps if s.tool_calls]
        assert len(tool_steps) >= 1
        assert any(
            tc.get("tool_name") == "skill.list"
            for s in tool_steps
            for tc in s.tool_calls
        )

    def test_work_path_llm_selects_workspace_list_dir(self):
        """LLM returns workspace.list_dir JSON, ToolRuntime executes it."""
        provider = FakeLLMProvider(response=_tool_plan_json("workspace.list_dir"))
        loop = _build_loop(llm_provider=provider, auto_approve=False)
        result = loop.execute("列一下当前目录")

        assert result.total_tool_calls >= 1
        tool_steps = [s for s in result.steps if s.tool_calls]
        assert len(tool_steps) >= 1
        assert any(
            tc.get("tool_name") == "workspace.list_dir"
            for s in tool_steps
            for tc in s.tool_calls
        )

    def test_tool_result_feedback_to_next_round(self):
        """First round: tool call. Second round: final answer. Multi-round works."""
        call_count = 0
        responses = [
            _tool_plan_json("workspace.status"),
            "当前工作目录是 D:\\Jarvis",
        ]

        def side_effect(*args, **kwargs):
            nonlocal call_count
            idx = min(call_count, len(responses) - 1)
            call_count += 1
            return responses[idx]

        provider = FakeLLMProvider(response="")
        provider.complete = MagicMock(side_effect=side_effect)

        loop = _build_loop(llm_provider=provider, auto_approve=False)
        result = loop.execute("我现在的目录是什么")

        # First round calls tool, second round returns final answer
        assert result.total_tool_calls >= 1
        assert result.total_rounds >= 2
        assert not result.exhausted
        # Final response should be the second LLM output
        assert "当前工作目录" in result.response

    def test_unknown_tool_rejected(self):
        """LLM returns a non-existent tool name, ToolRuntime rejects."""
        provider = FakeLLMProvider(response=_tool_plan_json("nonexistent_tool"))
        loop = _build_loop(llm_provider=provider, auto_approve=False)
        # Use a work-path input that matches _WORK_DIR_PATTERNS
        result = loop.execute("我现在的目录是什么")

        assert result.total_tool_calls >= 1
        # Check that tool result has error about tool_not_found
        tool_results = []
        for s in result.steps:
            tool_results.extend(s.tool_results)
        assert any("tool_not_found" in str(r) for r in tool_results)

    def test_shell_run_approval_required(self):
        """LLM returns shell.run, verify approval_required (not executed)."""
        provider = FakeLLMProvider(
            response=_tool_plan_json("shell.run", {"command": "pytest"}, "Run tests")
        )
        loop = _build_loop(llm_provider=provider, auto_approve=False)
        result = loop.execute("运行 pytest")

        assert result.total_tool_calls >= 1
        # shell.run requires approval — result should show approval_required
        tool_results = []
        for s in result.steps:
            tool_results.extend(s.tool_results)
        assert any(
            r.get("requires_approval", False) or "approval" in str(r.get("error", ""))
            for r in tool_results
        ), f"Expected approval_required in results: {tool_results}"

    def test_patch_apply_approval_required(self):
        """LLM returns patch.apply, verify approval_required (not executed)."""
        provider = FakeLLMProvider(
            response=_tool_plan_json(
                "patch.apply",
                {"file_path": "test.py", "content": "print('hello')"},
                "Apply patch",
            )
        )
        loop = _build_loop(llm_provider=provider, auto_approve=False)
        result = loop.execute("修改 test.py")

        assert result.total_tool_calls >= 1
        tool_results = []
        for s in result.steps:
            tool_results.extend(s.tool_results)
        assert any(
            r.get("requires_approval", False) or "approval" in str(r.get("error", ""))
            for r in tool_results
        ), f"Expected approval_required in results: {tool_results}"

    def test_env_read_safety_refusal(self):
        """'读取 .env' should be refused by safety, not enter LLM work path."""
        provider = FakeLLMProvider(response=_tool_plan_json("workspace.read_file", {"path": ".env"}))
        loop = _build_loop(llm_provider=provider, auto_approve=False)
        result = loop.execute("读取 .env")

        # Should be safety refusal BEFORE entering work path
        assert result.error == "safety_refusal"
        assert result.total_tool_calls == 0
        assert "SAFETY" in result.response

    def test_prompt_contains_tool_context(self):
        """Verify the LLM prompt contains tool context (tool schemas)."""
        captured_prompts = []
        provider = FakeLLMProvider(
            response="Final answer: no tools needed.",
            prompts=captured_prompts,
        )
        loop = _build_loop(llm_provider=provider, auto_approve=False)
        # Use exact work-path matching pattern from _WORK_REPO_PATTERNS
        loop.execute("检查一下这个项目的结构")

        assert len(captured_prompts) >= 1
        prompt = captured_prompts[0]["prompt"]
        # Prompt should contain tool names
        assert "workspace.status" in prompt or "workspace.list_dir" in prompt or "repo.inspect" in prompt

    def test_handler_not_leaked_in_prompt(self):
        """LLM prompt must NOT contain handler function references."""
        captured_prompts = []
        provider = FakeLLMProvider(
            response=_tool_plan_json("workspace.status"),
            prompts=captured_prompts,
        )
        loop = _build_loop(llm_provider=provider, auto_approve=False)
        loop.execute("我现在的目录是什么")

        for p in captured_prompts:
            prompt_text = p.get("prompt", "")
            # Handler functions should NOT appear
            assert "_handler_" not in prompt_text, "Handler function name leaked into LLM prompt"
            assert "<function" not in prompt_text.lower(), "Function reference leaked into LLM prompt"


class TestWorkPathAutoApprove:
    """Tests with auto_approve=True to verify tools execute fully."""

    def test_workspace_status_auto_approved(self):
        """workspace.status should execute and return real result with auto_approve."""
        provider = FakeLLMProvider(response=_tool_plan_json("workspace.status"))
        loop = _build_loop(llm_provider=provider, auto_approve=True)
        result = loop.execute("我现在的目录是什么")

        assert result.total_tool_calls >= 1
        # Find tool result for workspace.status
        tool_results = []
        for s in result.steps:
            tool_results.extend(s.tool_results)
        status_results = [r for r in tool_results if r.get("tool_name") == "workspace.status"]
        assert len(status_results) >= 1
        assert status_results[0].get("ok", False) is True

    def test_list_dir_auto_approved(self):
        """workspace.list_dir should execute and return real result with auto_approve."""
        provider = FakeLLMProvider(response=_tool_plan_json("workspace.list_dir"))
        loop = _build_loop(llm_provider=provider, auto_approve=True)
        result = loop.execute("列一下当前目录")

        assert result.total_tool_calls >= 1
        tool_results = []
        for s in result.steps:
            tool_results.extend(s.tool_results)
        list_results = [r for r in tool_results if r.get("tool_name") == "workspace.list_dir"]
        assert len(list_results) >= 1
        assert list_results[0].get("ok", False) is True


class TestWorkPathNoLLM:
    """Tests for work path when LLM is unavailable."""

    def test_work_path_no_llm_returns_structured(self):
        """Without LLM, work path returns structured acknowledgment, not fake success."""
        loop = _build_loop(llm_provider=None)
        # Use exact work-path matching pattern
        result = loop.execute("检查一下这个项目的结构")

        # Should NOT claim success
        assert "LLM" in result.response or "无法" in result.response or "无法连接" in result.response
        assert result.total_tool_calls == 0

    def test_work_path_null_llm_returns_error(self):
        """NullLLMProvider (raises RuntimeError) should return error or null result."""
        provider = NullLLMProvider()
        loop = _build_loop(llm_provider=provider)
        # Use exact work-path matching pattern
        result = loop.execute("检查一下这个项目的结构")

        # safe_complete catches exceptions and returns None -> llm_returned_none
        assert result.total_tool_calls == 0


class TestWorkPathMaxRounds:
    """Tests for max_rounds enforcement."""

    def test_max_rounds_exhausted(self):
        """If LLM keeps requesting tools, loop stops at max_rounds."""
        provider = FakeLLMProvider(response=_tool_plan_json("workspace.status"))
        loop = _build_loop(llm_provider=provider, auto_approve=True, max_rounds=2)
        # Use exact work-path matching pattern
        result = loop.execute("检查一下这个项目的结构")

        assert result.exhausted is True
        assert "MAX_ROUNDS" in result.response
        assert result.total_rounds == 2
