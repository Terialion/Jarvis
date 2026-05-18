"""Tests for background task notification auto-injection (s08)."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.jarvis.core.background import BackgroundTaskManager
from src.jarvis.agent.types import ChatInput


class TestBackgroundNotifications:
    def test_drain_returns_completed_task(self):
        mgr = BackgroundTaskManager(max_workers=2)

        def _fast_work():
            return "done"

        tid = mgr.submit("fast task", _fast_work)
        # Wait for completion
        mgr.check_blocking(tid, timeout=5)
        notifs = mgr.drain_notifications()
        assert len(notifs) == 1
        assert notifs[0]["task_id"] == tid
        assert notifs[0]["status"] == "completed"
        assert notifs[0]["result"] == "done"

    def test_drain_clears_queue(self):
        mgr = BackgroundTaskManager(max_workers=2)
        tid = mgr.submit("quick", lambda: "ok")
        mgr.check_blocking(tid, timeout=5)
        mgr.drain_notifications()
        notifs = mgr.drain_notifications()
        assert notifs == []

    def test_drain_includes_failures(self):
        mgr = BackgroundTaskManager(max_workers=2)

        def _failing():
            raise RuntimeError("boom")

        tid = mgr.submit("failing", _failing)
        mgr.check_blocking(tid, timeout=5)
        notifs = mgr.drain_notifications()
        assert len(notifs) == 1
        assert notifs[0]["status"] == "failed"
        assert notifs[0]["error"] == "boom"

    def test_drain_returns_empty_when_no_tasks(self):
        mgr = BackgroundTaskManager(max_workers=2)
        assert mgr.drain_notifications() == []

    def test_agent_loop_injects_notifications(self, monkeypatch):
        """Verify AgentLoop injects <background-results> when bg tasks complete."""
        from src.jarvis.agent import loop as loop_mod

        bg_mgr = BackgroundTaskManager(max_workers=2)
        tid = bg_mgr.submit("pre-completed", lambda: "ready")
        bg_mgr.check_blocking(tid, timeout=5)

        # Build a MagicMock-based tool registry that has the real bg_task_manager
        tool_registry = MagicMock()
        tool_registry.bg_task_manager = bg_mgr
        tool_registry.permission_mode = "workspace_write"
        tool_registry.message_bus.read_inbox.return_value = []  # no team inbox messages

        model_client = MagicMock()
        model_client.backend_info.return_value = {
            "model_backend": "mock", "model_provider": "mock", "model_name": "mock",
        }
        model_client.complete.return_value = MagicMock(
            content=[{"type": "text", "text": "bg_injected=True"}],
            final_answer="bg_injected=True",
            finish_reason="stop",
            tool_calls=[],
            assistant_text="bg_injected=True",
            reasoning_summary=None,
            usage={"input_tokens": 10, "output_tokens": 5},
        )
        model_client.complete_stream.return_value = iter([])

        loop = loop_mod.AgentLoop(
            project_root=".",
            model_client=model_client,
            tool_registry=tool_registry,
            max_steps=1,
            timeout_s=30,
        )

        result = loop.run_turn(
            ChatInput(
                text="hello",
                cwd=".",
                session_id="test_bg",
                metadata={"source": "test", "mode": "default"},
            )
        )

        assert result.ok
        assert "bg_injected=True" in str(result.final_answer)


class TestBackgroundManagerEdgeCases:
    def test_notification_result_truncated(self):
        mgr = BackgroundTaskManager(max_workers=2)
        long_result = "x" * 3000

        tid = mgr.submit("long output", lambda: long_result)
        mgr.check_blocking(tid, timeout=5)
        notifs = mgr.drain_notifications()
        assert len(notifs[0]["result"]) <= 2000
