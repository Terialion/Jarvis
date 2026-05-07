"""Tool registry/executor bridge for AgentLoop."""

from __future__ import annotations

from pathlib import Path
from typing import cast
from typing import Any

from ..core.command_runner import CommandRunner
from ..core.failure_analyzer import FailureAnalyzer
from ..core.file_editor import FileEditor
from ..core.policy import (
    ApprovalStore,
    HookInput,
    HookRegistry,
    PermissionPolicy,
    ToolRule,
    default_security_hook_registry,
    get_approval_store,
    redact_args_preview,
)
from ..core.repo_reader import RepoReader
from ..core.test_runner import TestRunner
from ..core.tools.registry import ToolRegistry as CoreToolRegistry
from ..core.tools.schema import ToolCall as CoreToolCall
from ..core.tools.schema import ToolContext as CoreToolContext
from ..core.tools.schema import ToolResult as CoreToolResult
from ..core.tools.schema import ToolSpec as CoreToolSpec
from ..skills.loader import SkillLoader
from ..skills.registry import SkillRegistry
from ..web.cache import WebCache
from ..web.fetch import FixtureFetchTransport, run_web_fetch
from ..web.providers.router import ProviderRouter
from ..web.schema import FetchRequest, SearchQuery
from ..web.search import run_web_search
from ..web.safety import block_reason_for_url
from .types import AgentEvent
from .types import ToolCall, ToolResult, ToolSpec


class ToolRegistryAdapter:
    """Collect and expose tool specs, backed by existing Jarvis core tools."""

    def __init__(self, *, project_root: str, permission_mode: str = "workspace_write") -> None:
        self.project_root = str(Path(project_root).resolve())
        self.permission_mode = permission_mode
        self.allow_live_web = False

        self.repo_reader = RepoReader()
        self.file_editor = FileEditor(project_root=self.project_root)
        self.command_runner = CommandRunner()
        self.test_runner = TestRunner()
        self.failure_analyzer = FailureAnalyzer()
        self.skill_loader = SkillLoader()
        self.skill_registry = SkillRegistry(project_root=self.project_root)
        self.web_router = ProviderRouter(default_provider="fake")
        self.web_cache = WebCache()
        self.web_transport = FixtureFetchTransport()
        self.hook_registry = default_security_hook_registry()

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
        self.core_registry.register(
            CoreToolSpec(
                name="skill.load",
                description="Load the full body of a named SKILL.md document.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                    },
                    "required": ["name"],
                },
                output_schema={"type": "object"},
                risk_level="low",
                requires_approval=False,
                permissions={"repo_read"},
                handler=self._handle_skill_load,
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="skill.run",
                description="Invoke an executable Jarvis skill by name with JSON arguments.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "arguments": {"type": "object"},
                    },
                    "required": ["name"],
                },
                output_schema={"type": "object"},
                risk_level="medium",
                requires_approval=False,
                permissions={"repo_read", "shell"},
                handler=self._handle_skill_run_marker,
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="web.search",
                description="Search the web via providerized search without fetching page bodies.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "provider": {"type": "string"},
                        "engine": {"type": "string"},
                        "top_k": {"type": "integer"},
                        "freshness": {"type": "string"},
                        "site": {"type": "string"},
                        "task_id": {"type": "string"},
                    },
                    "required": ["query"],
                },
                output_schema={"type": "object"},
                risk_level="medium",
                requires_approval=False,
                permissions={"repo_read"},
                handler=self._handle_web_search,
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="web.fetch",
                description="Safely fetch a readable web document via HTTP GET without executing JavaScript.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                        "extract_mode": {"type": "string"},
                        "max_chars": {"type": "integer"},
                        "provenance": {"type": "object"},
                    },
                    "required": ["url"],
                },
                output_schema={"type": "object"},
                risk_level="medium",
                requires_approval=False,
                permissions={"repo_read"},
                handler=self._handle_web_fetch,
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

    def _handle_skill_load(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        _ = context
        name = str(arguments.get("name") or "").strip()
        if not name:
            return CoreToolResult(
                tool_name="skill.load",
                ok=False,
                error="missing_skill_name",
                metadata={"error_code": "missing_skill_name"},
            )
        try:
            spec = self.skill_registry.get_loadable(name)
        except KeyError:
            return CoreToolResult(
                tool_name="skill.load",
                ok=False,
                error=f"skill_not_found:{name}",
                metadata={"error_code": "skill_not_found", "skill_name": name},
            )
        except PermissionError as exc:
            code = str(exc)
            return CoreToolResult(
                tool_name="skill.load",
                ok=False,
                error=code,
                metadata={"error_code": code, "skill_name": name},
            )
        body = self.skill_registry.load_body(name)
        wrapped = (
            f'<skill name="{spec.name}" risk_level="{spec.risk_level}">\n'
            f"{body.strip()}\n"
            "</skill>"
        )
        return CoreToolResult(
            tool_name="skill.load",
            ok=True,
            output=wrapped,
            metadata={
                "result_code": "ok",
                "skill_name": spec.name,
                "risk_level": spec.risk_level,
                "allowed_tools": list(spec.allowed_tools),
                "skill_path": spec.path,
            },
        )

    def _handle_skill_run_marker(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        _ = arguments, context
        return CoreToolResult(
            tool_name="skill.run",
            ok=False,
            error="skill_run_must_be_handled_by_agent_loop",
            metadata={"error_code": "skill_run_agent_loop_boundary"},
        )

    def _handle_web_search(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        _ = context
        query = SearchQuery(
            query=str(arguments.get("query") or "").strip(),
            provider=str(arguments.get("provider") or "auto"),
            engine=str(arguments.get("engine") or ""),
            top_k=int(arguments.get("top_k") or 5),
            freshness=str(arguments.get("freshness") or "") or None,
            site=str(arguments.get("site") or "") or None,
            task_id=str(arguments.get("task_id") or "") or None,
        )
        result = run_web_search(query, router=self.web_router, cache=self.web_cache, allow_live=self.allow_live_web)
        return CoreToolResult(
            tool_name="web.search",
            ok=bool(result.ok),
            output=result.to_dict(),
            error=result.error,
            metadata={
                "result_code": "ok" if result.ok else "web_search_failed",
                "provider": query.provider,
                "query": query.query,
                "result_count": len(result.results),
            },
        )

    def _handle_web_fetch(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        _ = context
        request = FetchRequest(
            url=str(arguments.get("url") or "").strip(),
            extract_mode=str(arguments.get("extract_mode") or "markdown"),
            max_chars=int(arguments.get("max_chars") or 12000),
            provenance=dict(arguments.get("provenance") or {}),
        )
        result = run_web_fetch(request, cache=self.web_cache, transport=self.web_transport)
        return CoreToolResult(
            tool_name="web.fetch",
            ok=bool(result.ok),
            output=result.to_dict(),
            error=result.error,
            metadata={
                "result_code": "ok" if result.ok else "web_fetch_failed",
                "url": request.url,
                "document_count": len(result.documents),
                "blocked": any(bool(run.get("blocked")) for run in result.runs if isinstance(run, dict)),
            },
        )

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
        permission_policy: PermissionPolicy | None = None,
        approval_store: ApprovalStore | None = None,
        hook_registry: HookRegistry | None = None,
    ) -> None:
        self.registry_adapter = registry_adapter
        self.permission_mode = permission_mode
        self.auto_approve = auto_approve
        self.permission_policy = permission_policy or PermissionPolicy.from_permission_mode(permission_mode)
        self.approval_store = approval_store or get_approval_store()
        self.hook_registry = hook_registry or registry_adapter.hook_registry

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
        spec = self.registry_adapter.core_registry.get(call.name)
        if spec is None:
            return ToolResult(call_id=call.id, name=call.name, ok=False, error=f"tool_not_found:{call.name}", metadata={"agent_events": []})

        agent_events: list[dict[str, Any]] = []
        args_preview = redact_args_preview(call.arguments)

        def emit(event_type: str, payload: dict[str, Any]) -> None:
            agent_events.append(
                AgentEvent.new(
                    turn_id=str(ctx.get("turn_id") or ""),
                    event_type=event_type,
                    payload=payload,
                ).to_dict()
            )

        if call.name == "web.fetch":
            initial_reason = block_reason_for_url(str(call.arguments.get("url") or ""))
            if initial_reason is not None:
                emit("web_fetch_blocked", {"tool_name": call.name, "url": call.arguments.get("url"), "block_reason": initial_reason})
                return ToolResult(
                    call_id=call.id,
                    name=call.name,
                    ok=False,
                    error=f"ssrf_blocked:{initial_reason}",
                    metadata={"blocked": True, "block_reason": initial_reason, "agent_events": agent_events, "args_preview": args_preview},
                )

        policy_decision = self.permission_policy.evaluate(call.name, call.arguments)
        emit("permission_policy_evaluated", policy_decision.to_dict())

        if call.name == "web.fetch":
            domain_decision = self.permission_policy.evaluate_domain(
                str(call.arguments.get("url") or ""),
                tool_name=call.name,
                arguments=call.arguments,
            )
            emit("domain_policy_evaluated", domain_decision.to_dict())
            if domain_decision.action == "deny":
                emit("domain_policy_denied", domain_decision.to_dict())
                return ToolResult(
                    call_id=call.id,
                    name=call.name,
                    ok=False,
                    error=f"domain_policy_denied:{domain_decision.reason}",
                    metadata={"agent_events": agent_events, "args_preview": args_preview, "domain": domain_decision.domain},
                )
            if domain_decision.action == "require_approval":
                policy_decision = domain_decision
                emit("domain_approval_required", domain_decision.to_dict())

        approved_request = self.approval_store.find_matching_approved(
            tool_name=call.name,
            arguments_preview=args_preview,
            session_id=str(ctx.get("session_id") or "") or None,
        )
        denied_request = self.approval_store.find_matching_denied(
            tool_name=call.name,
            arguments_preview=args_preview,
            session_id=str(ctx.get("session_id") or "") or None,
        )

        if policy_decision.action == "deny":
            emit("tool_policy_denied", policy_decision.to_dict())
            return ToolResult(
                call_id=call.id,
                name=call.name,
                ok=False,
                error=f"tool_policy_denied:{policy_decision.reason}",
                metadata={"agent_events": agent_events, "args_preview": args_preview},
            )

        if denied_request is not None:
            emit("approval_denied", {"approval_id": denied_request.approval_id, "tool_name": call.name, "retry": True})
            return ToolResult(
                call_id=call.id,
                name=call.name,
                ok=False,
                error=f"approval_denied:{denied_request.approval_id}",
                metadata={"agent_events": agent_events, "args_preview": args_preview},
            )

        if policy_decision.action == "require_approval" and not (self.auto_approve or approved_request is not None):
            pending = self.approval_store.find_matching_pending(
                tool_name=call.name,
                arguments_preview=args_preview,
                session_id=str(ctx.get("session_id") or "") or None,
            )
            request = pending or self.approval_store.create_request(
                tool_name=call.name,
                arguments_preview=args_preview,
                risk_level=policy_decision.risk_level,
                reason=policy_decision.reason,
                session_id=str(ctx.get("session_id") or "") or None,
                turn_id=str(ctx.get("turn_id") or "") or None,
            )
            emit(
                "approval_created",
                {"approval_id": request.approval_id, "tool_name": request.tool_name, "risk_level": request.risk_level, "reason": request.reason},
            )
            emit(
                "approval_required",
                {"approval_id": request.approval_id, "tool_name": request.tool_name, "risk_level": request.risk_level, "reason": request.reason},
            )
            return ToolResult(
                call_id=call.id,
                name=call.name,
                ok=False,
                error=f"approval_required:{request.approval_id}",
                metadata={
                    "approval_required": True,
                    "approval_id": request.approval_id,
                    "agent_events": agent_events,
                    "args_preview": args_preview,
                },
            )

        emit("tool_policy_allowed", policy_decision.to_dict())
        if approved_request is not None:
            emit("approval_approved", {"approval_id": approved_request.approval_id, "tool_name": call.name, "retry": True})

        pre_input = HookInput(
            hook_type="pre_tool_use",
            tool_name=call.name,
            arguments_preview=args_preview,
            result_preview=None,
            context={"risk_level": spec.risk_level, "permission_mode": tool_context.permission_mode},
        )
        pre_results = self.hook_registry.run_pre_tool_use(pre_input)
        for hook, hook_result in pre_results:
            emit("pretool_hook_started", {"hook_name": hook.name, "tool_name": call.name, "action": hook_result.action})
            emit("pretool_hook_completed", {"hook_name": hook.name, "tool_name": call.name, "action": hook_result.action, "message": hook_result.message})
            if hook_result.action in {"warn", "escalate"}:
                emit("security_warning_emitted", {"hook_name": hook.name, "tool_name": call.name, "message": hook_result.message})
            if hook_result.action == "deny":
                emit("pretool_hook_denied", {"hook_name": hook.name, "tool_name": call.name, "message": hook_result.message})
                return ToolResult(
                    call_id=call.id,
                    name=call.name,
                    ok=False,
                    error=f"pretool_hook_denied:{hook_result.message}",
                    metadata={"agent_events": agent_events, "args_preview": args_preview},
                )
            if hook_result.action == "require_approval" and not self.auto_approve:
                request = self.approval_store.create_request(
                    tool_name=call.name,
                    arguments_preview=args_preview,
                    risk_level=str(hook_result.risk_level or spec.risk_level),
                    reason=hook_result.message,
                    session_id=str(ctx.get("session_id") or "") or None,
                    turn_id=str(ctx.get("turn_id") or "") or None,
                )
                emit("approval_created", {"approval_id": request.approval_id, "tool_name": request.tool_name, "risk_level": request.risk_level, "reason": request.reason})
                emit("approval_required", {"approval_id": request.approval_id, "tool_name": request.tool_name, "risk_level": request.risk_level, "reason": request.reason})
                return ToolResult(
                    call_id=call.id,
                    name=call.name,
                    ok=False,
                    error=f"approval_required:{request.approval_id}",
                    metadata={"approval_required": True, "approval_id": request.approval_id, "agent_events": agent_events, "args_preview": args_preview},
                )

        core_call = CoreToolCall(tool_name=call.name, arguments=dict(call.arguments), reason=call.reason)
        try:
            core_result = cast(CoreToolResult, spec.handler(core_call.arguments, tool_context) if spec.handler is not None else CoreToolResult(tool_name=call.name, ok=False, error=f"no_handler:{call.name}"))
        except Exception as exc:
            core_result = CoreToolResult(tool_name=call.name, ok=False, error=f"handler_error:{type(exc).__name__}:{exc}", metadata={})

        if call.name == "web.fetch" and isinstance(core_result.output, dict):
            runs = list(core_result.output.get("runs") or [])
            blocked_run = next((run for run in runs if isinstance(run, dict) and run.get("blocked")), None)
            if blocked_run is not None:
                emit("web_fetch_blocked", {"tool_name": call.name, "url": call.arguments.get("url"), "block_reason": blocked_run.get("block_reason"), "final_url": blocked_run.get("final_url")})
            else:
                emit("web_fetch_completed" if core_result.ok else "web_fetch_failed", {"tool_name": call.name, "url": call.arguments.get("url")})
        elif call.name == "web.search":
            emit("web_search_completed" if core_result.ok else "web_search_failed", {"tool_name": call.name, "query": call.arguments.get("query")})

        post_preview = core_result.output if isinstance(core_result.output, dict) else {"output": core_result.output}
        post_input = HookInput(
            hook_type="post_tool_use",
            tool_name=call.name,
            arguments_preview=args_preview,
            result_preview=post_preview,
            context={
                "risk_level": spec.risk_level,
                "permission_mode": tool_context.permission_mode,
                "contains_secret_text": bool(core_result.output and "REDACTED" in str(core_result.output)),
            },
        )
        post_results = self.hook_registry.run_post_tool_use(post_input)
        for hook, hook_result in post_results:
            emit("posttool_hook_started", {"hook_name": hook.name, "tool_name": call.name, "action": hook_result.action})
            emit("posttool_hook_completed", {"hook_name": hook.name, "tool_name": call.name, "action": hook_result.action, "message": hook_result.message})
            if hook_result.action in {"warn", "escalate"}:
                emit("posttool_hook_warning", {"hook_name": hook.name, "tool_name": call.name, "message": hook_result.message})
                emit("security_warning_emitted", {"hook_name": hook.name, "tool_name": call.name, "message": hook_result.message})
            if hook_result.action == "redact" and isinstance(core_result.output, str):
                core_result.output = str(redact_args_preview({"output": core_result.output}).get("output") or "")

        metadata = dict(core_result.metadata or {})
        if core_result.output is not None and isinstance(core_result.output, dict):
            for key in ("changed_files", "commands_run", "tests_run"):
                if key in core_result.output and key not in metadata:
                    metadata[key] = core_result.output.get(key)
        metadata["agent_events"] = agent_events
        metadata["args_preview"] = args_preview

        return ToolResult(
            call_id=call.id,
            name=call.name,
            ok=core_result.ok,
            content=core_result.output if core_result.output is not None else "",
            error=core_result.error,
            metadata=metadata,
        )
