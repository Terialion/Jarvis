"""Controlled execution runtime for builtin Jarvis skills."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ..agent.types import AgentEvent, ToolCall, ToolResult, TurnContext, contains_secret_text
from .registry import SkillRegistry
from .runtime import SkillCall, SkillExecutionContext, SkillResult, SkillStep


SECRET_FILE_NAMES = {".env", ".env.local", ".env.production", "id_rsa", "id_dsa"}


class SkillExecutor:
    """Execute vetted builtin skills through ToolCallExecutor.

    The executor owns orchestration only. All file, shell, and test actions
    still pass through ToolCallExecutor and the existing policy/approval chain.
    """

    def __init__(
        self,
        *,
        skill_registry: SkillRegistry,
        tool_executor: Any,
        project_root: str = ".",
    ) -> None:
        self.skill_registry = skill_registry
        self.tool_executor = tool_executor
        self.project_root = str(Path(project_root).resolve())
        self._handlers: dict[str, Callable[[SkillExecutionContext], SkillResult]] = {
            "summarize_file": self._run_summarize_file,
            "repo_overview": self._run_repo_overview,
            "run_tests": self._run_run_tests,
            "fix_test_failure": self._run_fix_test_failure,
        }

    def run(self, skill_call: SkillCall, turn_context: TurnContext) -> SkillResult:
        try:
            spec = self.skill_registry.get_runnable(skill_call.name)
        except KeyError:
            event = self._event(turn_context, "skill_call_failed", {"skill_name": skill_call.name, "error": "skill_not_found"})
            return SkillResult(
                ok=False,
                skill_name=skill_call.name,
                final_answer=f"Skill not found: {skill_call.name}",
                output_type="error",
                events=[event],
                risks=["skill_not_found"],
            )
        except PermissionError as exc:
            code = str(exc)
            event = self._event(turn_context, "skill_call_failed", {"skill_name": skill_call.name, "error": code})
            return SkillResult(
                ok=False,
                skill_name=skill_call.name,
                final_answer=f"Skill `{skill_call.name}` is currently blocked: {code}.",
                output_type="refusal",
                events=[event],
                risks=[code],
            )

        ctx = SkillExecutionContext(
            skill_call=skill_call,
            skill_spec=spec,
            turn_context=turn_context,
            allowed_tools=list(spec.allowed_tools or []),
            policy_context={"permission_mode": turn_context.permission_mode},
        )
        ctx.events.append(self._event(turn_context, "skill_call_started", {"skill_name": spec.name, "skill_call_id": skill_call.id, "source": skill_call.source}))
        handler = self._handlers.get(spec.name)
        if handler is None:
            ctx.events.append(self._event(turn_context, "skill_call_failed", {"skill_name": spec.name, "error": "skill_not_executable"}))
            return SkillResult(
                ok=False,
                skill_name=spec.name,
                final_answer=f"Skill `{spec.name}` is loadable but not executable yet.",
                output_type="partial",
                events=list(ctx.events),
                risks=["skill_not_executable"],
            )
        result = handler(ctx)
        result.events.append(self._event(turn_context, "skill_call_completed" if result.ok else "skill_call_failed", {"skill_name": spec.name, "ok": result.ok}))
        return result

    def _run_summarize_file(self, ctx: SkillExecutionContext) -> SkillResult:
        raw_path = str(ctx.skill_call.arguments.get("path") or self._guess_file_path(ctx.turn_context.user_input) or "").strip()
        if not raw_path:
            return self._simple_result(ctx, ok=False, final_answer="Which file should I summarize?", output_type="clarification", risks=["missing_file_path"])
        if self._is_secret_path(raw_path):
            return self._simple_result(
                ctx,
                ok=False,
                final_answer="I cannot summarize secret-bearing files such as .env or private keys.",
                output_type="refusal",
                risks=["secret_file_refused"],
            )
        step, result, call_dict = self._execute_tool(ctx, "read_file", "Read target file", "repo_reader.read_file", {"path": self._resolve_workspace_path(raw_path)})
        observations = [self._observation_from_tool("summarize_file", result, related_files=[raw_path])]
        final = self._summarize_file_result(raw_path, result)
        return SkillResult(
            ok=result.ok,
            skill_name=ctx.skill_spec.name,
            final_answer=final,
            output_type="tool_result" if result.ok else "partial",
            steps=[step],
            observations=observations,
            tool_calls=[call_dict],
            tool_results=[result.to_dict()],
            events=list(ctx.events),
            risks=[] if result.ok else [str(result.error or "read_failed")],
            related_files=[raw_path],
        )

    def _run_repo_overview(self, ctx: SkillExecutionContext) -> SkillResult:
        steps: list[SkillStep] = []
        tool_results: list[ToolResult] = []
        observations: list[dict[str, Any]] = []
        search_step, search_result, search_call = self._execute_tool(ctx, "search_structure", "Search top-level project files", "repo_reader.search_files", {"repo_path": ctx.turn_context.cwd, "pattern": "README", "max_results": 20})
        steps.append(search_step)
        tool_results.append(search_result)
        read_step, read_result, read_call = self._execute_tool(ctx, "read_readme", "Read README if present", "repo_reader.read_file", {"path": self._resolve_workspace_path("README.md")})
        steps.append(read_step)
        tool_results.append(read_result)
        related = ["README.md"] if read_result.ok else []
        observations.append(self._observation_from_tool("repo_overview", read_result if read_result.ok else search_result, related_files=related))
        final = self._repo_overview_answer(search_result, read_result)
        ok = any(result.ok for result in tool_results)
        return SkillResult(
            ok=ok,
            skill_name=ctx.skill_spec.name,
            final_answer=final,
            output_type="tool_result" if ok else "partial",
            steps=steps,
            observations=observations,
            tool_calls=[search_call, read_call],
            tool_results=[result.to_dict() for result in tool_results],
            events=list(ctx.events),
            risks=[] if ok else ["repo_overview_incomplete"],
            related_files=related,
        )

    def _run_run_tests(self, ctx: SkillExecutionContext) -> SkillResult:
        command = str(ctx.skill_call.arguments.get("command") or self._default_test_command(ctx.turn_context.user_input))
        step, result, call_dict = self._execute_tool(ctx, "run_tests", "Run scoped test command", "test_runner.run_test", {"command": command, "cwd": ctx.turn_context.cwd, "timeout_s": 120})
        passed = bool(isinstance(result.content, dict) and result.content.get("passed"))
        final = self._test_result_answer(command, result, passed=passed)
        return SkillResult(
            ok=result.ok,
            skill_name=ctx.skill_spec.name,
            final_answer=final,
            output_type="tool_result" if passed else "partial",
            steps=[step],
            observations=[self._observation_from_tool("run_tests", result)],
            tool_calls=[call_dict],
            tool_results=[result.to_dict()],
            events=list(ctx.events),
            risks=[] if passed else ["tests_failed_or_unavailable"],
        )

    def _run_fix_test_failure(self, ctx: SkillExecutionContext) -> SkillResult:
        command = str(ctx.skill_call.arguments.get("command") or self._default_test_command(ctx.turn_context.user_input))
        step, result, call_dict = self._execute_tool(ctx, "inspect_failure", "Run or inspect failing tests", "test_runner.run_test", {"command": command, "cwd": ctx.turn_context.cwd, "timeout_s": 120})
        final = (
            "Dry-run repair plan:\n"
            f"- Reproduce or inspect with `{command}`.\n"
            "- Identify the smallest failing source/test pair from the output.\n"
            "- Read only the relevant files before proposing edits.\n"
            "- Ask for approval before any file modification.\n"
        )
        if result.content:
            final += f"\nObserved test result: {str(result.content)[:700]}"
        return SkillResult(
            ok=True,
            skill_name=ctx.skill_spec.name,
            final_answer=final,
            output_type="partial",
            steps=[step],
            observations=[self._observation_from_tool("fix_test_failure", result)],
            tool_calls=[call_dict],
            tool_results=[result.to_dict()],
            events=list(ctx.events),
            risks=["approval_required_for_edit", "no_auto_edit"],
        )

    def _execute_tool(self, ctx: SkillExecutionContext, step_name: str, description: str, tool_name: str, tool_args: dict[str, Any]) -> tuple[SkillStep, ToolResult, dict[str, Any]]:
        step = SkillStep(name=step_name, description=description, tool_name=tool_name, tool_args=dict(tool_args), status="running")
        ctx.events.append(self._event(ctx.turn_context, "skill_step_started", {"skill_name": ctx.skill_spec.name, "step_name": step_name, "tool_name": tool_name}))
        if not self._tool_allowed(tool_name, ctx.allowed_tools):
            step.status = "skipped"
            denied_call = ToolCall.new(name=tool_name, arguments=dict(tool_args), reason=f"skill:{ctx.skill_spec.name}:{step_name}:denied")
            ctx.events.append(
                self._event(
                    ctx.turn_context,
                    "skill_tool_denied",
                    {"skill_name": ctx.skill_spec.name, "step_name": step_name, "tool_name": tool_name, "risk": "tool_not_allowed_by_skill"},
                )
            )
            return step, ToolResult(call_id=denied_call.id, name=tool_name, ok=False, error="tool_not_allowed_by_skill", metadata={"risk": "tool_not_allowed_by_skill"}), denied_call.to_dict()
        call = ToolCall.new(name=tool_name, arguments=dict(tool_args), reason=f"skill:{ctx.skill_spec.name}:{step_name}")
        ctx.events.append(self._event(ctx.turn_context, "tool_call_started", {"step": step_name, "tool_call": call.to_dict()}))
        result = self.tool_executor.execute(
            call,
            context={
                "cwd": ctx.turn_context.cwd,
                "session_id": ctx.turn_context.session_id or "",
                "turn_id": ctx.turn_context.turn_id or "",
                "permission_mode": ctx.turn_context.permission_mode,
                "mode": "skill_runtime",
                "skill_name": ctx.skill_spec.name,
                "skill_step": step_name,
            },
        )
        for event in list((result.metadata or {}).get("agent_events") or []):
            if isinstance(event, dict):
                ctx.events.append(self._event(ctx.turn_context, str(event.get("type") or "turn_failed"), dict(event.get("payload") or {})))
        step.status = "completed" if result.ok else "failed"
        ctx.events.append(self._event(ctx.turn_context, "tool_call_completed", {"step": step_name, "tool_result": result.to_dict()}))
        ctx.events.append(self._event(ctx.turn_context, "skill_step_completed" if result.ok else "skill_step_failed", {"skill_name": ctx.skill_spec.name, "step_name": step_name, "tool_name": tool_name, "ok": result.ok}))
        ctx.events.append(self._event(ctx.turn_context, "skill_observation_added", {"skill_name": ctx.skill_spec.name, "step_name": step_name, "tool_name": tool_name, "ok": result.ok}))
        return step, result, call.to_dict()

    @staticmethod
    def _tool_allowed(tool_name: str, allowed_tools: list[str]) -> bool:
        allowed = set(allowed_tools or [])
        if tool_name in allowed:
            return True
        # Bash/command capability may be mediated through the test runner; the
        # command still flows through ToolCallExecutor and keeps policy checks.
        if tool_name == "test_runner.run_test" and "command_runner.run" in allowed:
            return True
        return False

    def _simple_result(self, ctx: SkillExecutionContext, *, ok: bool, final_answer: str, output_type: str, risks: list[str]) -> SkillResult:
        return SkillResult(ok=ok, skill_name=ctx.skill_spec.name, final_answer=final_answer, output_type=output_type, events=list(ctx.events), risks=risks)

    def _observation_from_tool(self, skill_name: str, result: ToolResult, *, related_files: list[str] | None = None) -> dict[str, Any]:
        return {
            "skill_name": skill_name,
            "summary": str(result.content if result.ok else result.error)[:600],
            "facts": {"tool_ok": result.ok, "tool_name": result.name},
            "related_files": list(related_files or []),
            "tool_calls": [result.name],
        }

    def _resolve_workspace_path(self, path: str) -> str:
        raw = Path(path)
        if raw.is_absolute():
            return str(raw)
        return str((Path(self.project_root) / raw).resolve())

    @staticmethod
    def _is_secret_path(path: str) -> bool:
        lowered = str(path or "").replace("\\", "/").lower()
        return Path(lowered).name in SECRET_FILE_NAMES or "/.env" in lowered or contains_secret_text(lowered)

    @staticmethod
    def _guess_file_path(text: str) -> str | None:
        for token in str(text or "").replace("`", " ").replace("\"", " ").split():
            if "." in token and not token.startswith("."):
                return token.strip(".,;:()[]{}")
        if "readme" in str(text or "").lower():
            return "README.md"
        return None

    @staticmethod
    def _default_test_command(text: str) -> str:
        lowered = str(text or "").lower()
        if "agent" in lowered:
            return "python -m pytest tests/agent -q"
        return "python -m pytest tests/agent -q"

    @staticmethod
    def _summarize_file_result(path: str, result: ToolResult) -> str:
        if not result.ok:
            return f"Could not read `{path}`: {result.error or 'unknown error'}"
        content = ""
        if isinstance(result.content, dict):
            content = str(result.content.get("content") or "")
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        preview = " ".join(lines[:8])[:900]
        return f"Summary for `{path}`: {preview or '(file is empty)'}"

    @staticmethod
    def _repo_overview_answer(search_result: ToolResult, read_result: ToolResult) -> str:
        parts = ["Project overview:"]
        if read_result.ok and isinstance(read_result.content, dict):
            content = str(read_result.content.get("content") or "")
            first_lines = " ".join(line.strip() for line in content.splitlines()[:8] if line.strip())
            parts.append(f"- README signal: {first_lines[:700] or '(empty README)'}")
        if search_result.ok and isinstance(search_result.content, dict):
            matches = list(search_result.content.get("matches") or [])[:8]
            paths = ", ".join(str(item.get("path") or "") for item in matches if isinstance(item, dict))
            if paths:
                parts.append(f"- Relevant docs/files: {paths}")
        parts.append("- Suggested next step: inspect README.md and tests for the current task path.")
        return "\n".join(parts)

    @staticmethod
    def _test_result_answer(command: str, result: ToolResult, *, passed: bool) -> str:
        if not result.ok:
            return f"Could not run `{command}`: {result.error or 'unknown error'}"
        status = "passed" if passed else "did not pass"
        return f"Test command `{command}` {status}. Result: {str(result.content)[:900]}"

    @staticmethod
    def _event(turn_context: TurnContext, event_type: str, payload: dict[str, Any]) -> AgentEvent:
        return AgentEvent.new(turn_id=str(turn_context.turn_id or ""), event_type=event_type, payload=payload)
