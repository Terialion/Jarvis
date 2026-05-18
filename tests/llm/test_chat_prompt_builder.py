"""Tests for build_chat_prompt() and generate_chat_response() in prompt_builder.

Validates:
- Chat prompt contains identity and safety rules.
- Chat prompt does NOT contain tool schemas, handlers, or secrets.
- LLM available response passes through.
- LLM unavailable fallback is informative.
"""

import pytest
from jarvis.core.llm.prompt_builder import (
    build_chat_prompt,
    generate_chat_response,
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

    def test_all_input_goes_to_llm(self):
        """All input, including greetings, goes through LLM — no local fallback bypass."""
        provider = FakeLLMProvider(response="LLM said hi back.")
        result = generate_chat_response(user_input="你好", chat_type="chat_answer", llm_provider=provider)
        assert result == "LLM said hi back."

    def test_llm_unavailable_returns_error(self):
        """With NullLLMProvider (throws), should return error message."""
        provider = NullLLMProvider()
        result = generate_chat_response(user_input="解释一下", chat_type="chat_answer", llm_provider=provider)
        assert "LLM call failed" in result or "LLM provider" in result

    def test_none_llm_returns_error(self):
        """With llm_provider=None, should return clear error."""
        result = generate_chat_response(user_input="解释一下", chat_type="chat_answer", llm_provider=None)
        assert "LLM provider" in result
