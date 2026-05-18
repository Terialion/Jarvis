"""Autonomous agent helpers — self-organizing teammates (s11)."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

POLL_INTERVAL = 5  # seconds between idle polls
IDLE_TIMEOUT = 60  # seconds before idle teammate auto-shutdowns

_claim_lock = threading.Lock()


def scan_unclaimed_tasks(tasks_dir: Path) -> list[dict[str, Any]]:
    """Find tasks with status=pending, no owner, and empty blockedBy."""
    unclaimed: list[dict[str, Any]] = []
    tasks_path = Path(tasks_dir)
    if not tasks_path.exists():
        return unclaimed
    for path in sorted(tasks_path.glob("task_plan_*.json")):
        try:
            task = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if (
            task.get("status") == "pending"
            and not task.get("owner")
            and not task.get("blockedBy")
        ):
            unclaimed.append(task)
    return unclaimed


def claim_task(tasks_dir: Path, task_id: str, owner: str) -> dict[str, Any]:
    """Atomically claim a task. Returns {ok: true/false, ...}."""
    with _claim_lock:
        path = Path(tasks_dir) / f"task_{task_id}.json"
        if not path.exists():
            return {"ok": False, "error": f"task_not_found: {task_id}"}
        try:
            task = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"ok": False, "error": "read_error"}

        if task.get("status") != "pending" or task.get("owner"):
            return {"ok": False, "error": "already_claimed"}
        if task.get("blockedBy"):
            return {"ok": False, "error": "task_is_blocked"}

        task["owner"] = owner
        task["status"] = "in_progress"
        import time
        task["updated_at"] = time.time()
        path.write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True, "task": task}


def make_identity_block(name: str, role: str, team_name: str) -> dict[str, Any]:
    """Re-establish teammate identity after context compression."""
    return {
        "role": "user",
        "content": (
            f"<identity>You are '{name}', role: {role}, "
            f"team: {team_name}. Continue your work.</identity>"
        ),
    }
