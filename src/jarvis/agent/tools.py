"""Tool registry/executor bridge for AgentLoop."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..core.command_runner import CommandRunner
from ..core.failure_analyzer import FailureAnalyzer
from ..core.file_editor import FileEditor
from ..core.hooks.registry import HookRegistry
from ..core.policy import ApprovalRiskMatrix
from ..core.repo_reader import RepoReader
from ..core.skill_harness.executor import execute_skill
from ..core.skill_harness.loader import SkillLoader
from ..core.skill_harness.matcher import SkillMatcher
from ..core.skill_harness.registry import SkillRegistry
from ..core.test_runner import TestRunner
from ..core.tools.registry import ToolRegistry as CoreToolRegistry
from ..core.tools.runtime import ApprovalGate, ToolRuntime
from ..core.tools.schema import ToolCall as CoreToolCall
from ..core.tools.schema import ToolContext as CoreToolContext
from ..core.tools.schema import ToolResult as CoreToolResult
from ..core.tools.schema import ToolSpec as CoreToolSpec
from .types import ToolCall, ToolResult, ToolSpec


class ToolRegistryAdapter:
    """Collect and expose tool specs, backed by existing Jarvis core tools."""

    def __init__(self, *, project_root: str, permission_mode: str = "workspace_write") -> None:
        self.project_root = str(Path(project_root).resolve())
        self.permission_mode = permission_mode

        self.repo_reader = RepoReader()
        self.file_editor = FileEditor(project_root=self.project_root)
        self.command_runner = CommandRunner()
        self.test_runner = TestRunner()
        self.failure_analyzer = FailureAnalyzer()
        self.skill_registry = SkillRegistry()
        self.skill_loader = SkillLoader()
        self.skill_matcher = SkillMatcher()
        self.risk_matrix = ApprovalRiskMatrix()
        self.hook_registry = HookRegistry()

        self.core_registry = CoreToolRegistry()
        self._register_core_specs()

    def list_tool_specs(self) -> list[ToolSpec]:
        specs: list[ToolSpec] = []
        for spec in self.core_registry.list_all():
            specs.append(
                ToolSpec(
                    name=spec.name,
                    description=spec.description,
                    input_schema=spec.input_schema,
                    risk_level=spec.risk_level,
                    requires_approval=spec.requires_approval,
                    permissions=sorted(spec.permissions),
                )
            )
        return specs

    def _register_core_specs(self) -> None:
        self.core_registry.register(
            CoreToolSpec(
                name="repo_reader.search_files",
                description="Search files by text pattern in repository.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "repo_path": {"type": "string"},
                        "pattern": {"type": "string"},
                        "max_results": {"type": "integer"},
                    },
                    "required": ["pattern"],
                },
                output_schema={"type": "object"},
                risk_level="low",
                requires_approval=False,
                permissions={"repo_read"},
                handler=self._handle_search_files,
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="repo_reader.read_file",
                description="Read repository file content (line-window optional).",
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "start_line": {"type": "integer"},
                        "end_line": {"type": "integer"},
                    },
                    "required": ["path"],
                },
                output_schema={"type": "object"},
                risk_level="low",
                requires_approval=False,
                permissions={"repo_read"},
                handler=self._handle_read_file,
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="file_editor.replace_text",
                description="Replace text in a file (single replacement).",
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "old": {"type": "string"},
                        "new": {"type": "string"},
                    },
                    "required": ["path", "old", "new"],
                },
                output_schema={"type": "object"},
                risk_level="high",
                requires_approval=True,
                permissions={"write"},
                handler=self._handle_replace_text,
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="command_runner.run",
                description="Run a shell command in workspace.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"},
                        "cwd": {"type": "string"},
                        "timeout_s": {"type": "integer"},
                    },
                    "required": ["command"],
                },
                output_schema={"type": "object"},
                risk_level="high",
                requires_approval=True,
                permissions={"shell"},
                handler=self._handle_command_run,
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="test_runner.run_test",
                description="Run scoped tests via TestRunner.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"},
                        "cwd": {"type": "string"},
                        "timeout_s": {"type": "integer"},
                    },
                    "required": [],
                },
                output_schema={"type": "object"},
                risk_level="medium",
                requires_approval=True,
                permissions={"shell"},
                handler=self._handle_test_run,
            )
        )

    def _handle_search_files(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        repo_path = str(arguments.get("repo_path") or context.workspace_root or self.project_root)
        pattern = str(arguments.get("pattern") or "")
        max_results = int(arguments.get("max_results") or 20)
        result = self.repo_reader.search_files(repo_path=repo_path, pattern=pattern, max_results=max_results)
        return self._wrap_core_result("repo_reader.search_files", result)

    def _handle_read_file(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        path = str(arguments.get("path") or "")
        start_line = arguments.get("start_line")
        end_line = arguments.get("end_line")
        result = self.repo_reader.read_file(path=path, start_line=start_line, end_line=end_line)
        return self._wrap_core_result("repo_reader.read_file", result)

    def _handle_replace_text(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        result = self.file_editor.replace_text(
            path=str(arguments.get("path") or ""),
            old=str(arguments.get("old") or ""),
            new=str(arguments.get("new") or ""),
        )
        payload = result.get("data") if result.get("ok") else result.get("error", {})
        wrapped = self._wrap_core_result("file_editor.replace_text", result)
        if wrapped.ok:
            wrapped.metadata["changed_files"] = [str(arguments.get("path") or "")]
        return wrapped

    def _handle_command_run(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        command = str(arguments.get("command") or "")
        cwd = str(arguments.get("cwd") or context.workspace_root or self.project_root)
        timeout_s = int(arguments.get("timeout_s") or 30)
        result = self.command_runner.run(command=command, cwd=cwd, timeout_s=timeout_s)
        wrapped = self._wrap_core_result("command_runner.run", result)
        wrapped.metadata["commands_run"] = [command]
        if "pytest" in command.lower():
            wrapped.metadata["tests_run"] = [command]
        return wrapped

    def _handle_test_run(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        command = arguments.get("command")
        cwd = str(arguments.get("cwd") or context.workspace_root or self.project_root)
        timeout_s = int(arguments.get("timeout_s") or 60)
        result = self.test_runner.run_test(command=command, cwd=cwd, timeout_s=timeout_s)
        wrapped = self._wrap_core_result("test_runner.run_test", result)
        wrapped.metadata["tests_run"] = [str((result.get("data") or {}).get("command") or command or "default")]
        return wrapped

    @staticmethod
    def _wrap_core_result(tool_name: str, raw: dict[str, Any]) -> CoreToolResult:
        if raw.get("ok"):
            return CoreToolResult(
                tool_name=tool_name,
                ok=True,
                output=raw.get("data"),
                metadata={"result_code": "ok"},
            )
        err = raw.get("error") or {}
        return CoreToolResult(
            tool_name=tool_name,
            ok=False,
            error=str(err.get("message") or err.get("code") or "tool_error"),
            metadata={"error_code": err.get("code"), "error_detail": err},
        )


class ToolCallExecutor:
    """Execute agent ToolCall through ToolRuntime safety/permission/approval chain."""

    def __init__(
        self,
        *,
        registry_adapter: ToolRegistryAdapter,
        permission_mode: str = "workspace_write",
        auto_approve: bool = False,
    ) -> None:
        self.registry_adapter = registry_adapter
        self.permission_mode = permission_mode
        self.runtime = ToolRuntime(
            registry=registry_adapter.core_registry,
            permission_mode=permission_mode,
            approval_gate=ApprovalGate(auto_approve=auto_approve),
            hook_registry=registry_adapter.hook_registry,
        )

    def execute(self, call: ToolCall, context: dict[str, Any] | None = None) -> ToolResult:
        ctx = context or {}
        tool_context = CoreToolContext(
            workspace_root=str(ctx.get("cwd") or self.registry_adapter.project_root),
            permission_mode=str(ctx.get("permission_mode") or self.permission_mode),
            mode=str(ctx.get("mode") or "agent"),
            session_id=str(ctx.get("session_id") or ""),
            request_id=str(ctx.get("turn_id") or ""),
            metadata=dict(ctx),
        )

        core_call = CoreToolCall(tool_name=call.name, arguments=dict(call.arguments), reason=call.reason)
        core_result = self.runtime.run(core_call, tool_context)

        metadata = dict(core_result.metadata or {})
        if core_result.output is not None and isinstance(core_result.output, dict):
            # Bubble up common artifacts for summary.
            for key in ("changed_files", "commands_run", "tests_run"):
                if key in core_result.output and key not in metadata:
                    metadata[key] = core_result.output.get(key)

        return ToolResult(
            call_id=call.id,
            name=call.name,
            ok=core_result.ok,
            content=core_result.output if core_result.output is not None else "",
            error=core_result.error,
            metadata=metadata,
        )
