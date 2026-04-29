"""Checkpoint / Rollback skeleton for Jarvis Core Phase 1."""

from __future__ import annotations

from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

from .result import error_result, ok_result
from .task_runtime import TaskRuntime


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CheckpointManager:
    """Minimal checkpoint skeleton attached to TaskRuntime."""

    def __init__(self, task_runtime: TaskRuntime) -> None:
        self.task_runtime = task_runtime
        self.default_top_n = 5
        self.default_sort_mode = "recent"

    def create_checkpoint(self, task_id: str, label: str, metadata: dict | None = None) -> dict:
        started = perf_counter()
        if not task_id or not label:
            return error_result(
                "COMMON_INVALID_INPUT",
                "task_id and label are required",
                {"task_id": task_id, "label": label},
                started,
            )
        task = self.task_runtime.tasks.get(task_id)
        if task is None:
            return error_result(
                "TASK_NOT_FOUND",
                f"Task not found: {task_id}",
                {"task_id": task_id},
                started,
            )

        checkpoint = {
            "checkpoint_id": f"ckpt_{uuid4().hex[:10]}",
            "task_id": task_id,
            "label": label,
            "metadata": metadata or {},
            "created_at": _utc_now(),
            "snapshot": {
                "status": task.get("status"),
                "steps_count": len(task.get("steps", [])),
                "changed_files_count": len(task.get("changed_files", [])),
                "command_runs_count": len(task.get("command_runs", [])),
                "test_runs_count": len(task.get("test_runs", [])),
                "key_steps": self._summarize_steps(task.get("steps", []), max_items=self.default_top_n),
                "step_ids": [step.get("step_id") for step in task.get("steps", []) if step.get("step_id")],
            },
        }
        task.setdefault("checkpoints", []).append(checkpoint)
        task["updated_at"] = _utc_now()
        self.task_runtime.add_checkpoint_step(
            task_id,
            "create",
            {"checkpoint_id": checkpoint["checkpoint_id"], "label": label, "metadata": metadata or {}},
        )
        return ok_result(checkpoint, started)

    def list_checkpoints(self, task_id: str) -> dict:
        started = perf_counter()
        task = self.task_runtime.tasks.get(task_id)
        if task is None:
            return error_result(
                "TASK_NOT_FOUND",
                f"Task not found: {task_id}",
                {"task_id": task_id},
                started,
            )
        checkpoints = list(task.get("checkpoints", []))
        self.task_runtime.add_checkpoint_step(
            task_id,
            "list",
            {"count": len(checkpoints)},
        )
        return ok_result({"task_id": task_id, "checkpoints": checkpoints}, started)

    def describe_checkpoint(
        self,
        task_id: str,
        checkpoint_id: str,
        top_n: int = 5,
        sort_mode: str = "recent",
        record_timeline: bool = True,
    ) -> dict:
        started = perf_counter()
        task = self.task_runtime.tasks.get(task_id)
        if task is None:
            return error_result(
                "TASK_NOT_FOUND",
                f"Task not found: {task_id}",
                {"task_id": task_id},
                started,
            )
        checkpoints = list(task.get("checkpoints", []))
        checkpoint = next((c for c in checkpoints if c.get("checkpoint_id") == checkpoint_id), None)
        if checkpoint is None:
            return error_result(
                "COMMON_NOT_FOUND",
                f"Checkpoint not found: {checkpoint_id}",
                {"task_id": task_id, "checkpoint_id": checkpoint_id},
                started,
            )

        top_n_used = self._coerce_top_n(top_n)
        sort_mode_used = self._coerce_sort_mode(sort_mode)
        snapshot = checkpoint.get("snapshot") or {}
        checkpoint_key_steps = list(snapshot.get("key_steps") or [])[-top_n_used:]
        current_key_steps = self._summarize_steps(task.get("steps", []), max_items=top_n_used)
        current_state = {
            "status": task.get("status"),
            "steps_count": len(task.get("steps", [])),
            "changed_files_count": len(task.get("changed_files", [])),
            "command_runs_count": len(task.get("command_runs", [])),
            "test_runs_count": len(task.get("test_runs", [])),
        }
        checkpoint_step_types = [step.get("step_type", "") for step in checkpoint_key_steps]
        current_step_types = [step.get("step_type", "") for step in current_key_steps]
        new_step_types = [s for s in current_step_types if s and s not in checkpoint_step_types]
        delta = {
            "steps_delta": current_state["steps_count"] - int(snapshot.get("steps_count", 0)),
            "changed_files_delta": current_state["changed_files_count"] - int(snapshot.get("changed_files_count", 0)),
            "command_runs_delta": current_state["command_runs_count"] - int(snapshot.get("command_runs_count", 0)),
            "test_runs_delta": current_state["test_runs_count"] - int(snapshot.get("test_runs_count", 0)),
            "new_step_types_since_checkpoint": new_step_types,
            "latest_current_step_type": current_step_types[-1] if current_step_types else None,
        }
        top_changed_steps = self._top_changed_steps(
            task_steps=task.get("steps", []),
            checkpoint_snapshot=snapshot,
            top_n=top_n_used,
            sort_mode=sort_mode_used,
        )
        if record_timeline:
            self.task_runtime.add_checkpoint_step(
                task_id,
                "describe",
                {"checkpoint_id": checkpoint_id, "top_n": top_n_used, "sort_mode": sort_mode_used},
            )
        return ok_result(
            {
                "task_id": task_id,
                "checkpoint_id": checkpoint_id,
                "checkpoint_label": checkpoint.get("label"),
                "created_at": checkpoint.get("created_at"),
                "checkpoint_metadata": checkpoint.get("metadata", {}),
                "checkpoint_snapshot": snapshot,
                "checkpoint_key_steps": checkpoint_key_steps,
                "current_key_steps": current_key_steps,
                "top_changed_steps": top_changed_steps,
                "current_state": current_state,
                "delta": delta,
                "top_n_used": top_n_used,
                "sort_mode_used": sort_mode_used,
            },
            started,
        )

    def _summarize_steps(self, steps: list[dict], max_items: int = 5) -> list[dict]:
        if not steps:
            return []
        selected = steps[-max_items:]
        summarized: list[dict] = []
        for step in selected:
            payload = step.get("input_payload") or {}
            payload_keys = sorted(list(payload.keys()))[:4] if isinstance(payload, dict) else []
            summarized.append(
                {
                    "step_id": step.get("step_id"),
                    "step_type": step.get("step_type"),
                    "status": step.get("status"),
                    "payload_keys": payload_keys,
                }
            )
        return summarized

    def _top_changed_steps(
        self,
        task_steps: list[dict],
        checkpoint_snapshot: dict,
        top_n: int,
        sort_mode: str,
    ) -> list[dict]:
        checkpoint_step_ids = set(checkpoint_snapshot.get("step_ids") or [])
        with_index = list(enumerate(task_steps, start=1))
        changed = [(idx, step) for idx, step in with_index if step.get("step_id") not in checkpoint_step_ids]
        if sort_mode == "importance":
            changed_sorted = sorted(
                changed,
                key=lambda item: (
                    self._importance_score(item[1]),
                    item[1].get("timeline_index", item[0]),
                ),
                reverse=True,
            )
        else:
            # Stable order by recency first; tie-breaker by timeline index descending.
            changed_sorted = sorted(changed, key=lambda item: item[0], reverse=True)
        top = changed_sorted[:top_n]
        result: list[dict] = []
        for idx, step in top:
            result.append(
                {
                    "timeline_index": step.get("timeline_index", idx),
                    "step_id": step.get("step_id"),
                    "step_type": step.get("step_type"),
                    "status": step.get("status"),
                }
            )
        return result

    def _coerce_top_n(self, top_n: int) -> int:
        if isinstance(top_n, int) and top_n > 0:
            return top_n
        return self.default_top_n

    def _coerce_sort_mode(self, sort_mode: str) -> str:
        mode = (sort_mode or "").strip().lower()
        if mode in {"recent", "importance"}:
            return mode
        return self.default_sort_mode

    @staticmethod
    def _importance_score(step: dict) -> int:
        step_type = str(step.get("step_type") or "").lower()
        if step_type.startswith("checkpoint.describe"):
            return 90
        if step_type.startswith("checkpoint.create"):
            return 80
        if "analyze_failure" in step_type:
            return 75
        if "run_test" in step_type:
            return 70
        if "file_edit" in step_type:
            return 65
        if "repo_read" in step_type:
            return 55
        if step_type.startswith("checkpoint."):
            return 50
        return 40
