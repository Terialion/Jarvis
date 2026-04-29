"""Task Runtime module for Jarvis Core Phase 1."""

from __future__ import annotations

from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

from .result import error_result, ok_result


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TaskRuntime:
    """In-memory runtime for tracking minimal task lifecycle and artifacts."""

    _allowed_statuses = {"created", "running", "blocked", "failed", "completed"}

    def __init__(self) -> None:
        self.sessions: dict[str, dict] = {}
        self.tasks: dict[str, dict] = {}

    def create_task(self, project_id: str, title: str, session_id: str | None = None) -> dict:
        started = perf_counter()
        if not project_id or not title:
            return error_result(
                "COMMON_INVALID_INPUT",
                "project_id and title are required",
                {"project_id": project_id, "title": title},
                started,
            )
        sid = session_id or f"session_{uuid4().hex[:8]}"
        task_id = f"task_{uuid4().hex[:10]}"
        now = _utc_now()
        task = {
            "task_id": task_id,
            "session_id": sid,
            "project_id": project_id,
            "title": title,
            "status": "created",
            "created_at": now,
            "updated_at": now,
            "steps": [],
            "changed_files": [],
            "command_runs": [],
            "test_runs": [],
            "checkpoints": [],
            "summary": None,
        }
        self.tasks[task_id] = task
        self.sessions.setdefault(sid, {"session_id": sid, "task_ids": []})["task_ids"].append(task_id)
        return ok_result(task, started)

    def add_step(self, task_id: str, step_type: str, payload: dict) -> dict:
        started = perf_counter()
        task = self._get_task(task_id)
        if task is None:
            return self._task_not_found(task_id, started)
        if not step_type:
            return error_result(
                "COMMON_INVALID_INPUT",
                "step_type is required",
                {"step_type": step_type},
                started,
            )
        step = {
            "step_id": f"step_{uuid4().hex[:10]}",
            "timeline_index": len(task["steps"]) + 1,
            "step_type": step_type,
            "status": "completed",
            "started_at": _utc_now(),
            "finished_at": _utc_now(),
            "input_payload": payload or {},
            "output_payload": {},
        }
        task["steps"].append(step)
        task["updated_at"] = _utc_now()
        return ok_result(step, started)

    def add_checkpoint_step(self, task_id: str, action: str, payload: dict | None = None) -> dict:
        checkpoint_payload = {
            "timeline_category": "checkpoint",
            "timeline_source": "checkpoint_manager",
            "checkpoint_action": action,
            "review_ready": True,
            **(payload or {}),
        }
        return self.add_step(task_id, f"checkpoint.{action}", checkpoint_payload)

    def set_status(self, task_id: str, status: str) -> dict:
        started = perf_counter()
        task = self._get_task(task_id)
        if task is None:
            return self._task_not_found(task_id, started)
        if status not in self._allowed_statuses:
            return error_result(
                "TASK_INVALID_STATE",
                f"Unsupported task status: {status}",
                {"status": status, "allowed": sorted(self._allowed_statuses)},
                started,
            )
        task["status"] = status
        task["updated_at"] = _utc_now()
        return ok_result({"task_id": task_id, "status": status}, started)

    def attach_file_change(self, task_id: str, change: dict) -> dict:
        return self._attach(task_id, "changed_files", change, "file_change")

    def attach_command_run(self, task_id: str, run: dict) -> dict:
        return self._attach(task_id, "command_runs", run, "command_run")

    def attach_test_run(self, task_id: str, run: dict) -> dict:
        return self._attach(task_id, "test_runs", run, "test_run")

    def finalize(self, task_id: str, summary: str) -> dict:
        started = perf_counter()
        task = self._get_task(task_id)
        if task is None:
            return self._task_not_found(task_id, started)
        task["summary"] = summary
        task["status"] = "completed"
        task["updated_at"] = _utc_now()
        return ok_result(task, started)

    def _attach(self, task_id: str, field: str, payload: dict, kind: str) -> dict:
        started = perf_counter()
        task = self._get_task(task_id)
        if task is None:
            return self._task_not_found(task_id, started)
        if not isinstance(payload, dict):
            return error_result(
                "TASK_STEP_ATTACH_FAILED",
                f"{kind} payload must be a dict",
                {"payload_type": str(type(payload))},
                started,
            )
        task[field].append(payload)
        task["updated_at"] = _utc_now()
        return ok_result({"task_id": task_id, "field": field, "count": len(task[field])}, started)

    def _get_task(self, task_id: str) -> dict | None:
        return self.tasks.get(task_id)

    @staticmethod
    def _task_not_found(task_id: str, started: float) -> dict:
        return error_result(
            "TASK_NOT_FOUND",
            f"Task not found: {task_id}",
            {"task_id": task_id},
            started,
        )
