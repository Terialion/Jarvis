"""Tests for autonomous agent helpers (s11)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.jarvis.core.teams.autonomous import (
    claim_task,
    make_identity_block,
    scan_unclaimed_tasks,
)
from src.jarvis.core.tasks.manager import PersistentTaskManager


@pytest.fixture
def tasks_dir():
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


class TestScanUnclaimed:
    def test_returns_pending_with_no_owner(self, tasks_dir):
        mgr = PersistentTaskManager(tasks_dir=tasks_dir)
        mgr.create(subject="Fix bug", session_id="s1")
        unclaimed = scan_unclaimed_tasks(tasks_dir)
        assert len(unclaimed) >= 1
        task = unclaimed[0]
        assert task["status"] == "pending"
        assert not task.get("owner")

    def test_skips_with_owner(self, tasks_dir):
        mgr = PersistentTaskManager(tasks_dir=tasks_dir)
        t = mgr.create(subject="Already claimed", session_id="s1")
        mgr.update(t["id"], status="in_progress", owner="alice")
        unclaimed = scan_unclaimed_tasks(tasks_dir)
        assert not any(u["id"] == t["id"] for u in unclaimed)

    def test_skips_blocked(self, tasks_dir):
        mgr = PersistentTaskManager(tasks_dir=tasks_dir)
        mgr.create(subject="Blocked task", session_id="s1", blocked_by=["plan_xyz"])
        unclaimed = scan_unclaimed_tasks(tasks_dir)
        assert len(unclaimed) == 0

    def test_skips_completed(self, tasks_dir):
        mgr = PersistentTaskManager(tasks_dir=tasks_dir)
        t = mgr.create(subject="Done", session_id="s1")
        mgr.update(t["id"], status="completed")
        unclaimed = scan_unclaimed_tasks(tasks_dir)
        assert not any(u["id"] == t["id"] for u in unclaimed)

    def test_empty_dir(self, tasks_dir):
        assert scan_unclaimed_tasks(tasks_dir) == []


class TestClaimTask:
    def test_claim_sets_owner_and_status(self, tasks_dir):
        mgr = PersistentTaskManager(tasks_dir=tasks_dir)
        t = mgr.create(subject="Refactor utils", session_id="s1")
        result = claim_task(tasks_dir, t["id"], "bob")
        assert result["ok"]
        assert result["task"]["owner"] == "bob"
        assert result["task"]["status"] == "in_progress"

    def test_rejects_already_claimed(self, tasks_dir):
        mgr = PersistentTaskManager(tasks_dir=tasks_dir)
        t = mgr.create(subject="Claimed", session_id="s1")
        claim_task(tasks_dir, t["id"], "alice")
        result = claim_task(tasks_dir, t["id"], "bob")
        assert not result["ok"]
        assert "already_claimed" in result["error"]

    def test_rejects_nonexistent(self, tasks_dir):
        result = claim_task(tasks_dir, "plan_nope", "alice")
        assert not result["ok"]

    def test_rejects_blocked(self, tasks_dir):
        mgr = PersistentTaskManager(tasks_dir=tasks_dir)
        t = mgr.create(subject="Blocked", session_id="s1", blocked_by=["plan_abc"])
        result = claim_task(tasks_dir, t["id"], "alice")
        assert not result["ok"]
        assert "blocked" in result["error"]


class TestIdentityBlock:
    def test_contains_name_role_team(self):
        block = make_identity_block("alice", "coder", "dream-team")
        content = block["content"]
        assert "alice" in content
        assert "coder" in content
        assert "dream-team" in content
        assert block["role"] == "user"
