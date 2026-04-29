"""TaskRuntime snapshot helpers for local single-process control-surface wiring."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from .result import error_result, ok_result
from .task_runtime import TaskRuntime


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_runtime_snapshot(task_runtime: TaskRuntime, path: str) -> dict:
    started = perf_counter()
    if not isinstance(task_runtime, TaskRuntime):
        return error_result(
            "COMMON_INVALID_INPUT",
            "task_runtime must be a TaskRuntime instance",
            {"received_type": str(type(task_runtime))},
            started,
        )
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0.0",
        "saved_at": _utc_now(),
        "sessions": task_runtime.sessions,
        "tasks": task_runtime.tasks,
    }
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return ok_result({"path": str(target), "snapshot": payload}, started)


def load_runtime_snapshot(path: str) -> dict:
    started = perf_counter()
    target = Path(path)
    if not target.exists():
        return error_result(
            "COMMON_NOT_FOUND",
            f"Runtime snapshot not found: {path}",
            {"path": path},
            started,
        )
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except Exception as exc:
        return error_result(
            "COMMON_INTERNAL_ERROR",
            "Failed to parse runtime snapshot",
            {"path": path, "exception": str(exc)},
            started,
        )
    if not isinstance(payload, dict):
        return error_result(
            "COMMON_INVALID_INPUT",
            "Runtime snapshot payload must be an object",
            {"path": path},
            started,
        )
    runtime = TaskRuntime()
    sessions = payload.get("sessions", {})
    tasks = payload.get("tasks", {})
    if not isinstance(sessions, dict) or not isinstance(tasks, dict):
        return error_result(
            "COMMON_INVALID_INPUT",
            "Invalid runtime snapshot structure",
            {"path": path},
            started,
        )
    runtime.sessions = sessions
    runtime.tasks = tasks
    return ok_result({"runtime": runtime, "snapshot": payload, "path": str(target)}, started)
