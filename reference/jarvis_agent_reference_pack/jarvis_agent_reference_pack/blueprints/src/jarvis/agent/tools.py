"""Tool bridge for Jarvis AgentLoop.

The executor must prefer existing Jarvis tools/skills instead of reimplementing them.
"""

from __future__ import annotations

import time
from typing import Callable, Any

from .types import ToolCall, ToolResult, ToolSpec


class StaticToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, tuple[ToolSpec, Callable[..., Any]]] = {}

    def register(self, spec: ToolSpec, fn: Callable[..., Any]) -> None:
        self._tools[spec.name] = (spec, fn)

    def list_specs(self) -> list[ToolSpec]:
        return [spec for spec, _ in self._tools.values()]

    def get(self, name: str) -> tuple[ToolSpec, Callable[..., Any]] | None:
        return self._tools.get(name)


class ToolRegistryAdapter:
    """Adapter target for Jarvis ToolRegistry + SkillRegistry."""

    def __init__(self, static: StaticToolRegistry | None = None, jarvis_registry=None, skill_registry=None) -> None:
        self.static = static or StaticToolRegistry()
        self.jarvis_registry = jarvis_registry
        self.skill_registry = skill_registry

    def list_specs(self) -> list[ToolSpec]:
        specs = list(self.static.list_specs())
        # Codex should extend here:
        # - jarvis.tools.registry -> ToolSpec
        # - src.jarvis.core.skill_harness.registry -> ToolSpec
        return specs

    def resolve(self, name: str):
        found = self.static.get(name)
        if found:
            return found
        return None


class ToolExecutor:
    def __init__(self, registry: ToolRegistryAdapter, approval_policy=None, hook_executor=None) -> None:
        self.registry = registry
        self.approval_policy = approval_policy
        self.hook_executor = hook_executor

    def execute(self, call: ToolCall) -> ToolResult:
        started = time.perf_counter()
        resolved = self.registry.resolve(call.name)
        if not resolved:
            return ToolResult(
                call_id=call.call_id,
                name=call.name,
                ok=False,
                error=f"Unknown tool: {call.name}",
                error_type="unknown_tool",
            )
        spec, fn = resolved
        try:
            self._before_tool_call(spec, call)
            data = fn(**call.arguments)
            result = ToolResult(
                call_id=call.call_id,
                name=call.name,
                ok=True,
                content=str(data)[:8000],
                data=data if isinstance(data, dict) else {"value": data},
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
            self._after_tool_call(spec, call, result)
            return result
        except Exception as exc:
            result = ToolResult(
                call_id=call.call_id,
                name=call.name,
                ok=False,
                error=str(exc),
                error_type=type(exc).__name__,
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
            self._after_tool_call(spec, call, result)
            return result

    def _before_tool_call(self, spec: ToolSpec, call: ToolCall) -> None:
        if self.hook_executor:
            self.hook_executor.run("before_tool_call", {"tool": spec.name, "arguments": call.arguments})
        # ApprovalRiskMatrix integration target goes here.

    def _after_tool_call(self, spec: ToolSpec, call: ToolCall, result: ToolResult) -> None:
        if self.hook_executor:
            self.hook_executor.run("after_tool_call", {"tool": spec.name, "result": result})
