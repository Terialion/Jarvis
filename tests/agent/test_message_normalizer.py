"""Unit tests for message_normalizer."""
from __future__ import annotations

from src.jarvis.agent.message_normalizer import normalize_messages


def test_qwen_consolidates_mid_conversation_system():
    """Qwen: system messages after user must be converted to user role."""
    messages = [
        {"role": "system", "content": "Initial system prompt"},
        {"role": "user", "content": "Hello"},
        {"role": "system", "content": "Mid-conversation instruction"},
        {"role": "user", "content": "Another question"},
    ]
    result = normalize_messages(messages, provider="qwen", model="qwen3.6-chat")

    # Only one system message at the beginning
    system_count = sum(1 for m in result if m["role"] == "system")
    assert system_count == 1

    # Mid-conversation system converted to user, consecutive users merged
    roles = [m["role"] for m in result]
    assert roles == ["system", "user"]

    # First system contains merged content
    assert "Initial system prompt" in result[0]["content"]
    # Mid-conversation instruction now in the merged user message
    assert "Mid-conversation instruction" in result[1]["content"]
    assert "Another question" in result[1]["content"]


def test_qwen_no_mid_system_messages():
    """Qwen: normal messages without mid-system messages pass through."""
    messages = [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "Question"},
    ]
    result = normalize_messages(messages, provider="qwen", model="qwen3.6-chat")
    assert len(result) == 2
    assert result[0]["role"] == "system"
    assert result[1]["role"] == "user"


def test_deepseek_chat_merges_consecutive_user():
    """DeepSeek chat: consecutive same-role messages merged."""
    messages = [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "First question"},
        {"role": "user", "content": "Second question"},
        {"role": "assistant", "content": "Answer"},
    ]
    result = normalize_messages(messages, provider="deepseek", model="deepseek-v4-pro")

    roles = [m["role"] for m in result]
    # Consecutive users merged into one
    assert roles == ["system", "user", "assistant"]
    assert "First question" in result[1]["content"]
    assert "Second question" in result[1]["content"]


def test_deepseek_chat_merges_consecutive_assistant():
    """DeepSeek chat: consecutive assistant messages merged."""
    messages = [
        {"role": "system", "content": "System"},
        {"role": "user", "content": "Question"},
        {"role": "assistant", "content": "Part 1"},
        {"role": "assistant", "content": "Part 2"},
    ]
    result = normalize_messages(messages, provider="deepseek", model="deepseek-v4-pro")
    roles = [m["role"] for m in result]
    assert roles == ["system", "user", "assistant"]


def test_deepseek_reasoner_merges_system_into_first_user():
    """DeepSeek reasoner: system content merged into first user message."""
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello"},
    ]
    result = normalize_messages(messages, provider="deepseek", model="deepseek-reasoner")

    # No system message
    assert result[0]["role"] == "user"
    assert "You are a helpful assistant." in result[0]["content"]
    assert "Hello" in result[0]["content"]


def test_generic_passthrough():
    """Generic/OpenAI providers: no changes needed."""
    messages = [
        {"role": "system", "content": "System"},
        {"role": "user", "content": "Question"},
    ]
    result = normalize_messages(messages, provider="openai", model="gpt-4.1-mini")
    assert result == messages


def test_empty_messages():
    """Empty message list passes through."""
    assert normalize_messages([], provider="qwen", model="qwen3.6-chat") == []


def test_multiple_system_at_beginning_merged():
    """Multiple system messages at the beginning are merged into one."""
    messages = [
        {"role": "system", "content": "Part 1"},
        {"role": "system", "content": "Part 2"},
        {"role": "user", "content": "Question"},
    ]
    result = normalize_messages(messages, provider="qwen", model="qwen3.6-chat")
    assert len(result) == 2
    assert result[0]["role"] == "system"
    assert "Part 1" in result[0]["content"]
    assert "Part 2" in result[0]["content"]
    assert result[1]["role"] == "user"
