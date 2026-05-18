"""Persistent cross-session task manager backed by .jarvis/tasks/*.json files."""

from __future__ import annotations

import json
import time
from pathlib import Path
from threading import Lock
from typing import Any


class PersistentTaskManager:
    """File-based task persistence that survives session restarts.

    Each task is stored as ``.jarvis/tasks/task_{plan_id}.json``.
    """

    def __init__(self, tasks_dir: Path) -> None:
        self.tasks_dir = Path(tasks_dir)
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._id_counter = 0

    # ── internal helpers ──────────────────────────────────────────

    def _path(self, task_id: str) -> Path:
        return self.tasks_dir / f"task_{task_id}.json"

    def _load(self, task_id: str) -> dict[str, Any] | None:
        path = self._path(task_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def _save(self, task: dict[str, Any]) -> None:
        path = self._path(str(task["id"]))
        path.write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── public API ────────────────────────────────────────────────

    def create(
        self,
        subject: str,
        description: str = "",
        session_id: str = "",
        task_id: str = "",
        blocked_by: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._id_counter += 1
        task: dict[str, Any] = {
            "id": task_id or f"plan_{int(time.time() * 1_000_000)}_{self._id_counter}",
            "subject": subject,
            "description": description,
            "status": "pending",
            "owner": "",
            "worktree": "",
            "blockedBy": list(blocked_by or []),
            "session_id": session_id,
            "created_at": time.time(),
            "updated_at": time.time(),
            "metadata": dict(metadata or {}),
        }
        with self._lock:
            self._save(task)
        return task

    def get(self, task_id: str) -> dict[str, Any] | None:
        return self._load(task_id)

    def update(
        self,
        task_id: str,
        *,
        status: str | None = None,
        owner: str | None = None,
        add_blocked_by: list[str] | None = None,
        remove_blocked_by: list[str] | None = None,
    ) -> dict[str, Any] | None:
        with self._lock:
            task = self._load(task_id)
            if task is None:
                return None

            if status is not None:
                task["status"] = status
            if owner is not None:
                task["owner"] = owner

            if add_blocked_by:
                for bid in add_blocked_by:
                    if bid not in task.get("blockedBy", []):
                        task.setdefault("blockedBy", []).append(bid)
            if remove_blocked_by:
                blocked = task.get("blockedBy", [])
                task["blockedBy"] = [b for b in blocked if b not in remove_blocked_by]

            task["updated_at"] = time.time()

            self._save(task)

            if status == "completed":
                self._clear_dependency(task_id)

            return task

    def _clear_dependency(self, completed_id: str) -> None:
        """Remove *completed_id* from every other task's blockedBy list."""
        for path in sorted(self.tasks_dir.glob("task_plan_*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            blocked = data.get("blockedBy", [])
            if completed_id in blocked:
                data["blockedBy"] = [b for b in blocked if b != completed_id]
                data["updated_at"] = time.time()
                path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_all(self, session_id: str | None = None) -> list[dict[str, Any]]:
        tasks: list[dict[str, Any]] = []
        for path in sorted(self.tasks_dir.glob("task_plan_*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if session_id and data.get("session_id") != session_id:
                continue
            tasks.append(data)
        tasks.sort(key=lambda t: t.get("created_at", 0), reverse=True)
        return tasks

    def list_by_status(self, status: str) -> list[dict[str, Any]]:
        return [t for t in self.list_all() if t.get("status") == status]

    # ── worktree binding (used by s12) ────────────────────────────

    def bind_worktree(self, task_id: str, worktree_name: str) -> dict[str, Any] | None:
        with self._lock:
            task = self._load(task_id)
            if task is None:
                return None
            task["worktree"] = worktree_name
            if task.get("status") == "pending":
                task["status"] = "in_progress"
            task["updated_at"] = time.time()
            self._save(task)
            return task

    def unbind_worktree(self, task_id: str) -> dict[str, Any] | None:
        with self._lock:
            task = self._load(task_id)
            if task is None:
                return None
            task["worktree"] = ""
            task["updated_at"] = time.time()
            self._save(task)
            return task
