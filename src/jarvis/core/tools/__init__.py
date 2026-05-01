"""Core tools module — ToolRegistry, ToolSpec, ToolCall, ToolResult, ToolRuntime, AgentToolLoop."""

from .schema import ToolCall, ToolContext, ToolResult, ToolSpec
from .registry import ToolRegistry
from .builtin import BUILTIN_TOOL_SPECS, register_builtin_tools
from .runtime import ApprovalGate, ToolRuntime
from .loop import AgentToolLoop, LoopResult, LoopStep

__all__ = [
    "ToolSpec",
    "ToolCall",
    "ToolResult",
    "ToolContext",
    "ToolRegistry",
    "ApprovalGate",
    "ToolRuntime",
    "AgentToolLoop",
    "LoopResult",
    "LoopStep",
    "BUILTIN_TOOL_SPECS",
    "register_builtin_tools",
]
