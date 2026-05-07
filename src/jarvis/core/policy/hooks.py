from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from ...agent.types import _redact_value

HookAction = Literal["allow", "deny", "require_approval", "warn", "record", "redact", "escalate"]
HookType = Literal["pre_tool_use", "post_tool_use"]


@dataclass(frozen=True)
class HookInput:
    hook_type: HookType
    tool_name: str
    arguments_preview: dict[str, Any] | str
    result_preview: dict[str, Any] | str | None
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _redact_value(asdict(self))


@dataclass(frozen=True)
class HookResult:
    action: HookAction
    message: str
    risk_level: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _redact_value(asdict(self))


@dataclass(frozen=True)
class HookDefinition:
    name: str
    hook_type: HookType
    matcher: dict[str, Any] = field(default_factory=dict)
    action: HookAction = "allow"
    enabled: bool = True
    message: str = ""

    def matches(self, hook_input: HookInput) -> bool:
        if not self.enabled:
            return False
        for key, expected in dict(self.matcher or {}).items():
            actual = hook_input.context.get(key) if key not in {"tool_name", "risk_level"} else (
                hook_input.tool_name if key == "tool_name" else hook_input.context.get("risk_level")
            )
            if isinstance(expected, (list, tuple, set)):
                if actual not in expected:
                    return False
            elif actual != expected:
                return False
        return True


class HookRegistry:
    def __init__(self, hooks: list[HookDefinition] | None = None) -> None:
        self._hooks: list[HookDefinition] = list(hooks or [])

    def register(self, hook: HookDefinition) -> None:
        self._hooks.append(hook)

    def list(self) -> list[HookDefinition]:
        return list(self._hooks)

    def run_pre_tool_use(self, hook_input: HookInput) -> list[tuple[HookDefinition, HookResult]]:
        return self._run("pre_tool_use", hook_input)

    def run_post_tool_use(self, hook_input: HookInput) -> list[tuple[HookDefinition, HookResult]]:
        return self._run("post_tool_use", hook_input)

    def _run(self, hook_type: HookType, hook_input: HookInput) -> list[tuple[HookDefinition, HookResult]]:
        results: list[tuple[HookDefinition, HookResult]] = []
        for hook in self._hooks:
            if hook.hook_type != hook_type or not hook.matches(hook_input):
                continue
            results.append(
                (
                    hook,
                    HookResult(
                        action=hook.action,
                        message=hook.message or f"{hook.name}:{hook.action}",
                        risk_level=str(hook_input.context.get("risk_level") or ""),
                        metadata={"hook_name": hook.name},
                    ),
                )
            )
        return results
