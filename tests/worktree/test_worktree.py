"""Tests for worktree manager and event bus (s12)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.jarvis.core.worktree.event_bus import EventBus
from src.jarvis.core.worktree.manager import WorktreeManager


# ── EventBus tests ──────────────────────────────────────────────────


class TestEventBus:
    def test_emit_and_list_recent(self):
        with tempfile.TemporaryDirectory() as td:
            bus = EventBus(Path(td) / "events.jsonl")
            bus.emit("worktree.create.before", worktree={"name": "s12"})
            bus.emit("worktree.create.after", worktree={"name": "s12"})
            entries = bus.list_recent(limit=10)
            assert len(entries) == 2
            assert entries[0]["event"] == "worktree.create.before"
            assert entries[1]["worktree"]["name"] == "s12"

    def test_list_recent_empty_when_no_file(self):
        with tempfile.TemporaryDirectory() as td:
            bus = EventBus(Path(td) / "nonexistent" / "events.jsonl")
            assert bus.list_recent() == []

    def test_emit_includes_task_error(self):
        with tempfile.TemporaryDirectory() as td:
            bus = EventBus(Path(td) / "events.jsonl")
            bus.emit("worktree.create.failed", worktree={"name": "bad"}, error="something broke")
            entries = bus.list_recent()
            assert len(entries) == 1
            assert entries[0]["error"] == "something broke"
            assert entries[0]["worktree"]["name"] == "bad"

    def test_emit_includes_task(self):
        with tempfile.TemporaryDirectory() as td:
            bus = EventBus(Path(td) / "events.jsonl")
            bus.emit("task.completed", task={"id": "plan_1"})
            entries = bus.list_recent()
            assert entries[0]["task"]["id"] == "plan_1"

    def test_list_recent_respects_limit(self):
        with tempfile.TemporaryDirectory() as td:
            bus = EventBus(Path(td) / "events.jsonl")
            for i in range(10):
                bus.emit(f"event_{i}")
            assert len(bus.list_recent(limit=3)) == 3


# ── WorktreeManager tests ───────────────────────────────────────────


class TestWorktreeManager:
    def test_validate_name_rejects_empty(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            with tempfile.TemporaryDirectory() as td:
                mgr = WorktreeManager(Path(td))
                result = mgr.create("")
                assert not result["ok"]
                assert "invalid" in result["error"]

    def test_validate_name_rejects_special_chars(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            with tempfile.TemporaryDirectory() as td:
                mgr = WorktreeManager(Path(td))
                result = mgr.create("na me")
                assert not result["ok"]
                assert "invalid" in result["error"]

    def test_validate_name_accepts_valid(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="", stderr=""),  # git rev-parse
                MagicMock(returncode=0, stdout="", stderr=""),  # git worktree add
            ]
            with tempfile.TemporaryDirectory() as td:
                mgr = WorktreeManager(Path(td))
                result = mgr.create("my-s12.task")
                assert result["ok"]

    def test_create_and_list(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="", stderr=""),
                MagicMock(returncode=0, stdout="", stderr=""),
            ]
            with tempfile.TemporaryDirectory() as td:
                mgr = WorktreeManager(Path(td))
                mgr.create("test-wt")
                data = mgr.list_all()
                assert len(data["worktrees"]) == 1
                assert data["worktrees"][0]["name"] == "test-wt"
                assert data["worktrees"][0]["status"] == "active"

    def test_create_with_task_id(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="", stderr=""),
                MagicMock(returncode=0, stdout="", stderr=""),
            ]
            with tempfile.TemporaryDirectory() as td:
                mgr = WorktreeManager(Path(td))
                result = mgr.create("task-wt", task_id="plan_abc")
                assert result["ok"]
                assert result["worktree"]["task_id"] == "plan_abc"

    def test_create_rejects_duplicate(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="", stderr=""),
                MagicMock(returncode=0, stdout="", stderr=""),
            ]
            with tempfile.TemporaryDirectory() as td:
                mgr = WorktreeManager(Path(td))
                mgr.create("dup")
                result = mgr.create("dup")
                assert not result["ok"]
                assert "already exists" in result["error"]

    def test_non_git_repo_returns_error(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = Exception("not a git repo")
            with tempfile.TemporaryDirectory() as td:
                mgr = WorktreeManager(Path(td))
                result = mgr.create("test")
                assert not result["ok"]
                assert "not a git repository" in result["error"]

    def test_status_not_found(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            with tempfile.TemporaryDirectory() as td:
                mgr = WorktreeManager(Path(td))
                result = mgr.status("nonexistent")
                assert not result["ok"]
                assert "not found" in result["error"]

    def test_status_returns_git_output(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="", stderr=""),  # rev-parse
                MagicMock(returncode=0, stdout="", stderr=""),  # worktree add
                MagicMock(returncode=0, stdout="## main\nM file.py", stderr=""),  # status
            ]
            with tempfile.TemporaryDirectory() as td:
                mgr = WorktreeManager(Path(td))
                mgr.create("st-wt")
                result = mgr.status("st-wt")
                assert result["ok"]
                assert "file.py" in result["status_output"]

    def test_run_in_worktree(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="", stderr=""),  # rev-parse
                MagicMock(returncode=0, stdout="", stderr=""),  # worktree add
                MagicMock(returncode=0, stdout="hello", stderr=""),  # command
            ]
            with tempfile.TemporaryDirectory() as td:
                mgr = WorktreeManager(Path(td))
                mgr.create("cmd-wt")
                # git worktree add is mocked, so create the directory manually
                wt_dir = Path(td) / ".jarvis" / "worktrees" / "cmd-wt"
                wt_dir.mkdir(parents=True, exist_ok=True)
                result = mgr.run("cmd-wt", "echo hello")
                assert result["ok"]
                assert result["stdout"] == "hello"

    def test_run_not_found(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            with tempfile.TemporaryDirectory() as td:
                mgr = WorktreeManager(Path(td))
                result = mgr.run("nope", "echo hi")
                assert not result["ok"]
                assert "not found" in result["error"]

    def test_remove_marks_removed(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="", stderr=""),
                MagicMock(returncode=0, stdout="", stderr=""),
                MagicMock(returncode=0, stdout="", stderr=""),  # git worktree remove
            ]
            with tempfile.TemporaryDirectory() as td:
                mgr = WorktreeManager(Path(td))
                mgr.create("rm-wt")
                result = mgr.remove("rm-wt")
                assert result["ok"]
                assert result["worktree"]["status"] == "removed"

    def test_keep_changes_status(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="", stderr=""),
                MagicMock(returncode=0, stdout="", stderr=""),
            ]
            with tempfile.TemporaryDirectory() as td:
                mgr = WorktreeManager(Path(td))
                mgr.create("keep-wt")
                result = mgr.keep("keep-wt")
                assert result["ok"]
                assert result["worktree"]["status"] == "kept"

    def test_events_logged_on_create(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="", stderr=""),
                MagicMock(returncode=0, stdout="", stderr=""),
            ]
            with tempfile.TemporaryDirectory() as td:
                events = EventBus(Path(td) / "events.jsonl")
                mgr = WorktreeManager(Path(td), events=events)
                mgr.create("evt-wt")
                entries = events.list_recent()
                create_events = [e for e in entries if e["event"] in ("worktree.create.before", "worktree.create.after")]
                assert len(create_events) == 2

    def test_events_logged_on_remove(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="", stderr=""),
                MagicMock(returncode=0, stdout="", stderr=""),
                MagicMock(returncode=0, stdout="", stderr=""),
            ]
            with tempfile.TemporaryDirectory() as td:
                events = EventBus(Path(td) / "events.jsonl")
                mgr = WorktreeManager(Path(td), events=events)
                mgr.create("rmv-wt")
                mgr.remove("rmv-wt")
                entries = events.list_recent()
                remove_events = [e for e in entries if e["event"] in ("worktree.remove.before", "worktree.remove.after")]
                assert len(remove_events) == 2

    def test_create_failed_event(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="", stderr=""),
                MagicMock(returncode=1, stdout="", stderr="git error: something"),
            ]
            with tempfile.TemporaryDirectory() as td:
                events = EventBus(Path(td) / "events.jsonl")
                mgr = WorktreeManager(Path(td), events=events)
                result = mgr.create("fail-wt")
                assert not result["ok"]
                entries = events.list_recent()
                failed = [e for e in entries if e["event"] == "worktree.create.failed"]
                assert len(failed) == 1
