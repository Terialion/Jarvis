"""Read-only control surface for Phase 2 control/review consumption."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter

from .checkpoint_manager import CheckpointManager
from .data_outlets import DataOutlets
from .release_gate_store import merge_gate_views, read_acceptance_summary, read_release_gate_summary
from .result import error_result, ok_result
from .task_runtime import TaskRuntime


class ControlSurface:
    """Minimal local read-only control interface."""

    def __init__(
        self,
        task_runtime: TaskRuntime,
        checkpoint_manager: CheckpointManager,
        project_root: str | None = None,
    ) -> None:
        self.task_runtime = task_runtime
        self.checkpoint_manager = checkpoint_manager
        self.project_root = str(Path(project_root or ".").resolve())

    def get_task_summary(self, task_id: str) -> dict:
        started = perf_counter()
        task = self.task_runtime.tasks.get(task_id)
        if task is None:
            return self._task_not_found(task_id, started)
        return ok_result(DataOutlets.task_summary(task), started)

    def get_task_timeline(self, task_id: str, limit: int = 50) -> dict:
        started = perf_counter()
        task = self.task_runtime.tasks.get(task_id)
        if task is None:
            return self._task_not_found(task_id, started)
        limit_value = limit if isinstance(limit, int) and limit > 0 else 50
        return ok_result(DataOutlets.task_timeline(task, limit=limit_value), started)

    def get_latest_test_result(self, task_id: str) -> dict:
        started = perf_counter()
        task = self.task_runtime.tasks.get(task_id)
        if task is None:
            return self._task_not_found(task_id, started)
        return ok_result(DataOutlets.latest_test_result(task), started)

    def get_checkpoint_review(self, task_id: str, checkpoint_id: str) -> dict:
        started = perf_counter()
        described = self.checkpoint_manager.describe_checkpoint(
            task_id=task_id,
            checkpoint_id=checkpoint_id,
            record_timeline=False,
        )
        if not described["ok"]:
            return described
        return ok_result(DataOutlets.checkpoint_review(described["data"]), started)

    def get_review_pane(self, task_id: str, checkpoint_id: str | None = None) -> dict:
        started = perf_counter()
        task = self.task_runtime.tasks.get(task_id)
        if task is None:
            return self._task_not_found(task_id, started)

        latest_test = DataOutlets.latest_test_result(task)
        latest_payload = latest_test.get("latest") or {}
        checkpoint_summary = {}
        if checkpoint_id:
            described = self.checkpoint_manager.describe_checkpoint(
                task_id=task_id,
                checkpoint_id=checkpoint_id,
                record_timeline=False,
            )
            if not described["ok"]:
                return described
            checkpoint_summary = DataOutlets.checkpoint_review(described["data"])
        gate_summary = self.get_release_gate_summary()["data"] or {}
        pane = DataOutlets.review_pane(
            task=task,
            rules_warnings=list(task.get("rules_warnings", [])),
            fallback_policy=latest_payload.get("fallback_policy", {}),
            checkpoint_compare_summary=checkpoint_summary,
            test_result_summary=latest_test,
            finalize_summary=task.get("summary"),
            gate_status=gate_summary,
        )
        return ok_result(pane, started)

    def get_ordered_review_fields(self, task_id: str, checkpoint_id: str | None = None) -> dict:
        started = perf_counter()
        pane_result = self.get_review_pane(task_id, checkpoint_id=checkpoint_id)
        if not pane_result.get("ok"):
            return pane_result
        pane = pane_result.get("data") or {}
        return ok_result(
            {
                "task_id": task_id,
                "checkpoint_id": checkpoint_id,
                "contract_version": pane.get("ui_contract_version"),
                "priority_source": pane.get("ui_priority_source"),
                "priority_fields": list(pane.get("ui_priority_fields", [])),
                "ordered_review_fields": list(pane.get("ui_priority_values", [])),
                "unknown_priority_fields": list(pane.get("ui_unknown_priority_fields", [])),
            },
            started,
        )

    def get_release_gate_summary(self) -> dict:
        started = perf_counter()
        release = read_release_gate_summary(self.project_root)
        if not release["ok"]:
            return release
        acceptance = read_acceptance_summary(self.project_root)
        if not acceptance["ok"]:
            return acceptance
        merged = merge_gate_views(release.get("data"), acceptance.get("data"))
        return ok_result(DataOutlets.gate_summary(merged), started)

    def list_recent_tasks(self, limit: int = 10) -> dict:
        started = perf_counter()
        limit_value = limit if isinstance(limit, int) and limit > 0 else 10
        ordered = sorted(
            self.task_runtime.tasks.values(),
            key=lambda t: t.get("updated_at") or "",
            reverse=True,
        )
        items = [DataOutlets.task_summary(task) for task in ordered[:limit_value]]
        return ok_result({"items": items, "count": len(items)}, started)

    def get_operator_runs_recent(
        self,
        *,
        limit: int = 20,
        runtime_status: str | None = None,
        stop_reason: str | None = None,
        success: bool | None = None,
    ) -> dict:
        started = perf_counter()
        runs = self._collect_runs()
        filtered = []
        for run in runs:
            if runtime_status and str(run.get("state")) != str(runtime_status):
                continue
            run_stop = ((run.get("stop_record") or {}).get("reason") if isinstance(run.get("stop_record"), dict) else None)
            if stop_reason and str(run_stop) != str(stop_reason):
                continue
            if success is not None:
                is_success = str(run.get("state")) == "completed" and run_stop == "success"
                if bool(success) != is_success:
                    continue
            filtered.append(run)
        return ok_result(DataOutlets.operator_run_list(filtered, limit=limit), started)

    def get_operator_run(self, run_id: str) -> dict:
        started = perf_counter()
        run = self._find_run_by_id(run_id)
        if run is None:
            return error_result("OPERATOR_RUN_NOT_FOUND", f"Run not found: {run_id}", {"run_id": run_id}, started)
        return ok_result(DataOutlets.operator_run_detail(run), started)

    def get_operator_run_trace(self, run_id: str, *, limit: int = 200) -> dict:
        started = perf_counter()
        run = self._find_run_by_id(run_id)
        if run is None:
            return error_result("OPERATOR_RUN_NOT_FOUND", f"Run not found: {run_id}", {"run_id": run_id}, started)
        return ok_result(DataOutlets.operator_run_trace(run, limit=limit), started)

    def get_operator_run_skill_hits(self, run_id: str) -> dict:
        started = perf_counter()
        run = self._find_run_by_id(run_id)
        if run is None:
            return error_result("OPERATOR_RUN_NOT_FOUND", f"Run not found: {run_id}", {"run_id": run_id}, started)
        return ok_result(DataOutlets.operator_run_skill_hits(run), started)

    def get_operator_run_tool_calls(self, run_id: str) -> dict:
        started = perf_counter()
        run = self._find_run_by_id(run_id)
        if run is None:
            return error_result("OPERATOR_RUN_NOT_FOUND", f"Run not found: {run_id}", {"run_id": run_id}, started)
        return ok_result(DataOutlets.operator_run_tool_calls(run), started)

    def get_operator_run_stop_summary(self, run_id: str) -> dict:
        started = perf_counter()
        run = self._find_run_by_id(run_id)
        if run is None:
            return error_result("OPERATOR_RUN_NOT_FOUND", f"Run not found: {run_id}", {"run_id": run_id}, started)
        return ok_result(DataOutlets.operator_run_stop_summary(run), started)

    def get_operator_review_summary(self) -> dict:
        started = perf_counter()
        tasks = list(self.task_runtime.tasks.values())
        total = len(tasks)
        finalized = 0
        warning_tasks = 0
        needs_approval = 0
        for task in tasks:
            if str(task.get("status")) == "done":
                finalized += 1
            if task.get("rules_warnings"):
                warning_tasks += 1
            if self._task_needs_approval(task):
                needs_approval += 1
        summary = {
            "total_tasks": total,
            "finalized_tasks": finalized,
            "open_tasks": max(0, total - finalized),
            "warning_tasks": warning_tasks,
            "needs_approval_tasks": needs_approval,
        }
        return ok_result(DataOutlets.operator_review_summary(summary), started)

    def get_operator_dashboard(self) -> dict:
        started = perf_counter()
        runs = self._collect_runs()
        recent = DataOutlets.operator_run_list(runs, limit=20)
        active_count = len([run for run in runs if str(run.get("state")) in {"running", "retrying", "waiting_for_approval"}])
        failed_count = len(
            [
                run
                for run in runs
                if str(run.get("state")) in {"failed", "stopped"}
                and ((run.get("stop_record") or {}).get("reason") != "success")
            ]
        )
        gate = self.get_release_gate_summary()
        review = self.get_operator_review_summary()
        runtime_obs = {
            "total_runs": len(runs),
            "active_runs": active_count,
            "failed_or_stopped_runs": failed_count,
            "latest_run_id": self._latest_run_id(runs),
        }
        payload = DataOutlets.operator_dashboard(
            gateway_summary={},
            active_runs_summary={
                "total_runs": len(runs),
                "active_runs": active_count,
                "failed_or_stopped_runs": failed_count,
            },
            recent_runs=recent,
            channels_summary={},
            nodes_summary={},
            gate_summary=DataOutlets.operator_gate_summary(gate.get("data") if gate.get("ok") else {}),
            review_summary=review.get("data") if review.get("ok") else {},
            runtime_observability_summary=runtime_obs,
        )
        return ok_result(payload, started)

    @staticmethod
    def _task_not_found(task_id: str, started: float) -> dict:
        return error_result(
            "TASK_NOT_FOUND",
            f"Task not found: {task_id}",
            {"task_id": task_id},
            started,
        )

    def _collect_runs(self) -> list[dict]:
        runs: list[dict] = []
        for task in self.task_runtime.tasks.values():
            task_runs = list(task.get("react_runs", []))
            for run in task_runs:
                normalized = dict(run)
                normalized.setdefault("task_id", task.get("task_id"))
                runs.append(normalized)
        runs.sort(key=lambda run: str(run.get("run_id") or ""), reverse=True)
        return runs

    def _find_run_by_id(self, run_id: str) -> dict | None:
        if not run_id:
            return None
        for run in self._collect_runs():
            if run.get("run_id") == run_id:
                return run
        return None

    def _latest_run_id(self, runs: list[dict]) -> str | None:
        if not runs:
            return None
        return runs[0].get("run_id")

    def _task_needs_approval(self, task: dict) -> bool:
        for run in task.get("react_runs", []):
            stop_record = run.get("stop_record") or {}
            if isinstance(stop_record, dict) and stop_record.get("reason") == "approval_required_stop":
                return True
        return False
