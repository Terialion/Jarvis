"""Background task manager for parallel execution of long-running operations."""

from __future__ import annotations

import time
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Callable
from uuid import uuid4


@dataclass
class BackgroundTask:
    task_id: str
    description: str = ""
    status: str = "running"  # running | completed | failed | cancelled
    created_at: float = field(default_factory=time.perf_counter)
    result: Any = None
    error: str | None = None
    _future: Future | None = field(default=None, repr=False)


class BackgroundTaskManager:
    """Thread-pool based manager for running tasks in the background.

    Usage::

        mgr = BackgroundTaskManager(max_workers=4)
        task_id = mgr.submit("Run tests", some_function, arg1, arg2)
        # ... later ...
        status = mgr.check(task_id)  # {"status": "completed", "result": ...}
    """

    def __init__(self, max_workers: int = 4) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._tasks: dict[str, BackgroundTask] = {}
        self._lock = Lock()
        self._notification_queue: list[dict[str, Any]] = []

    def submit(self, description: str, fn: Callable, *args: Any, **kwargs: Any) -> str:
        """Submit a callable for background execution. Returns the task_id."""
        task_id = f"bg_{uuid4().hex[:12]}"
        task = BackgroundTask(task_id=task_id, description=description)
        future = self._executor.submit(self._run_and_store, task, fn, *args, **kwargs)
        task._future = future
        with self._lock:
            self._tasks[task_id] = task
        return task_id

    def check(self, task_id: str) -> dict[str, Any]:
        """Check the status of a background task."""
        with self._lock:
            task = self._tasks.get(task_id)
        if task is None:
            return {"task_id": task_id, "status": "not_found"}
        return {
            "task_id": task_id,
            "status": task.status,
            "description": task.description,
            "result": task.result if task.status == "completed" else None,
            "error": task.error,
        }

    def check_blocking(self, task_id: str, timeout: float = 30.0) -> dict[str, Any]:
        """Block until the task completes or timeout expires."""
        with self._lock:
            task = self._tasks.get(task_id)
        if task is None:
            return {"task_id": task_id, "status": "not_found"}
        if task._future is not None:
            try:
                task._future.result(timeout=timeout)
            except FutureTimeoutError:
                pass
            except Exception:
                pass
        return self.check(task_id)

    def cancel(self, task_id: str) -> bool:
        """Cancel a running background task."""
        with self._lock:
            task = self._tasks.get(task_id)
        if task is None:
            return False
        if task._future is not None and not task._future.done():
            cancelled = task._future.cancel()
            if cancelled:
                task.status = "cancelled"
            return cancelled
        return False

    def list_tasks(self) -> list[dict[str, Any]]:
        """List all background tasks."""
        with self._lock:
            return [self.check(tid) for tid in self._tasks]

    def wait_any(self, task_ids: list[str], timeout: float = 30.0) -> list[str]:
        """Return the subset of task_ids that have completed."""
        completed: list[str] = []
        deadline = time.perf_counter() + timeout
        while time.perf_counter() < deadline:
            with self._lock:
                for tid in task_ids:
                    task = self._tasks.get(tid)
                    if task and task.status in ("completed", "failed", "cancelled"):
                        if tid not in completed:
                            completed.append(tid)
            if len(completed) >= len(task_ids):
                break
            time.sleep(0.1)
        return completed

    def drain_notifications(self) -> list[dict[str, Any]]:
        """Return and clear all pending completion notifications."""
        with self._lock:
            notifs = list(self._notification_queue)
            self._notification_queue.clear()
        return notifs

    def _run_and_store(self, task: BackgroundTask, fn: Callable, *args: Any, **kwargs: Any) -> None:
        try:
            task.result = fn(*args, **kwargs)
            task.status = "completed"
        except Exception as exc:
            task.error = str(exc)
            task.status = "failed"
        with self._lock:
            self._notification_queue.append({
                "task_id": task.task_id,
                "description": task.description,
                "status": task.status,
                "result": str(task.result)[:2000] if task.status == "completed" else None,
                "error": task.error if task.status == "failed" else None,
            })

    def shutdown(self, *, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait)
