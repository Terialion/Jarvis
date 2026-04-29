"""Heavy ReAct runtime (first runnable version).

Built by upgrading the react_readiness skeleton into a bounded, auditable runtime.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from ..checkpoint_manager import CheckpointManager
from ..failure_analyzer import FailureAnalyzer
from ..file_editor import FileEditor
from ..repo_reader import RepoReader
from ..result import error_result, ok_result
from ..task_runtime import TaskRuntime
from ..test_runner import TestRunner
from .context_manager import SessionContextManager
from .replay_store import EventType, ReplayStore
from .stop_conditions import StopConditionsManager
from .working_memory import WorkingMemory, WorkingMemoryKey
from ..command_runner import CommandRunner
from ..skill_harness import (
    SkillContextAssembler,
    SkillHitLogger,
    SkillLoader,
    SkillMatcher,
    SkillRegistry,
)
from ..routing import IntentPolicyRouter
from ..policy import ApprovalRiskMatrix
from ..hooks.registry import HookRegistry
from ..hooks.executor import HookExecutor
from ..hooks.models import HookRegistration
from ..eval.harness_metrics_store import HarnessMetricsStore
from ..memory.store import PersistentMemoryStore
from ..memory.retriever import MemoryRetriever
from ..subagents.runner import SubagentRunner
from ..subagents.models import SubagentRun
from ..subagents.policy import validate_subtask_budget
from ..subagents.merge import merge_subagent_result
from ..rethink import build_rethink_context, evaluate_rethink


class RuntimeState(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    RETRYING = "retrying"
    STOPPED = "stopped"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ObservationRecord:
    step_number: int
    payload: dict[str, Any]

    def to_dict(self) -> dict:
        return {"step_number": self.step_number, "payload": self.payload}


@dataclass
class ActionRecord:
    step_number: int
    chosen_skill: str | None
    chosen_tool: str
    action_input: dict[str, Any]
    action_result: dict[str, Any]

    def to_dict(self) -> dict:
        return {
            "step_number": self.step_number,
            "chosen_skill": self.chosen_skill,
            "chosen_tool": self.chosen_tool,
            "action_input": self.action_input,
            "action_result": self.action_result,
        }


@dataclass
class CheckRecord:
    step_number: int
    check_result: dict[str, Any]

    def to_dict(self) -> dict:
        return {"step_number": self.step_number, "check_result": self.check_result}


@dataclass
class RuntimeStopRecord:
    reason: str
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"reason": self.reason, "detail": self.detail}


@dataclass
class StepTrace:
    step_number: int
    observation: ObservationRecord
    chosen_skill: str | None
    chosen_tool: str
    action_input: dict[str, Any]
    action_result: dict[str, Any]
    check_result: dict[str, Any]
    route_summary: dict[str, Any] = field(default_factory=dict)
    strategy: dict[str, Any] = field(default_factory=dict)
    stop_reason: str | None = None

    def to_dict(self) -> dict:
        return {
            "step_number": self.step_number,
            "observation": self.observation.to_dict(),
            "chosen_skill": self.chosen_skill,
            "chosen_tool": self.chosen_tool,
            "action_input": self.action_input,
            "action_result": self.action_result,
            "check_result": self.check_result,
            "route_summary": self.route_summary,
            "strategy": self.strategy,
            "stop_reason": self.stop_reason,
        }


@dataclass
class RunResult:
    run_id: str
    task_id: str
    state: RuntimeState
    traces: list[StepTrace]
    stop_record: RuntimeStopRecord
    retries: int
    fallback: dict[str, Any]
    skill_eval: dict[str, Any]
    route_result: dict[str, Any]
    route_quality_summary: dict[str, Any]
    recovery_effectiveness_summary: dict[str, Any]
    approval_policy_summary: dict[str, Any]
    duration_ms: int

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "state": self.state.value,
            "traces": [t.to_dict() for t in self.traces],
            "stop_record": self.stop_record.to_dict(),
            "retries": self.retries,
            "fallback": self.fallback,
            "skill_eval": self.skill_eval,
            "route_result": self.route_result,
            "route_quality_summary": self.route_quality_summary,
            "recovery_effectiveness_summary": self.recovery_effectiveness_summary,
            "approval_policy_summary": self.approval_policy_summary,
            "duration_ms": self.duration_ms,
        }


@dataclass
class HeavyReActConfig:
    max_steps: int = 8
    timeout_s: int = 120
    max_failures: int = 3
    no_progress_threshold: int = 3
    retry_same_plan_limit: int = 1
    retry_replan_limit: int = 1
    context_budget: int = 12000


class HeavyReActRuntime:
    """Runnable bounded runtime for observe -> plan -> act -> check."""

    def __init__(
        self,
        *,
        project_root: str,
        task_runtime: TaskRuntime,
        repo_reader: RepoReader,
        file_editor: FileEditor,
        command_runner: CommandRunner,
        test_runner: TestRunner,
        failure_analyzer: FailureAnalyzer,
        checkpoint_manager: CheckpointManager | None = None,
        context_manager: SessionContextManager | None = None,
        working_memory: WorkingMemory | None = None,
        replay_store: ReplayStore | None = None,
        stop_manager: StopConditionsManager | None = None,
        skill_registry: SkillRegistry | None = None,
        skill_loader: SkillLoader | None = None,
        skill_matcher: SkillMatcher | None = None,
        skill_context_assembler: SkillContextAssembler | None = None,
        skill_hit_logger: SkillHitLogger | None = None,
        intent_policy_router: IntentPolicyRouter | None = None,
        config: HeavyReActConfig | None = None,
        hook_registry: HookRegistry | None = None,
        metrics_store: HarnessMetricsStore | None = None,
        memory_store: PersistentMemoryStore | None = None,
    ) -> None:
        self.project_root = str(Path(project_root).resolve())
        self.task_runtime = task_runtime
        self.repo_reader = repo_reader
        self.file_editor = file_editor
        self.command_runner = command_runner
        self.test_runner = test_runner
        self.failure_analyzer = failure_analyzer
        self.checkpoint_manager = checkpoint_manager
        self.context_manager = context_manager or SessionContextManager()
        self.working_memory = working_memory or WorkingMemory()
        self.replay_store = replay_store or ReplayStore()
        self.config = config or HeavyReActConfig()
        self.stop_manager = stop_manager or StopConditionsManager(
            max_steps=self.config.max_steps,
            max_failures=self.config.max_failures,
            no_progress_threshold=self.config.no_progress_threshold,
            timeout_seconds=self.config.timeout_s,
            max_context_budget=self.config.context_budget,
        )

        self.skill_registry = skill_registry or SkillRegistry()
        self.skill_loader = skill_loader or SkillLoader(
            available_tools=["repo_reader", "file_editor", "command_runner", "test_runner", "failure_analyzer"]
        )
        self.skill_matcher = skill_matcher or SkillMatcher()
        self.skill_context_assembler = skill_context_assembler or SkillContextAssembler()
        self.skill_hit_logger = skill_hit_logger or SkillHitLogger()
        self.intent_policy_router = intent_policy_router or IntentPolicyRouter()
        self.risk_matrix = ApprovalRiskMatrix(self.intent_policy_router.config_manager)
        self.hook_registry = hook_registry or HookRegistry()
        self.hook_executor = HookExecutor(self.hook_registry, self.risk_matrix)
        self.metrics_store = metrics_store or HarnessMetricsStore()
        self.memory_store = memory_store or PersistentMemoryStore()
        self.memory_retriever = MemoryRetriever(self.memory_store)
        self.subagent_runner = SubagentRunner()
        self._ensure_skills_loaded()

    def run(
        self,
        *,
        task_input: str,
        project_id: str | None = None,
        title: str = "heavy react run",
        task_id: str | None = None,
        plan_template: list[dict] | None = None,
    ) -> dict:
        started = time.perf_counter()
        created = None
        if task_id is None:
            created = self.task_runtime.create_task(project_id=project_id or self.project_root, title=title)
            if not created.get("ok"):
                return created
            task_id = created["data"]["task_id"]
        task = self.task_runtime.tasks.get(task_id)
        if task is None:
            return error_result("TASK_NOT_FOUND", f"Task not found: {task_id}", {"task_id": task_id}, started)

        run_id = f"react_run_{int(time.time() * 1000)}"
        self.task_runtime.set_status(task_id, "running")
        self.task_runtime.add_step(task_id, "react.run.start", {"run_id": run_id, "state": RuntimeState.CREATED.value})
        self.hook_executor.run("before_task_start", {"run_id": run_id, "task_id": task_id, "task_input": task_input})

        self.context_manager.create_context(task_id, {"facts": [f"task_input={task_input}"]})
        recalled_project_cmd = self.memory_retriever.recall(memory_type="project", key="test_command", limit=1)
        if recalled_project_cmd:
            self.working_memory.set_working_memory(task_id, "recalled_test_command", recalled_project_cmd[-1].get("value"))
            self.hook_executor.run("on_memory_write", {"run_id": run_id, "task_id": task_id, "memory_event": "recall", "key": "test_command"})
        self.working_memory.create_store(task_id)
        self.replay_store.create_replay(run_id)
        routed = self.intent_policy_router.route(task_input)
        if routed.get("ok"):
            route_payload = routed["data"]["route_result"]
        else:
            route_payload = {
                "domain": "think",
                "intent": "analysis.plan",
                "confidence": 0.4,
                "reasons": ["route_internal_fallback"],
                "extracted_entities": {},
                "attached_default_skills": [],
                "selected_policies": [],
                "planner_hints": {},
                "approval_risk_hints": {"approval_required": False, "risk_level": "low", "reasons": []},
                "trace_metadata": {"route_error": routed.get("error", {})},
                "fallback_used": True,
            }
        self.working_memory.set_working_memory(task_id, "route_result", route_payload)
        self.working_memory.set_working_memory(
            task_id,
            "context_hints",
            {
                "route_summary": self._route_summary(route_payload),
                "runtime_strategy_hints": route_payload.get("planner_hints") or {},
                "low_confidence_handling": (route_payload.get("trace_metadata") or {}).get("low_confidence_handling"),
                "approval_policy_trace": route_payload.get("approval_risk_hints") or {},
            },
        )
        self.task_runtime.add_step(task_id, "react.route", {"run_id": run_id, "route_summary": self._route_summary(route_payload)})
        self.replay_store.record_event(
            run_id,
            EventType.PLAN,
            -1,
            {"route_summary": self._route_summary(route_payload), "route_result": route_payload},
            "heavy_react.route",
        )

        state = RuntimeState.RUNNING
        step_traces: list[StepTrace] = []
        retries = 0
        repeated_failures = 0
        replan_retries = 0
        same_plan_retries = 0
        last_progress_marker: str | None = None
        no_progress_count = 0
        current_plan = list(plan_template or self._default_plan(task_input))
        stop_record = RuntimeStopRecord(reason="unknown")
        fallback = {"mode": "none", "detail": None}
        recovery_records: list[dict[str, Any]] = []
        approval_records: list[dict[str, Any]] = []
        strategy_records: list[dict[str, Any]] = []
        rethink_records: list[dict[str, Any]] = []

        for step_index in range(self.config.max_steps):
            if (time.perf_counter() - started) >= self.config.timeout_s:
                state = RuntimeState.STOPPED
                stop_record = RuntimeStopRecord(reason="timeout_stop", detail={"timeout_s": self.config.timeout_s})
                break

            observation = self._observe(
                run_id=run_id,
                task_id=task_id,
                step_number=step_index,
                task_input=task_input,
                plan=current_plan,
            )
            matched = self._match_skills(task_input, observation)
            chosen_skill = matched["data"]["matched_skills"][0]["skill_id"] if matched["data"]["matched_skills"] else None
            assembled = self.skill_context_assembler.assemble(
                matched_skills=matched["data"]["matched_skills"],
                registry_snapshot=self.skill_registry.list_skills()["data"]["items"],
                context_budget_chars=1400,
                max_active_skills=3,
            )
            self.working_memory.set_working_memory(task_id, "active_skills", assembled["data"]["active_skill_ids"])

            action = self._plan_action(current_plan=current_plan, step_number=step_index)
            self.hook_executor.run("before_plan", {"run_id": run_id, "task_id": task_id, "step_number": step_index, "action": action})
            if action is None:
                state = RuntimeState.COMPLETED
                stop_record = RuntimeStopRecord(reason="plan_exhausted", detail={"step": step_index})
                break
            strategy = self._decide_strategy(
                route_result=route_payload,
                action=action,
                step_number=step_index,
                repeated_failures=repeated_failures,
                no_progress_count=no_progress_count,
            )
            strategy_records.append(strategy)
            action = self._apply_strategy_to_action(
                run_id=run_id,
                task_id=task_id,
                step_number=step_index,
                action=action,
                strategy=strategy,
                route_payload=route_payload,
            )
            self.hook_executor.run("after_plan", {"run_id": run_id, "task_id": task_id, "step_number": step_index, "action": action, "strategy": strategy})
            self.hook_executor.run("before_tool_call", {"run_id": run_id, "task_id": task_id, "step_number": step_index, "action": action})

            action_result = self._act(run_id=run_id, task_id=task_id, step_number=step_index, action=action)
            self.hook_executor.run(
                "after_tool_call",
                {"run_id": run_id, "task_id": task_id, "step_number": step_index, "action": action, "action_result": action_result},
            )
            if not action_result.get("ok"):
                self.hook_executor.run(
                    "on_tool_error",
                    {
                        "run_id": run_id,
                        "task_id": task_id,
                        "step_number": step_index,
                        "action": action,
                        "error": action_result.get("error"),
                    },
                )
            check = self._check(task_id=task_id, action=action, action_result=action_result, repeated_failures=repeated_failures)
            check = self._apply_route_hints(check=check, action=action, route_result=route_payload)
            check["strategy"] = strategy
            self.working_memory.set_working_memory(
                task_id,
                "runtime_feedback",
                {
                    "last_failure_type": check.get("replan_reason") or check.get("retry_reason") or check.get("fallback_reason"),
                    "prefer_safe_skills": bool(check.get("needs_approval")),
                    "last_outcome": check.get("outcome"),
                },
            )
            if check.get("recovery_record"):
                recovery_records.append(dict(check["recovery_record"]))
                self.hook_executor.run("on_recovery_triggered", {"run_id": run_id, "task_id": task_id, "step_number": step_index, "recovery": check["recovery_record"]})
            if check.get("approval_policy"):
                approval_records.append(dict(check["approval_policy"]))
                self.hook_executor.run("on_approval_requested", {"run_id": run_id, "task_id": task_id, "step_number": step_index, "approval_policy": check["approval_policy"]})
            rethink_record = self._evaluate_rethink(
                run_id=run_id,
                task_id=task_id,
                step_number=step_index,
                route_payload=route_payload,
                action_result=action_result,
                check=check,
                repeated_failures=repeated_failures,
                no_progress_count=no_progress_count,
            )
            if rethink_record:
                rethink_records.append(rethink_record)

            trace = StepTrace(
                step_number=step_index,
                observation=ObservationRecord(step_number=step_index, payload=observation),
                chosen_skill=chosen_skill,
                chosen_tool=action.get("tool", "unknown"),
                action_input=dict(action),
                action_result=action_result,
                check_result=check,
                route_summary=self._route_summary(route_payload),
                strategy=strategy,
                stop_reason=check.get("stop_reason"),
            )
            step_traces.append(trace)

            self.skill_hit_logger.log_hit(
                run_id=run_id,
                task_id=task_id,
                step_number=step_index,
                active_skills=list(assembled["data"]["active_skill_ids"]),
                matched_skill_ids=[item["skill_id"] for item in matched["data"]["matched_skills"]],
                chosen_skill_id=chosen_skill,
                chosen_tool=action.get("tool"),
                action_outcome=check.get("outcome", "unknown"),
                seeded_by_policy=bool(chosen_skill and chosen_skill in set(route_payload.get("attached_default_skills") or [])),
                seed_sources=["policy_seed"] if chosen_skill and chosen_skill in set(route_payload.get("attached_default_skills") or []) else [],
            )

            self._record_trace(run_id=run_id, step_trace=trace)
            self._write_runtime_step(task_id=task_id, step_trace=trace)
            self.metrics_store.append_event(
                {
                    "run_id": run_id,
                    "task_id": task_id,
                    "kind": "strategy",
                    "step_number": step_index,
                    "strategy_mode": strategy.get("mode"),
                    "risk_tier": (check.get("approval_policy") or {}).get("risk_tier"),
                }
            )

            progress_marker = f"{action.get('tool')}::{check.get('outcome')}::{action_result.get('ok')}"
            if progress_marker == last_progress_marker:
                no_progress_count += 1
            else:
                no_progress_count = 0
            last_progress_marker = progress_marker

            if check.get("needs_approval"):
                state = RuntimeState.WAITING_FOR_APPROVAL
                stop_record = RuntimeStopRecord(reason="approval_required_stop", detail={"step": step_index, "action": action})
                self.hook_executor.run(
                    "on_approval_resolved",
                    {"run_id": run_id, "task_id": task_id, "step_number": step_index, "state": "pending", "reason": "approval_required_stop"},
                )
                break

            if check.get("should_stop"):
                state = RuntimeState.COMPLETED if check.get("passed") else RuntimeState.STOPPED
                stop_record = RuntimeStopRecord(reason=check.get("stop_reason") or "stopped", detail={"step": step_index})
                break

            if check.get("retry_same_plan") and same_plan_retries < self.config.retry_same_plan_limit:
                state = RuntimeState.RETRYING
                same_plan_retries += 1
                retries += 1
                continue

            if check.get("retry_with_replan") and replan_retries < self.config.retry_replan_limit:
                state = RuntimeState.RETRYING
                replan_retries += 1
                retries += 1
                current_plan = self._replan_from_failure(current_plan, action_result, check)
                continue

            if not check.get("passed"):
                repeated_failures += 1
                if repeated_failures >= self.config.max_failures:
                    state = RuntimeState.STOPPED
                    stop_record = RuntimeStopRecord(reason="repeated_failure_stop", detail={"failures": repeated_failures})
                    break
            else:
                repeated_failures = 0

            if no_progress_count >= self.config.no_progress_threshold:
                state = RuntimeState.STOPPED
                stop_record = RuntimeStopRecord(reason="no_progress_stop", detail={"count": no_progress_count})
                break

            if current_plan:
                current_plan.pop(0)

        if stop_record.reason == "unknown":
            state = RuntimeState.STOPPED
            stop_record = RuntimeStopRecord(reason="max_steps_stop", detail={"max_steps": self.config.max_steps})

        if state in {RuntimeState.STOPPED, RuntimeState.FAILED}:
            fallback = self._fallback(stop_record)
            self.hook_executor.run("on_fallback_used", {"run_id": run_id, "task_id": task_id, "fallback": fallback, "stop_reason": stop_record.reason})
            if fallback["mode"] == "fallback_to_human_review":
                state = RuntimeState.FAILED

        skill_eval = self.skill_hit_logger.evaluate(run_id)
        eval_data = skill_eval["data"] if skill_eval.get("ok") else {"run_id": run_id, "total_steps": 0}
        aggregate_eval = self.skill_hit_logger.aggregate_effectiveness(task_id=task_id)
        if aggregate_eval.get("ok"):
            eval_data["task_effectiveness"] = aggregate_eval.get("data")
        route_quality = self._route_quality_summary(route_payload=route_payload, traces=step_traces)
        recovery_summary = self._recovery_effectiveness_summary(recovery_records=recovery_records, traces=step_traces)
        approval_summary = self._approval_policy_summary(approval_records=approval_records, route_payload=route_payload)

        duration_ms = max(0, int((time.perf_counter() - started) * 1000))
        run_result = RunResult(
            run_id=run_id,
            task_id=task_id,
            state=state,
            traces=step_traces,
            stop_record=stop_record,
            retries=retries,
            fallback=fallback,
            skill_eval=eval_data,
            route_result=route_payload,
            route_quality_summary=route_quality,
            recovery_effectiveness_summary=recovery_summary,
            approval_policy_summary=approval_summary,
            duration_ms=duration_ms,
        )

        self.replay_store.record_event(run_id, EventType.STOP, len(step_traces), run_result.stop_record.to_dict(), "heavy_react")
        self.replay_store.finalize_replay(run_id, run_result.stop_record.reason)
        self.hook_executor.run("after_task_complete", {"run_id": run_id, "task_id": task_id, "state": state.value, "stop_reason": run_result.stop_record.reason})
        self.metrics_store.append_event(
            {
                "run_id": run_id,
                "task_id": task_id,
                "kind": "route",
                "route_domain": route_payload.get("domain"),
                "route_intent": route_payload.get("intent"),
                "risk_tier": approval_summary.get("route_risk_level"),
            }
        )

        task.setdefault("react_runs", []).append(run_result.to_dict())
        task["latest_react_run_id"] = run_id
        summary = (
            f"heavy_react:{state.value} stop={run_result.stop_record.reason} "
            f"steps={len(step_traces)} retries={retries}"
        )
        self.task_runtime.finalize(task_id, summary)
        self.task_runtime.add_step(
            task_id,
            "react.run.finalize",
            {
                "run_id": run_id,
                "state": state.value,
                "stop_reason": run_result.stop_record.reason,
                "fallback": fallback,
                "skill_eval": eval_data,
                "route_summary": self._route_summary(route_payload),
                "route_quality_summary": route_quality,
                "recovery_effectiveness_summary": recovery_summary,
                "approval_policy_summary": approval_summary,
                "strategy_records": strategy_records,
                "rethink_summary": self._rethink_summary(rethink_records),
            },
        )
        if state == RuntimeState.COMPLETED:
            test_cmd = self._select_test_command(task_id=task_id)
            self.memory_store.write(
                {
                    "memory_type": "project",
                    "key": "test_command",
                    "value": test_cmd,
                    "run_id": run_id,
                    "task_id": task_id,
                    "source": "runtime_success",
                }
            )
            self.hook_executor.run("on_memory_write", {"run_id": run_id, "task_id": task_id, "memory_event": "write", "key": "test_command"})
        else:
            self.memory_store.write(
                {
                    "memory_type": "failure",
                    "key": "last_failure",
                    "value": run_result.stop_record.reason,
                    "run_id": run_id,
                    "task_id": task_id,
                    "source": "runtime_failure",
                }
            )
            self.hook_executor.run("on_memory_write", {"run_id": run_id, "task_id": task_id, "memory_event": "write", "key": "last_failure"})

        return ok_result(
            {
                "task_id": task_id,
                "created_task": created["data"] if created else None,
                "run_result": run_result.to_dict(),
                "replay_export": self.replay_store.export_replay_json(run_id),
                "rethink_summary": self._rethink_summary(rethink_records),
            },
            started,
        )

    def _default_plan(self, task_input: str) -> list[dict]:
        return [
            {
                "tool": "repo_reader.search_symbol",
                "symbol": "return 1" if "return" in task_input.lower() else "def ",
                "max_results": 5,
            },
            {
                "tool": "file_editor.replace_text",
                "old": "return 1",
                "new": "return 2",
            },
            {
                "tool": "test_runner.run_test",
                "command": None,
            },
            {
                "tool": "failure_analyzer.analyze",
            },
        ]

    def _observe(
        self,
        *,
        run_id: str,
        task_id: str,
        step_number: int,
        task_input: str,
        plan: list[dict],
    ) -> dict:
        observation = {
            "task_id": task_id,
            "task_input": task_input,
            "step_number": step_number,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "pending_plan_steps": len(plan),
            "task_status": self.task_runtime.tasks[task_id].get("status"),
            "last_result": self.working_memory.get_working_memory(task_id, WorkingMemoryKey.LAST_RESULT, {}),
        }
        self.context_manager.append_observation(task_id, observation, step_number=step_number)
        self.replay_store.record_event(run_id, EventType.OBSERVATION, step_number, observation, "heavy_react.observe")
        return observation

    def _plan_action(self, *, current_plan: list[dict], step_number: int) -> dict | None:
        if not current_plan:
            return None
        action = dict(current_plan[0])
        action["step_number"] = step_number
        return action

    def _act(self, *, run_id: str, task_id: str, step_number: int, action: dict) -> dict:
        tool = action.get("tool")
        root = self.project_root
        if tool == "repo_reader.search_symbol":
            result = self.repo_reader.search_symbol(root, action.get("symbol") or "def ", action.get("max_results") or 20)
            self.working_memory.set_working_memory(task_id, "last_search", result)
            return result

        if tool == "repo_reader.search_files":
            result = self.repo_reader.search_files(root, action.get("pattern") or ".py", action.get("max_results") or 20)
            self.working_memory.set_working_memory(task_id, "last_search", result)
            return result

        if tool == "file_editor.replace_text":
            self.hook_executor.run("before_file_edit", {"run_id": run_id, "task_id": task_id, "step_number": step_number, "action": action})
            target = self._resolve_target_file(task_id)
            if not target:
                return error_result("REPO_FILE_NOT_FOUND", "No target file for replace", {"task_id": task_id})
            result = self.file_editor.replace_text(target, str(action.get("old") or ""), str(action.get("new") or ""))
            if result.get("ok"):
                diff = self.file_editor.diff(target)
                if diff.get("ok"):
                    self.task_runtime.attach_file_change(task_id, diff["data"])
            self.hook_executor.run("after_file_edit", {"run_id": run_id, "task_id": task_id, "step_number": step_number, "action": action, "result": result})
            return result

        if tool == "file_editor.insert_text":
            self.hook_executor.run("before_file_edit", {"run_id": run_id, "task_id": task_id, "step_number": step_number, "action": action})
            target = self._resolve_target_file(task_id)
            if not target:
                return error_result("REPO_FILE_NOT_FOUND", "No target file for insert", {"task_id": task_id})
            result = self.file_editor.insert_text(
                target,
                str(action.get("anchor") or ""),
                str(action.get("content") or ""),
                str(action.get("position") or "after"),
            )
            self.hook_executor.run("after_file_edit", {"run_id": run_id, "task_id": task_id, "step_number": step_number, "action": action, "result": result})
            return result

        if tool == "command_runner.run":
            self.hook_executor.run("before_command", {"run_id": run_id, "task_id": task_id, "step_number": step_number, "action": action})
            result = self.command_runner.run(
                command=str(action.get("command") or ""),
                cwd=str(action.get("cwd") or self.project_root),
                timeout_s=int(action.get("timeout_s") or 30),
            )
            self.task_runtime.attach_command_run(task_id, result.get("data") if result.get("ok") else {"error": result.get("error")})
            self.hook_executor.run("after_command", {"run_id": run_id, "task_id": task_id, "step_number": step_number, "action": action, "result": result})
            return result

        if tool == "test_runner.run_test":
            result = self.test_runner.run_test(
                command=action.get("command") or self._select_test_command(task_id=task_id),
                cwd=str(action.get("cwd") or self.project_root),
                timeout_s=int(action.get("timeout_s") or 60),
            )
            self.task_runtime.attach_test_run(task_id, result.get("data") if result.get("ok") else {"error": result.get("error")})
            return result

        if tool == "failure_analyzer.analyze":
            latest_test = self.task_runtime.tasks[task_id].get("test_runs", [])
            test_run = latest_test[-1] if latest_test else {}
            return self.failure_analyzer.analyze(test_run, {"task_id": task_id})

        if tool == "subagent.delegate":
            result = self._run_subagent_delegate(
                run_id=run_id,
                task_id=task_id,
                step_number=step_number,
                action=action,
            )
            return result

        return error_result("COMMON_INVALID_INPUT", f"Unsupported tool: {tool}", {"tool": tool})

    def _check(self, *, task_id: str, action: dict, action_result: dict, repeated_failures: int) -> dict:
        if action_result.get("ok"):
            data = action_result.get("data") or {}
            if action.get("tool") == "test_runner.run_test":
                passed = bool(data.get("passed"))
                if passed:
                    return {
                        "passed": True,
                        "should_stop": True,
                        "stop_reason": "success",
                        "outcome": "test_passed",
                        "recovery_record": {"recovery_outcome": "success_no_recovery"},
                    }
                return {
                    "passed": False,
                    "should_stop": False,
                    "retry_same_plan": False,
                    "retry_with_replan": True,
                    "outcome": "test_failed",
                    "retry_reason": "test_assertion_failure",
                    "replan_reason": "test_failed_requires_patch",
                    "recovery_record": {
                        "retry_reason": "test_assertion_failure",
                        "replan_reason": "test_failed_requires_patch",
                        "recovery_policy": "retry_with_replan",
                        "recovery_outcome": "pending",
                    },
                }
            if action.get("tool") == "failure_analyzer.analyze":
                return {
                    "passed": data.get("failure_type") != "unknown",
                    "should_stop": True,
                    "stop_reason": "fallback_to_summary",
                    "outcome": f"analysis:{data.get('failure_type')}",
                    "fallback_reason": str(data.get("failure_type") or "analysis_unknown"),
                    "recovery_record": {
                        "fallback_reason": str(data.get("failure_type") or "analysis_unknown"),
                        "recovery_policy": "fallback_to_summary",
                        "recovery_outcome": "fallback",
                    },
                }
            return {
                "passed": True,
                "should_stop": False,
                "outcome": "success",
                "recovery_record": {"recovery_outcome": "success_no_recovery"},
            }

        err = action_result.get("error") or {}
        code = err.get("code")
        details = err.get("details") or {}
        if code in {"CMD_BLOCKED_BY_POLICY", "EDIT_WRITE_DENIED"} and details.get("needs_confirmation"):
            return {
                "passed": False,
                "should_stop": True,
                "stop_reason": "approval_required_stop",
                "needs_approval": True,
                "outcome": "approval_needed",
                "approval_policy": {
                    "risk_tier": "high",
                    "approval_reason": "tool_guard_confirmation_required",
                    "policy_source": "tool_guard",
                },
                "recovery_record": {
                    "retry_reason": "approval_block",
                    "recovery_policy": "approval_gated_strategy",
                    "recovery_outcome": "stopped_for_approval",
                },
            }

        if repeated_failures + 1 >= self.config.max_failures:
            return {
                "passed": False,
                "should_stop": True,
                "stop_reason": "repeated_failure_stop",
                "outcome": "repeated_failure",
                "retry_reason": "repeated_failure_threshold",
                "recovery_record": {
                    "retry_reason": "repeated_failure_threshold",
                    "recovery_policy": "stop_repeated_failure",
                    "recovery_outcome": "stopped",
                },
            }

        if code in {"TEST_TIMEOUT", "CMD_TIMEOUT"}:
            return {
                "passed": False,
                "should_stop": True,
                "stop_reason": "timeout_stop",
                "outcome": "timeout",
                "retry_reason": "timeout",
                "fallback_reason": "timeout_stop",
                "recovery_record": {
                    "retry_reason": "timeout",
                    "fallback_reason": "timeout_stop",
                    "recovery_policy": "timeout_stop",
                    "recovery_outcome": "stopped",
                },
            }

        return {
            "passed": False,
            "should_stop": False,
            "retry_same_plan": True,
            "retry_with_replan": True,
            "outcome": f"error:{code or 'unknown'}",
            "retry_reason": str(code or "unknown_error"),
            "replan_reason": str(code or "unknown_error"),
            "recovery_record": {
                "retry_reason": str(code or "unknown_error"),
                "replan_reason": str(code or "unknown_error"),
                "recovery_policy": "retry_then_replan",
                "recovery_outcome": "pending",
            },
        }

    def _apply_strategy_to_action(
        self,
        *,
        run_id: str,
        task_id: str,
        step_number: int,
        action: dict,
        strategy: dict[str, Any],
        route_payload: dict[str, Any],
    ) -> dict:
        hints = route_payload.get("planner_hints") or {}
        if strategy.get("chosen_strategy") == "delegate_subagent" or bool(hints.get("delegate_research")):
            return {
                "tool": "subagent.delegate",
                "subtask": str(hints.get("delegated_subtask") or action.get("tool") or "research"),
                "allowed_tools": list(hints.get("allowed_tools") or ["repo_reader.search_files", "repo_reader.search_symbol"]),
                "budget_steps": int(hints.get("subtask_budget_steps") or 3),
                "timeout_s": int(hints.get("subtask_timeout_s") or 30),
                "isolated_context": {"task_id": task_id, "step_number": step_number, "route_domain": route_payload.get("domain")},
            }
        return action

    def _run_subagent_delegate(self, *, run_id: str, task_id: str, step_number: int, action: dict) -> dict:
        budget_steps = int(action.get("budget_steps") or 3)
        budget_check = validate_subtask_budget(budget_steps)
        if not budget_check.get("ok"):
            return error_result("SUBAGENT_INVALID_BUDGET", budget_check["error"]["message"], budget_check["error"])
        child_run_id = f"{run_id}.child.{step_number}"
        subtask = str(action.get("subtask") or "research")
        isolated_context = dict(action.get("isolated_context") or {})
        allowed_tools = list(action.get("allowed_tools") or [])
        self.replay_store.record_event(
            run_id,
            EventType.PLAN,
            step_number,
            {
                "subagent_event": "child_created",
                "child_run_id": child_run_id,
                "parent_run_id": run_id,
                "allowed_tools": allowed_tools,
                "isolated_context": isolated_context,
            },
            "heavy_react.subagent",
        )
        try:
            child_result = self.subagent_runner.run_subtask(
                SubagentRun(
                    subagent_id=f"subagent_{step_number}",
                    parent_run_id=run_id,
                    task=subtask,
                    budget_steps=budget_steps,
                    context={"isolated_context": isolated_context, "allowed_tools": allowed_tools},
                )
            )
        except Exception as exc:
            self.replay_store.record_event(
                run_id,
                EventType.ERROR,
                step_number,
                {"subagent_event": "child_failed", "child_run_id": child_run_id, "error": str(exc)},
                "heavy_react.subagent",
            )
            return ok_result(
                {
                    "subagent_failed": True,
                    "child_run_id": child_run_id,
                    "parent_run_id": run_id,
                    "failure_isolated": True,
                    "merge_decision": {
                        "status": "needs_review",
                        "applied": False,
                        "reason": "child_failure_isolated",
                    },
                }
            )
        merged_trace = merge_subagent_result([], child_result)
        payload = {
            "child_run_id": child_run_id,
            "parent_run_id": run_id,
            "subagent_result": child_result,
            "merge_decision": {
                "status": "accepted",
                "applied": True,
                "reason": "subagent_completed",
                "merged_trace_len": len(merged_trace),
            },
            "failure_isolated": True,
        }
        self.replay_store.record_event(run_id, EventType.ACTION_RESULT, step_number, payload, "heavy_react.subagent")
        self.task_runtime.add_step(
            task_id,
            "react.subagent",
            {
                "run_id": run_id,
                "step_number": step_number,
                "parent_run_id": run_id,
                "child_run_id": child_run_id,
                "allowed_tools": allowed_tools,
                "isolated_context": isolated_context,
                "merge_decision": payload["merge_decision"],
            },
        )
        return ok_result(payload)

    def _select_test_command(self, *, task_id: str) -> str:
        recalled = self.working_memory.get_working_memory(task_id, "recalled_test_command", "")
        if recalled:
            return str(recalled)
        return "pytest -q"

    def _replan_from_failure(self, current_plan: list[dict], action_result: dict, check: dict) -> list[dict]:
        next_plan = list(current_plan[1:]) if len(current_plan) > 1 else []
        if not next_plan or next_plan[0].get("tool") != "failure_analyzer.analyze":
            next_plan.insert(0, {"tool": "failure_analyzer.analyze"})
        if check.get("stop_reason") == "timeout_stop":
            next_plan = [{"tool": "command_runner.run", "command": 'python -c "print(\"timeout_probe\")"'}]
        return next_plan

    def _fallback(self, stop_record: RuntimeStopRecord) -> dict:
        reason = stop_record.reason
        if reason in {"repeated_failure_stop", "no_progress_stop"}:
            return {"mode": "fallback_to_human_review", "detail": {"reason": reason}}
        return {"mode": "fallback_to_summary", "detail": {"reason": reason}}

    def _resolve_target_file(self, task_id: str) -> str | None:
        last_search = self.working_memory.get_working_memory(task_id, "last_search", {})
        data = last_search.get("data") if isinstance(last_search, dict) else {}
        matches = data.get("matches") or []
        if not matches:
            return None
        rel = matches[0].get("path")
        if not rel:
            return None
        return str(Path(self.project_root) / rel)

    def _record_trace(self, *, run_id: str, step_trace: StepTrace) -> None:
        payload = step_trace.to_dict()
        self.replay_store.record_event(run_id, EventType.STEP_START, step_trace.step_number, {"step": step_trace.step_number}, "heavy_react")
        self.replay_store.record_event(
            run_id,
            EventType.PLAN,
            step_trace.step_number,
            {"tool": step_trace.chosen_tool, "route_summary": step_trace.route_summary, "strategy": step_trace.strategy},
            "heavy_react",
        )
        self.replay_store.record_event(run_id, EventType.ACTION_RESULT, step_trace.step_number, step_trace.action_result, "heavy_react")
        self.replay_store.record_event(run_id, EventType.CHECK, step_trace.step_number, step_trace.check_result, "heavy_react")
        self.replay_store.record_event(run_id, EventType.MEMORY_WRITE, step_trace.step_number, payload, "heavy_react.trace")

    def _write_runtime_step(self, *, task_id: str, step_trace: StepTrace) -> None:
        self.task_runtime.add_step(
            task_id,
            "react.step",
            {
                "step_number": step_trace.step_number,
                "chosen_tool": step_trace.chosen_tool,
                "chosen_skill": step_trace.chosen_skill,
                "check_result": step_trace.check_result,
                "stop_reason": step_trace.stop_reason,
                "route_summary": step_trace.route_summary,
            },
        )
        self.working_memory.set_working_memory(task_id, WorkingMemoryKey.LAST_RESULT, step_trace.action_result)
        self.working_memory.set_working_memory(task_id, WorkingMemoryKey.STEP_COUNT, step_trace.step_number + 1)

    def _ensure_skills_loaded(self) -> None:
        # bundled
        bundled = self.skill_loader.load_bundled_skills()
        for entry in bundled.get("data", {}).get("loaded_skills", []):
            self.skill_registry.register_skill(entry)

    def _match_skills(self, task_input: str, observation: dict) -> dict:
        available = self.skill_registry.filter_skills(status="enabled")
        skills = available.get("data", {}).get("items", [])
        task_id = observation.get("task_id") or ""
        route_result = self.working_memory.get_working_memory(
            task_id=task_id,
            key="route_result",
            default={},
        )
        runtime_feedback = self.working_memory.get_working_memory(
            task_id=task_id,
            key="runtime_feedback",
            default={},
        )
        pre_routing_hints = route_result if isinstance(route_result, dict) else {}
        if isinstance(runtime_feedback, dict):
            pre_routing_hints = dict(pre_routing_hints)
            pre_routing_hints["runtime_feedback"] = runtime_feedback
        return self.skill_matcher.match_skills(
            task_input=task_input,
            context=observation,
            available_tools=["repo_reader", "file_editor", "command_runner", "test_runner", "failure_analyzer"],
            available_skills=skills,
            pre_routing_hints=pre_routing_hints,
        )

    @staticmethod
    def _route_summary(route_result: dict[str, Any]) -> dict[str, Any]:
        return {
            "domain": route_result.get("domain"),
            "intent": route_result.get("intent"),
            "confidence": route_result.get("confidence"),
            "fallback_used": bool(route_result.get("fallback_used")),
            "attached_default_skills": list(route_result.get("attached_default_skills") or []),
            "selected_policies": list(route_result.get("selected_policies") or []),
        }

    def _apply_route_hints(self, *, check: dict[str, Any], action: dict[str, Any], route_result: dict[str, Any]) -> dict[str, Any]:
        risk_eval = self.risk_matrix.evaluate_action(
            tool_name=str(action.get("tool") or ""),
            action_input=action,
            route_result=route_result,
        )
        risk = risk_eval.get("data") if risk_eval.get("ok") else {}
        if isinstance(risk, dict):
            check = dict(check)
            check["approval_policy"] = {
                "risk_tier": risk.get("risk_tier"),
                "risk_category": risk.get("risk_category"),
                "approval_required": bool(risk.get("approval_required")),
                "approval_reason": risk.get("approval_reason"),
                "escalation_path": risk.get("escalation_path"),
                "policy_source": risk.get("policy_source"),
            }
            risky_tools = {"command_runner.run", "file_editor.replace_text", "file_editor.insert_text"}
            if risk.get("approval_required") and not check.get("needs_approval") and str(action.get("tool")) in risky_tools:
                check["needs_approval"] = True
                check["should_stop"] = True
                check["stop_reason"] = "approval_required_stop"
                check["outcome"] = "approval_needed_by_risk_matrix"
                check["recovery_record"] = {
                    "retry_reason": "approval_block",
                    "recovery_policy": "approval_gated_strategy",
                    "recovery_outcome": "stopped_for_approval",
                }

        approval = route_result.get("approval_risk_hints") or {}
        if not isinstance(approval, dict):
            return check
        if not approval.get("approval_required"):
            return check
        if check.get("passed"):
            return check
        if check.get("needs_approval"):
            return check
        risky_tools = {"command_runner.run", "file_editor.replace_text", "file_editor.insert_text"}
        if str(action.get("tool")) in risky_tools:
            next_check = dict(check)
            next_check["needs_approval"] = True
            next_check["should_stop"] = True
            next_check["stop_reason"] = "approval_required_stop"
            next_check["outcome"] = "approval_needed_by_route_hint"
            next_check["approval_risk_hints"] = approval
            return next_check
        return check

    @staticmethod
    def _decide_strategy(
        *,
        route_result: dict[str, Any],
        action: dict[str, Any],
        step_number: int,
        repeated_failures: int,
        no_progress_count: int,
    ) -> dict[str, Any]:
        hints = route_result.get("planner_hints") or {}
        task_shape = str(hints.get("task_shape") or "")
        approval_hints = route_result.get("approval_risk_hints") or {}
        strategy_level = "step"
        strategy_type = "execute_plan_step"
        reasons: list[str] = [f"step={step_number}"]

        if step_number == 0:
            strategy_level = "task"
            strategy_type = "task_level_bootstrap"
            reasons.append("initial_step")

        if bool(approval_hints.get("approval_required")) and str(action.get("tool")) in {
            "command_runner.run",
            "file_editor.replace_text",
            "file_editor.insert_text",
        }:
            strategy_type = "approval_gated_strategy"
            reasons.append("approval_risk_hint")

        if repeated_failures > 0:
            strategy_type = "retry_with_replan" if repeated_failures >= 1 else "retry_with_same_plan"
            reasons.append(f"repeated_failures={repeated_failures}")

        if no_progress_count > 0:
            reasons.append(f"no_progress_count={no_progress_count}")

        if hints.get("likely_multi_step"):
            reasons.append("planner_hint:likely_multi_step")
        if hints.get("delegate_research") or task_shape in {"research_heavy", "cross_domain"}:
            strategy_type = "delegate_subagent"
            reasons.append("planner_hint:delegate_subagent")

        return {
            "chosen_strategy": strategy_type,
            "strategy_level": strategy_level,
            "strategy_reasons": reasons,
            "replan_trigger": "failure_feedback" if "replan" in strategy_type else None,
            "fallback_trigger": "approval_required" if strategy_type == "approval_gated_strategy" else None,
            "route_hints_used": {
                "domain": route_result.get("domain"),
                "intent": route_result.get("intent"),
            },
        }

    @staticmethod
    def _route_quality_summary(*, route_payload: dict[str, Any], traces: list[StepTrace]) -> dict[str, Any]:
        confidence = float(route_payload.get("confidence") or 0.0)
        quality = "high"
        if confidence < 0.5:
            quality = "low"
        elif confidence < 0.75:
            quality = "medium"
        return {
            "route_quality": quality,
            "confidence": round(confidence, 4),
            "fallback_used": bool(route_payload.get("fallback_used")),
            "domain": route_payload.get("domain"),
            "intent": route_payload.get("intent"),
            "steps_observed": len(traces),
        }

    @staticmethod
    def _recovery_effectiveness_summary(*, recovery_records: list[dict[str, Any]], traces: list[StepTrace]) -> dict[str, Any]:
        retry_count = sum(1 for item in recovery_records if item.get("retry_reason"))
        replan_count = sum(1 for item in recovery_records if item.get("replan_reason"))
        fallback_count = sum(1 for item in recovery_records if item.get("fallback_reason"))
        outcomes = [str(item.get("recovery_outcome") or "") for item in recovery_records]
        success_like = sum(1 for val in outcomes if "success" in val or "fallback" in val)
        return {
            "retry_count": retry_count,
            "replan_count": replan_count,
            "fallback_count": fallback_count,
            "recovery_records": len(recovery_records),
            "recovery_success_ratio": round((success_like / len(recovery_records)), 4) if recovery_records else 0.0,
            "steps_observed": len(traces),
        }

    @staticmethod
    def _approval_policy_summary(*, approval_records: list[dict[str, Any]], route_payload: dict[str, Any]) -> dict[str, Any]:
        tiers: dict[str, int] = {}
        required_count = 0
        for item in approval_records:
            tier = str(item.get("risk_tier") or "unknown")
            tiers[tier] = tiers.get(tier, 0) + 1
            if item.get("approval_required"):
                required_count += 1
        route_hints = route_payload.get("approval_risk_hints") or {}
        return {
            "approval_events": len(approval_records),
            "approval_required_events": required_count,
            "risk_tier_distribution": tiers,
            "route_approval_required": bool(route_hints.get("approval_required")),
            "route_risk_level": route_hints.get("risk_level"),
        }

    def _evaluate_rethink(
        self,
        *,
        run_id: str,
        task_id: str,
        step_number: int,
        route_payload: dict[str, Any],
        action_result: dict[str, Any],
        check: dict[str, Any],
        repeated_failures: int,
        no_progress_count: int,
    ) -> dict[str, Any] | None:
        context = build_rethink_context(
            run_id=run_id,
            task_id=task_id,
            step_number=step_number,
            route_confidence=float(route_payload.get("confidence") or 1.0),
            test_failed=bool((check.get("failure_record") or {}).get("failure_type") == "test_failed_requires_patch"),
            tool_failed=not bool(action_result.get("ok", True)),
            repeated_failure_count=int(repeated_failures),
            no_progress=bool(no_progress_count >= self.config.no_progress_threshold),
            evidence_insufficient=bool((check.get("route_quality") or {}).get("quality") == "low"),
            approval_denied=bool((check.get("approval_policy") or {}).get("decision") == "deny"),
            subagent_failed=bool((action_result.get("data") or {}).get("subagent_failed")),
            memory_conflict=False,
            policy_blocked=bool((check.get("approval_policy") or {}).get("decision") == "deny"),
        )
        listed = self.skill_registry.list_skills()
        available_skills = [item.get("skill_id") for item in (listed.get("data") or {}).get("items", [])]
        result = evaluate_rethink(context, available_skills=[s for s in available_skills if s])
        if not result.decision.should_rethink:
            return None
        payload = {
            "event": "rethink.completed",
            "trigger": result.decision.trigger,
            "reason": result.decision.reason,
            "strategy_adjustment": result.strategy_adjustment.__dict__,
            "skill_adjustment": result.skill_adjustment.__dict__,
            "revised_plan": result.revised_plan.__dict__,
        }
        self.replay_store.record_event(
            run_id, EventType.PLAN, step_number, {"event": "rethink.started", "trigger": result.decision.trigger}, "heavy_react.rethink"
        )
        self.replay_store.record_event(run_id, EventType.PLAN, step_number, payload, "heavy_react.rethink")
        self.task_runtime.add_step(task_id, "react.rethink", payload)
        self.metrics_store.append_event(
            {
                "run_id": run_id,
                "task_id": task_id,
                "kind": "rethink",
                "step_number": step_number,
                "rethink_trigger": result.decision.trigger,
                "risk_tier": (check.get("approval_policy") or {}).get("risk_tier") or "medium",
            }
        )
        self.memory_store.write(
            {
                "memory_type": "execution",
                "key": "rethink_lesson",
                "value": f"{result.decision.trigger}:{result.strategy_adjustment.strategy}",
                "run_id": run_id,
                "task_id": task_id,
                "source": "rethink",
            }
        )
        return payload

    @staticmethod
    def _rethink_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
        distribution: dict[str, int] = {}
        for item in records:
            trigger = str(item.get("trigger") or "none")
            distribution[trigger] = distribution.get(trigger, 0) + 1
        return {"events": len(records), "trigger_distribution": distribution}
