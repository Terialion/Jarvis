"""Tests for AgentToolLoop chat path — LLM integration and fallback behavior.

Chat path must:
- Use LLM provider when available.
- Return clear fallback when LLM is unavailable.
- Never call tools.
- Never trigger approval.
- Never read/write files or run shell.
"""

import pytest
from src.jarvis.core.tools.registry import ToolRegistry
from src.jarvis.core.tools.builtin import register_builtin_tools
from src.jarvis.core.tools.runtime import ToolRuntime
from src.jarvis.core.tools.loop import AgentToolLoop
from src.jarvis.core.llm.provider import FakeLLMProvider, NullLLMProvider


def _build_loop(llm_provider=None, max_rounds=3):
    """Build a default AgentToolLoop for testing."""
    reg = ToolRegistry()
    register_builtin_tools(reg)
    runtime = ToolRuntime(registry=reg, permission_mode="read_only")
    return AgentToolLoop(registry=reg, runtime=runtime, llm_provider=llm_provider, max_rounds=max_rounds)


class TestChatPathUsesLLM:
    """Chat path should call LLM when available."""

    def test_chat_path_uses_llm_provider(self):
        """With FakeLLMProvider, response should contain the fake response text."""
        provider = FakeLLMProvider(response="hello from llm")
        loop = _build_loop(llm_provider=provider)
        result = loop.execute("解释一下什么是 CLI agent")
        assert "hello from llm" in result.response

    def test_chat_path_llm_receives_prompt(self):
        """LLM provider should receive a chat prompt (not work prompt)."""
        provider = FakeLLMProvider(response="some answer", prompts=[])
        loop = _build_loop(llm_provider=provider)
        loop.execute("解释一下什么是 sandbox")
        assert len(provider.prompts) >= 1
        # The prompt should mention chat mode, not work tools
        prompt_text = provider.prompts[0]["prompt"]
        assert "chat" in prompt_text.lower() or "聊天" in prompt_text


class TestChatPathNoTools:
    """Chat path must never call tools."""

    def test_chat_path_no_tool_calls(self):
        """LoopResult.total_tool_calls must be 0 for chat."""
        provider = FakeLLMProvider(response="some chat response")
        loop = _build_loop(llm_provider=provider)
        result = loop.execute("给我讲个笑话")
        assert result.total_tool_calls == 0

    def test_chat_path_no_tool_calls_no_llm(self):
        """Even without LLM, chat path must have 0 tool calls."""
        loop = _build_loop(llm_provider=None)
        result = loop.execute("解释一下什么是 CLI agent")
        assert result.total_tool_calls == 0

    def test_chat_path_steps_have_no_tool_calls(self):
        """No step should have tool_calls populated."""
        provider = FakeLLMProvider(response="chat answer")
        loop = _build_loop(llm_provider=provider)
        result = loop.execute("你是谁")
        for step in result.steps:
            assert step.tool_calls == []


class TestChatPathNoApproval:
    """Chat path must never trigger approval."""

    def test_chat_path_no_approval_in_steps(self):
        """No step error should mention approval."""
        provider = FakeLLMProvider(response="plan response")
        loop = _build_loop(llm_provider=provider)
        result = loop.execute("帮我规划一下如何重构，不要直接改代码")
        for step in result.steps:
            if step.error:
                assert "approval" not in step.error.lower()

    def test_chat_path_result_no_approval_error(self):
        """Result error should not be about approval."""
        provider = FakeLLMProvider(response="ok")
        loop = _build_loop(llm_provider=provider)
        result = loop.execute("你觉得我的路由设计合理吗")
        assert result.error is None or "approval" not in (result.error or "").lower()


class TestChatPathLLMUnavailable:
    """Chat path must gracefully handle unavailable LLM."""

    def test_chat_path_llm_unavailable_fallback(self):
        """With NullLLMProvider, should return a clear fallback mentioning unavailability."""
        provider = NullLLMProvider()
        loop = _build_loop(llm_provider=provider)
        result = loop.execute("解释一下 sandbox 和 approval 的区别")
        assert result.response is not None
        assert len(result.response) > 0
        # Should contain some indication of unavailability
        assert "LLM provider" in result.response or "不可用" in result.response

    def test_chat_path_no_llm_fallback(self):
        """With llm_provider=None, should return a clear fallback."""
        loop = _build_loop(llm_provider=None)
        result = loop.execute("帮我写一段 README 介绍，但先不要写文件")
        assert result.response is not None
        assert len(result.response) > 0
        # Should not be empty or crash
        assert "LLM provider" in result.response or "不可用" in result.response

    def test_chat_path_unavailable_still_no_tools(self):
        """Even when LLM is unavailable, no tools should be called."""
        loop = _build_loop(llm_provider=None)
        result = loop.execute("为什么 shell 要审批")
        assert result.total_tool_calls == 0


class TestChatPathSpecificCases:
    """Specific chat request types."""

    def test_chat_path_identity_question(self):
        """"你是谁" returns a helpful response."""
        loop = _build_loop(llm_provider=None)
        result = loop.execute("你是谁")
        assert result.response is not None
        assert len(result.response) > 0
        assert result.total_tool_calls == 0

    def test_chat_path_capability_question(self):
        """"你能做什么" returns a helpful response."""
        loop = _build_loop(llm_provider=None)
        result = loop.execute("你能做什么")
        assert result.response is not None
        assert len(result.response) > 0
        assert result.total_tool_calls == 0

    def test_chat_path_plan_request(self):
        """Planning request (no code changes) goes to chat path."""
        provider = FakeLLMProvider(response="Here is a plan...")
        loop = _build_loop(llm_provider=provider)
        result = loop.execute("帮我规划一下如何重构输入路由，不要直接改代码")
        assert result.total_tool_calls == 0
        assert result.total_rounds >= 1
        # Should get LLM response
        assert "plan" in result.response.lower() or len(result.response) > 10

    def test_chat_path_joke(self):
        """"给我讲个笑话" returns non-empty response."""
        loop = _build_loop(llm_provider=None)
        result = loop.execute("给我讲个笑话")
        assert result.response is not None
        assert len(result.response) > 0
        assert result.total_tool_calls == 0

    def test_chat_path_greeting(self):
        """"你好" returns a greeting."""
        loop = _build_loop(llm_provider=None)
        result = loop.execute("你好")
        assert result.response is not None
        assert len(result.response) > 0
        assert result.total_tool_calls == 0
        # Local fallback should return a proper greeting
        assert "Jarvis" in result.response or "你好" in result.response

    def test_chat_path_explain_concept(self):
        """Explanation request goes to chat path, no tools."""
        provider = FakeLLMProvider(response="CLI agent 是一个...")
        loop = _build_loop(llm_provider=provider)
        result = loop.execute("解释一下什么是 CLI agent")
        assert result.total_tool_calls == 0
        assert "CLI agent" in result.response

    def test_chat_path_sandbox_vs_approval_explain(self):
        """Explaining sandbox vs approval should be chat, no tools."""
        provider = FakeLLMProvider(response="sandbox 和 approval 是两个不同的安全层...")
        loop = _build_loop(llm_provider=provider)
        result = loop.execute("解释一下 sandbox 和 approval 的区别")
        assert result.total_tool_calls == 0
        assert len(result.response) > 5

    def test_chat_path_readme_without_writing(self):
        """Write README but explicitly don't write file = chat path."""
        provider = FakeLLMProvider(response="# Jarvis README\n...")
        loop = _build_loop(llm_provider=provider)
        result = loop.execute("帮我写一段 README 介绍，但先不要写文件")
        assert result.total_tool_calls == 0
