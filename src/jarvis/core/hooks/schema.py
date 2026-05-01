"""Hook schema definitions for the core hook system.

Hooks are execution boundaries (pre/post tool use), not semantic routing layers.
Hooks cannot:
- Expand permissions
- Cancel safety refusal
- Let shell.run / patch.apply bypass approval
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Literal


class HookStage(str, Enum):
    USER_PROMPT_SUBMIT = "user_prompt_submit"
    PRE_TOOL_USE = "pre_tool_use"
    POST_TOOL_USE = "post_tool_use"
    STOP = "stop"


@dataclass(frozen=True)
class HookResult:
    allowed: bool = True
    reason: str | None = None
    message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class HookSpec:
    """Specification for a registered hook.

    Stages:
    - pre_tool_use: Runs before tool execution. If allowed=False, blocks execution.
    - post_tool_use: Runs after tool execution. Audit only; errors do not affect ToolResult.
    - stop: Lifecycle hook, no tool context.

    Matcher: dict matching tool_name, risk_level, permission, etc.
    """
    name: str
    stage: Literal["pre_tool_use", "post_tool_use", "stop"]
    matcher: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    risk_level: str = "low"
    handler: Callable[..., HookResult] | None = None

    def matches(self, *, tool_name: str = "", risk_level: str = "", permission: str = "") -> bool:
        """Check if this hook matches the given tool context."""
        if not self.matcher:
            return True
        if "tool_name" in self.matcher and self.matcher["tool_name"] != tool_name:
            return False
        if "risk_level" in self.matcher and self.matcher["risk_level"] != risk_level:
            return False
        if "permission" in self.matcher and self.matcher["permission"] != permission:
            return False
        return True
