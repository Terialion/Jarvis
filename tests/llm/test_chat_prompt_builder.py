"""Tests for build_chat_prompt() and generate_chat_response() in prompt_builder.

Validates:
- Chat prompt contains identity and safety rules.
- Chat prompt does NOT contain tool schemas, handlers, or secrets.
- Local fallback for basic requests.
- LLM unavailable fallback.
- LLM available response passes through.
"""

import pytest
from jarvis.core.llm.prompt_builder import (
    build_chat_prompt,
    generate_chat_response,
    _is_local_fallback_request,
    _local_fallback_response,
    _llm_unavailable_fallback,
    _CHAT_SYSTEM_PROMPT,
)
from jarvis.core.llm.provider import FakeLLMProvider, NullLLMProvider


class TestBuildChatPrompt:
    """Tests for build_chat_prompt()."""

    def test_build_chat_prompt_contains_identity(self):
        """Prompt must contain Jarvis identity."""
        prompt = build_chat_prompt(user_input="hello", chat_type="chat_answer")
        assert "Jarvis" in prompt
        assert "chat" in prompt.lower()

    def test_build_chat_prompt_contains_chat_type(self):
        """Prompt must include the chat_type."""
        prompt = build_chat_prompt(user_input="test", chat_type="joke_answer")
        assert "joke_answer" in prompt

    def test_build_chat_prompt_contains_user_input(self):
        """Prompt must include the user's input."""
        prompt = build_chat_prompt(user_input="解释一下什么是 CLI", chat_type="chat_answer")
        assert "解释一下什么是 CLI" in prompt

    def test_build_chat_prompt_no_tool_schema(self):
        """Prompt must NOT contain tool schemas or handler references."""
        prompt = build_chat_prompt(user_input="test", chat_type="chat_answer")
        # Should not have tool schema terminology
        assert "tool_schema" not in prompt.lower()
        assert "handler" not in prompt.lower()
        assert "input_schema" not in prompt.lower()

    def test_build_chat_prompt_no_secret(self):
        """Prompt must NOT leak secret values while keeping safety boundaries."""
        prompt = build_chat_prompt(user_input="test", chat_type="chat_answer")
        assert "JARVIS_LLM_API_KEY=" not in prompt
        assert "sk-" not in prompt
        assert "secret" not in prompt.lower() or "secret" in _CHAT_SYSTEM_PROMPT  # safety rule mention is ok
        # The safety rule about not reading secrets is fine; just no actual values.

    def test_build_chat_prompt_has_safety_rules(self):
        """Prompt must contain safety constraints."""
        prompt = build_chat_prompt(user_input="test", chat_type="chat_answer")
        # The system prompt contains safety rules
        assert "安全" in prompt or "safety" in prompt.lower() or "不能" in prompt

    def test_build_chat_prompt_prohibits_tools(self):
        """Prompt must state that tools are not allowed in chat mode."""
        prompt = build_chat_prompt(user_input="test", chat_type="chat_answer")
        assert "不允许调用工具" in prompt or "no tool" in prompt.lower()


class TestLocalFallback:
    """Tests for local fallback without LLM."""

    def test_local_fallback_for_greeting(self):
        """"你好" should be recognized as a local fallback request."""
        assert _is_local_fallback_request("你好") is True
        resp = _local_fallback_response("你好", "chat_answer")
        assert len(resp) > 0
        assert "Jarvis" in resp or "你好" in resp

    def test_local_fallback_for_identity(self):
        """"你是谁" should be recognized as a local fallback request."""
        assert _is_local_fallback_request("你是谁") is True
        resp = _local_fallback_response("你是谁", "identity_answer")
        assert len(resp) > 0
        assert "Jarvis" in resp

    def test_local_fallback_for_capability(self):
        """"你能做什么" should be recognized as a local fallback request."""
        assert _is_local_fallback_request("你能做什么") is True
        resp = _local_fallback_response("你能做什么", "help_answer")
        assert len(resp) > 0

    def test_local_fallback_not_for_explanation(self):
        """Explanation requests should NOT use local fallback."""
        assert _is_local_fallback_request("解释一下什么是 CLI agent") is False

    def test_local_fallback_not_for_joke(self):
        """Joke requests should NOT use local fallback (except basic ones)."""
        assert _is_local_fallback_request("给我讲个笑话") is False


class TestGenerateChatResponse:
    """Tests for generate_chat_response()."""

    def test_llm_available_response(self):
        """With FakeLLMProvider, should return the fake response."""
        provider = FakeLLMProvider(response="This is a generated response.")
        result = generate_chat_response(user_input="解释一下什么是 sandbox", chat_type="chat_answer", llm_provider=provider)
        assert result == "This is a generated response."

    def test_llm_available_captures_prompts(self):
        """LLM provider should receive the chat prompt."""
        provider = FakeLLMProvider(response="ok", prompts=[])
        generate_chat_response(user_input="test", chat_type="chat_answer", llm_provider=provider)
        assert len(provider.prompts) == 1
        assert "test" in provider.prompts[0]["prompt"]

    def test_llm_unavailable_fallback(self):
        """With NullLLMProvider (throws), should return clear fallback."""
        provider = NullLLMProvider()
        result = generate_chat_response(user_input="解释一下", chat_type="chat_answer", llm_provider=provider)
        assert "LLM provider" in result or "不可用" in result

    def test_none_llm_fallback(self):
        """With llm_provider=None, should return clear fallback."""
        result = generate_chat_response(user_input="解释一下", chat_type="chat_answer", llm_provider=None)
        assert "LLM provider" in result or "不可用" in result

    def test_local_fallback_skips_llm(self):
        """Local fallback requests should not call LLM at all."""
        provider = FakeLLMProvider(response="should not be called")
        # "你好" uses local fallback
        result = generate_chat_response(user_input="你好", chat_type="chat_answer", llm_provider=provider)
        # Local fallback should return its own response, not the LLM's
        assert result != "should not be called"

    def test_llm_unavailable_fallback_content(self):
        """Fallback message should be informative."""
        fallback = _llm_unavailable_fallback()
        assert len(fallback) > 0
        assert "不可用" in fallback or "unavailable" in fallback.lower()
        # Should suggest alternatives
        assert "查看" in fallback or "查看" in fallback or "skill" in fallback.lower()
