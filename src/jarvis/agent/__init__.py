"""Jarvis chat-first agent loop package."""

from .types import AgentRunResult, ChatInput, ToolCall, ToolResult

__all__ = [
    "AgentLoop",
    "AgentRunResult",
    "ChatInput",
    "ToolCall",
    "ToolResult",
]


def __getattr__(name: str):
    if name == "AgentLoop":
        from .loop import AgentLoop

        return AgentLoop
    raise AttributeError(name)

