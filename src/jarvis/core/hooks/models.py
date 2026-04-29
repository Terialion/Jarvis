from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

HookFn = Callable[[dict[str, Any]], dict[str, Any] | None]

HOOK_POINTS = [
    "before_task_start",
    "after_task_complete",
    "before_plan",
    "after_plan",
    "before_tool_call",
    "after_tool_call",
    "on_tool_error",
    "before_file_edit",
    "after_file_edit",
    "before_command",
    "after_command",
    "on_approval_requested",
    "on_approval_resolved",
    "on_recovery_triggered",
    "on_fallback_used",
    "on_rethink_started",
    "on_rethink_completed",
    "on_memory_write",
]


@dataclass
class HookRegistration:
    hook_id: str
    hook_point: str
    callback: HookFn
    metadata: dict[str, Any] = field(default_factory=dict)
