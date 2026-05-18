"""Tests for PersistentTaskManager — cross-session file-based task persistence."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.jarvis.core.tasks.manager import PersistentTaskManager


@pytest.fixture
def tasks_dir():
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


@pytest.fixture
def manager(tasks_dir):
    return PersistentTaskManager(tasks_dir=tasks_dir)


class TestPersistentTaskManager:
    def test_create_and_get(self, manager):
        task = manager.create(subject="Add auth", description="Implement login flow")
        assert task["id"].startswith("plan_")
        assert task["subject"] == "Add auth"
        assert task["status"] == "pending"

        fetched = manager.get(task["id"])
        assert fetched is not None
        assert fetched["subject"] == "Add auth"

    def test_get_nonexistent_returns_none(self, manager):
        assert manager.get("plan_nonexistent") is None

    def test_update_status(self, manager):
        task = manager.create(subject="Refactor config")
        updated = manager.update(task["id"], status="in_progress")
        assert updated["status"] == "in_progress"

        fetched = manager.get(task["id"])
        assert fetched["status"] == "in_progress"

    def test_blockedby_auto_clear_on_completion(self, manager):
        b = manager.create(subject="Task B")
        a = manager.create(subject="Task A", blocked_by=[b["id"]])

        assert b["id"] in manager.get(a["id"])["blockedBy"]

        manager.update(b["id"], status="completed")

        a_after = manager.get(a["id"])
        assert b["id"] not in a_after["blockedBy"]

    def test_list_all(self, manager):
        manager.create(subject="First task")
        manager.create(subject="Second task")
        all_tasks = manager.list_all()
        assert len(all_tasks) >= 2

    def test_list_by_session(self, manager):
        manager.create(subject="Session A task", session_id="sess_a")
        manager.create(subject="Session B task", session_id="sess_b")

        a_tasks = manager.list_all(session_id="sess_a")
        b_tasks = manager.list_all(session_id="sess_b")
        assert len(a_tasks) >= 1
        assert len(b_tasks) >= 1
        assert all(t["session_id"] == "sess_a" for t in a_tasks)

    def test_list_by_status(self, manager):
        manager.create(subject="Pending task")
        t2 = manager.create(subject="Done task")
        manager.update(t2["id"], status="completed")

        pending = manager.list_by_status("pending")
        completed = manager.list_by_status("completed")
        assert len(pending) >= 1
        assert len(completed) >= 1

    def test_update_add_blocked_by(self, manager):
        a = manager.create(subject="Task A")
        b = manager.create(subject="Task B")
        manager.update(a["id"], add_blocked_by=[b["id"]])
        assert b["id"] in manager.get(a["id"])["blockedBy"]

    def test_update_remove_blocked_by(self, manager):
        a = manager.create(subject="Task A", blocked_by=["plan_xyz"])
        manager.update(a["id"], remove_blocked_by=["plan_xyz"])
        assert "plan_xyz" not in manager.get(a["id"])["blockedBy"]

    def test_update_nonexistent_returns_none(self, manager):
        assert manager.update("plan_nonexistent", status="completed") is None

    def test_persistence_across_instances(self, tasks_dir):
        m1 = PersistentTaskManager(tasks_dir=tasks_dir)
        task = m1.create(subject="Survive restart")
        tid = task["id"]

        m2 = PersistentTaskManager(tasks_dir=tasks_dir)
        fetched = m2.get(tid)
        assert fetched is not None
        assert fetched["subject"] == "Survive restart"

    def test_file_format_is_valid_json(self, manager, tasks_dir):
        task = manager.create(subject="Check format", description="desc")
        path = tasks_dir / f"task_{task['id']}.json"
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["id"] == task["id"]
        assert data["subject"] == "Check format"

    def test_custom_task_id(self, manager):
        task = manager.create(subject="Custom ID", task_id="plan_mycustomid")
        assert task["id"] == "plan_mycustomid"
        assert manager.get("plan_mycustomid") is not None


class TestWorktreeBinding:
    def test_bind_worktree(self, manager):
        task = manager.create(subject="Auth refactor")
        result = manager.bind_worktree(task["id"], "auth-wt")
        assert result is not None
        assert result["worktree"] == "auth-wt"
        assert result["status"] == "in_progress"  # promoted from pending

    def test_bind_worktree_nonexistent(self, manager):
        assert manager.bind_worktree("plan_nope", "wt") is None

    def test_unbind_worktree(self, manager):
        task = manager.create(subject="UI fix")
        manager.bind_worktree(task["id"], "ui-wt")
        result = manager.unbind_worktree(task["id"])
        assert result is not None
        assert result["worktree"] == ""

    def test_bind_does_not_change_already_in_progress(self, manager):
        task = manager.create(subject="In progress")
        manager.update(task["id"], status="in_progress")
        result = manager.bind_worktree(task["id"], "wt")
        assert result["status"] == "in_progress"
