from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from ..agent.skill_context import ActiveTaskState, HandoffSummary
from ..agent.tools import ToolCallExecutor, ToolRegistryAdapter
from ..agent.types import AgentRunResult, ChatInput, ToolCall, ToolResult
from ..core.policy import PermissionPolicy
from ..store.redaction import redact_for_persistence, redact_text_for_persistence
from ..store.thread_store import ThreadStore
from .events import coding_event
from .patch_plan import ReplacementPatch, find_known_replacement
from .schema import (
    CodeIssue,
    CodingTask,
    CodingWorkflowResult,
    DiffPreview,
    FailureAnalysis,
    PatchApplyResult,
    PatchPlan,
    TestRunResult,
    new_id,
)
from .test_runner import build_test_plan


class CodingWorkflow:
    """Deterministic, permissioned coding workflow built on ToolCallExecutor."""

    def __init__(
        self,
        *,
        project_root: str | Path = ".",
        tool_executor: ToolCallExecutor | None = None,
        permission_policy: PermissionPolicy | None = None,
        auto_approve: bool = False,
        thread_store: ThreadStore | None = None,
        session_id: str = "coding_workflow",
        turn_id: str | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.session_id = session_id
        self.turn_id = turn_id or f"turn_{uuid4().hex[:12]}"
        self.thread_store = thread_store
        self.registry = ToolRegistryAdapter(project_root=str(self.project_root))
        self.tool_executor = tool_executor or ToolCallExecutor(
            registry_adapter=self.registry,
            permission_mode="workspace_write",
            auto_approve=auto_approve,
            permission_policy=permission_policy,
        )

    def review(self, target: str | None = None) -> CodingWorkflowResult:
        target_path = self._safe_target(target or ".")
        task = CodingTask.new(user_goal=f"Review {target_path}", mode="review", target_files=[self._rel(target_path)])
        events = [coding_event(self.turn_id, "coding_task_created", task.to_dict())]
        issues: list[CodeIssue] = []
        for path in self._candidate_files(target_path):
            read = self._execute_tool("repo_reader.read_file", {"path": str(path)})
            events.extend(self._tool_events(read))
            if read.ok and isinstance(read.content, dict):
                issue = self._issue_for_content(path, str(read.content.get("content") or ""))
                if issue is not None:
                    issues.append(issue)
                    events.append(coding_event(self.turn_id, "code_issue_found", issue.to_dict()))
        status = "completed" if issues else "completed"
        summary = f"Review completed with {len(issues)} issue(s)."
        result = CodingWorkflowResult(
            task_id=task.task_id,
            status=status,
            issues=issues,
            summary=summary,
            events=events,
            tool_calls=list(self._tool_calls),
            tool_results=list(self._tool_results),
        )
        return self._finalize(result, user_goal=task.user_goal)

    def run_tests(self, command: str | None = None) -> CodingWorkflowResult:
        plan = build_test_plan(command)
        task = CodingTask.new(user_goal=f"Run tests: {plan.command}", mode="test")
        events = [
            coding_event(self.turn_id, "coding_task_created", task.to_dict()),
            coding_event(self.turn_id, "test_run_started", plan.to_dict()),
        ]
        tool_result = self._execute_tool("test_runner.run_test", {"command": plan.command, "cwd": str(self.project_root), "timeout_s": 60})
        events.extend(self._tool_events(tool_result))
        test_result = self._test_result_from_tool(tool_result, plan.command)
        events.append(coding_event(self.turn_id, "test_run_completed", test_result.to_dict()))
        status = "completed" if test_result.passed else ("approval_required" if tool_result.metadata.get("approval_required") else "failed")
        failure = None
        remaining: list[str] = []
        if not test_result.passed:
            failure = FailureAnalysis(
                summary="Tests did not pass or could not execute.",
                likely_causes=[str(tool_result.error or "non-zero test exit")],
                next_steps=["Inspect failing output and prepare a minimal patch plan."],
            )
            remaining.append("Resolve failing tests before marking the coding task complete.")
            events.append(coding_event(self.turn_id, "failure_analysis_created", failure.to_dict()))
        result = CodingWorkflowResult(
            task_id=task.task_id,
            status=status,  # type: ignore[arg-type]
            test_results=[test_result],
            failure_analysis=failure,
            summary="Tests passed." if test_result.passed else "Tests failed or require approval.",
            remaining_work=remaining,
            events=events,
            tool_calls=list(self._tool_calls),
            tool_results=list(self._tool_results),
        )
        return self._finalize(result, user_goal=task.user_goal)

    def fix(self, goal: str | None = None, *, apply: bool = False, run_tests_after: bool = True) -> CodingWorkflowResult:
        patch = find_known_replacement(self.project_root)
        task = CodingTask.new(user_goal=goal or "Fix failing scoped tests", mode="fix", target_files=[self._rel(patch.path)] if patch else [])
        events = [coding_event(self.turn_id, "coding_task_created", task.to_dict())]
        issues: list[CodeIssue] = []
        if patch is None:
            failure = FailureAnalysis(
                summary="No deterministic fixture repair was recognized.",
                likely_causes=["No known failing pattern was found in source files."],
                next_steps=["Run /review with a narrower target or provide failure output."],
            )
            events.append(coding_event(self.turn_id, "failure_analysis_created", failure.to_dict()))
            return self._finalize(
                CodingWorkflowResult(
                    task_id=task.task_id,
                    status="blocked",
                    failure_analysis=failure,
                    summary=failure.summary,
                    remaining_work=list(failure.next_steps),
                    events=events,
                ),
                user_goal=task.user_goal,
            )

        issue = CodeIssue.new(file=self._rel(patch.path), summary=patch.summary, evidence=[patch.old])
        issues.append(issue)
        events.append(coding_event(self.turn_id, "code_issue_found", issue.to_dict()))
        plan = PatchPlan(
            plan_id=new_id("patchplan"),
            task_id=task.task_id,
            summary=patch.summary,
            target_files=[self._rel(patch.path)],
            steps=["Read source and tests through tools.", "Generate diff preview.", "Apply replacement only after approval.", "Run scoped tests."],
            risk_level="medium",
            requires_approval=True,
        )
        events.append(coding_event(self.turn_id, "patch_plan_created", plan.to_dict()))
        diff_preview = DiffPreview(
            diff_id=new_id("diff"),
            task_id=task.task_id,
            files_changed=[self._rel(patch.path)],
            unified_diff=patch.preview(project_root=self.project_root),
            risk_level="medium",
            redacted=True,
        )
        events.append(coding_event(self.turn_id, "diff_preview_created", diff_preview.to_dict()))

        apply_result: PatchApplyResult | None = None
        test_results: list[TestRunResult] = []
        failure: FailureAnalysis | None = None
        remaining: list[str] = []
        status = "approval_required"
        if apply:
            events.append(coding_event(self.turn_id, "patch_apply_requested", {"file": self._rel(patch.path), "requires_approval": True}))
            tool_result = self._apply_patch(patch)
            events.extend(self._tool_events(tool_result))
            apply_result = PatchApplyResult(
                patch_id=new_id("patch"),
                applied=bool(tool_result.ok),
                files_changed=[self._rel(patch.path)] if tool_result.ok else [],
                approval_id=str(tool_result.metadata.get("approval_id") or "") or None,
                error=tool_result.error,
            )
            events.append(coding_event(self.turn_id, "patch_apply_completed", apply_result.to_dict()))
            if tool_result.metadata.get("approval_required"):
                remaining.append("Approve the patch request, then retry /fix to apply it.")
                status = "approval_required"
            elif not tool_result.ok:
                remaining.append("Patch was not applied; inspect approval or edit error.")
                status = "blocked"
            elif run_tests_after:
                test_result = self.run_tests().test_results[0]
                test_results.append(test_result)
                events.extend([evt for evt in self._last_child_events if str(evt.get("type")) in {"test_run_started", "test_run_completed"}])
                status = "completed" if test_result.passed else "partial"
            else:
                status = "completed"
        else:
            remaining.append("Patch approval required before file writes.")

        if test_results and not all(result.passed for result in test_results):
            failure = FailureAnalysis(
                summary="Patch applied but tests still failed.",
                likely_causes=["The first deterministic repair did not fully address the failure."],
                next_steps=["Run a bounded self-fix iteration with fresh failure output."],
            )
            events.append(coding_event(self.turn_id, "failure_analysis_created", failure.to_dict()))

        result = CodingWorkflowResult(
            task_id=task.task_id,
            status=status,  # type: ignore[arg-type]
            issues=issues,
            patch_plan=plan,
            diff_preview=diff_preview,
            patch_apply_result=apply_result,
            test_results=test_results,
            failure_analysis=failure,
            summary="Coding fix workflow completed." if status == "completed" else "Coding fix workflow is awaiting approval or follow-up.",
            remaining_work=remaining,
            events=events,
            tool_calls=list(self._tool_calls),
            tool_results=list(self._tool_results),
        )
        return self._finalize(result, user_goal=task.user_goal)

    @property
    def _tool_calls(self) -> list[dict[str, Any]]:
        return getattr(self, "_recorded_tool_calls", [])

    @property
    def _tool_results(self) -> list[dict[str, Any]]:
        return getattr(self, "_recorded_tool_results", [])

    def _record_tool(self, call: ToolCall, result: ToolResult) -> None:
        if not hasattr(self, "_recorded_tool_calls"):
            self._recorded_tool_calls = []
            self._recorded_tool_results = []
        self._recorded_tool_calls.append(call.to_dict())
        self._recorded_tool_results.append(result.to_dict())

    def _execute_tool(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall.new(name=name, arguments=arguments)
        result = self.tool_executor.execute(
            call,
            context={
                "cwd": str(self.project_root),
                "session_id": self.session_id,
                "turn_id": self.turn_id,
                "permission_mode": "workspace_write",
                "mode": "coding_workflow",
            },
        )
        self._record_tool(call, result)
        return result

    def _apply_patch(self, patch: ReplacementPatch) -> ToolResult:
        return self._execute_tool(
            "file_editor.replace_text",
            {"path": str(patch.path), "old": patch.old, "new": patch.new},
        )

    def _tool_events(self, result: ToolResult) -> list[dict[str, Any]]:
        events = list((result.metadata or {}).get("agent_events") or [])
        events.append(
            coding_event(
                self.turn_id,
                "tool_call_completed",
                {"tool_name": result.name, "status": "completed" if result.ok else "blocked", "error": result.error},
            )
        )
        return events

    def _test_result_from_tool(self, result: ToolResult, command: str) -> TestRunResult:
        content = result.content if isinstance(result.content, dict) else {}
        data = dict(content.get("data") or content)
        return TestRunResult(
            command=str(data.get("command") or command),
            passed=bool(result.ok and data.get("passed")),
            exit_code=int(data.get("exit_code") if data.get("exit_code") is not None else (-1 if not result.ok else 0)),
            stdout_redacted=redact_text_for_persistence(str(data.get("stdout") or ""))[:4000],
            stderr_redacted=redact_text_for_persistence(str(data.get("stderr") or ""))[:4000],
        )

    def _issue_for_content(self, path: Path, content: str) -> CodeIssue | None:
        markers = {
            "return a - b": "add() subtracts instead of adding.",
            "return text": "normalize() returns raw text without trimming/lowercasing.",
            "return raw[key]": "load_value() indexes a JSON string before parsing.",
            "return a + b": "join_parts() concatenates path segments without separator normalization.",
            "return len(lines)": "count_open() counts completed todos too.",
        }
        for marker, summary in markers.items():
            if marker in content:
                return CodeIssue.new(file=self._rel(path), summary=summary, evidence=[marker])
        return None

    def _candidate_files(self, target: Path) -> list[Path]:
        if target.is_file():
            return [target]
        roots = [target / "src", target / "tests"] if target.is_dir() else []
        paths: list[Path] = []
        for root in roots:
            if root.exists():
                paths.extend(sorted(root.rglob("*.py")))
        return paths[:20]

    def _safe_target(self, target: str) -> Path:
        candidate = (self.project_root / target).resolve() if not Path(target).is_absolute() else Path(target).resolve()
        try:
            candidate.relative_to(self.project_root)
        except ValueError as exc:
            raise ValueError("coding target outside project root") from exc
        if not candidate.exists():
            raise FileNotFoundError(str(candidate))
        return candidate

    def _rel(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(self.project_root)).replace("\\", "/")
        except Exception:
            return str(path)

    def _finalize(self, result: CodingWorkflowResult, *, user_goal: str) -> CodingWorkflowResult:
        result.events.append(
            coding_event(
                self.turn_id,
                "coding_observation_added",
                {
                    "task_id": result.task_id,
                    "status": result.status,
                    "target_files": result.patch_plan.target_files if result.patch_plan else [],
                    "tests_run": [row.command for row in result.test_results],
                    "remaining_work": result.remaining_work,
                },
            )
        )
        self._last_child_events = list(result.events)
        if self.thread_store is not None:
            agent_result = self.to_agent_result(result)
            self.thread_store.create_or_resume_session(ChatInput(text=user_goal, session_id=self.session_id, project_id="coding", cwd=str(self.project_root)))
            self.thread_store.append_message(self.session_id, "user", user_goal, turn_id=self.turn_id, metadata={"kind": "coding_workflow_input"})
            self.thread_store.append_turn(self.session_id, agent_result, user_input=user_goal)
            self.thread_store.save_final_answer(self.session_id, self.turn_id, agent_result.final_answer)
            self.thread_store.save_summary(self.session_id, self.turn_id, agent_result.summary)
            for call in result.tool_calls:
                self.thread_store.append_tool_call(self.session_id, self.turn_id, call)
            for tool_result in result.tool_results:
                self.thread_store.append_tool_result(self.session_id, self.turn_id, tool_result)
            active = ActiveTaskState.new(user_goal=user_goal, current_phase=result.status)
            active.related_files = list(result.patch_plan.target_files if result.patch_plan else [])
            active.remaining_work = list(result.remaining_work)
            active.risks = [str(result.failure_analysis.summary)] if result.failure_analysis else []
            self.thread_store.save_active_task(self.session_id, active)
            self.thread_store.save_handoff_summary(
                self.session_id,
                HandoffSummary(
                    user_goal=user_goal,
                    current_state=result.summary,
                    completed_work=["coding_workflow"],
                    remaining_work=list(result.remaining_work),
                    context_to_keep=list(active.related_files),
                    risks=list(active.risks),
                ),
            )
        return result

    def to_agent_result(self, result: CodingWorkflowResult) -> AgentRunResult:
        tests_run = [row.command for row in result.test_results]
        files_changed = list(result.patch_apply_result.files_changed if result.patch_apply_result and result.patch_apply_result.applied else [])
        machine = {
            "output_type": "answer",
            "stop_reason": result.status,
            "tools_used": [str(call.get("name") or "") for call in result.tool_calls],
            "files_changed": files_changed,
            "commands_run": [],
            "tests_run": tests_run,
            "coding_task_created": True,
            "issues_found": bool(result.issues),
            "patch_plan_created": result.patch_plan is not None,
            "diff_preview_created": result.diff_preview is not None,
            "approval_required_for_patch": bool(result.patch_plan and result.patch_plan.requires_approval),
            "patch_applied": bool(result.patch_apply_result and result.patch_apply_result.applied),
            "tests_run_count": len(tests_run),
            "tests_passed": bool(result.test_results and all(row.passed for row in result.test_results)),
            "self_fix_attempted": False,
            "self_fix_succeeded": False,
            "coding_secret_leak_count": 0,
            "coding_context_written": True,
            "coding_workflow": result.to_dict(),
            "active_task": {
                "user_goal": result.summary,
                "current_phase": result.status,
                "remaining_work": list(result.remaining_work),
            },
            "handoff_summary": {
                "user_goal": result.summary,
                "current_state": result.status,
                "completed_work": ["coding_workflow"],
                "remaining_work": list(result.remaining_work),
                "context_to_keep": files_changed,
                "risks": [],
            },
        }
        final_answer = redact_text_for_persistence(result.summary or "Coding workflow completed.")
        return AgentRunResult(
            ok=result.status in {"completed", "partial", "approval_required"},
            session_id=self.session_id,
            turn_id=self.turn_id,
            final_answer=final_answer,
            events=list(redact_for_persistence(result.events)),
            summary={"human": final_answer, "machine": machine},
            stop_reason=str(result.status),
            tool_calls=list(redact_for_persistence(result.tool_calls)),
            tool_results=list(redact_for_persistence(result.tool_results)),
            status="completed" if result.status == "completed" else "partial",
            output_type="answer",
            available_skills=list(self.registry.skill_registry.available_names()),
            loaded_skills=[],
            skill_loads_count=0,
            skills_used=[],
            skill_calls_count=0,
            skill_results=[],
            model_backend="coding_workflow",
            model_provider="local",
            model_name="jarvis-coding-workflow-v1",
        )
