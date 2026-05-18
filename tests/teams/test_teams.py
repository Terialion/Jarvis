"""Tests for agent teams — MessageBus and TeammateManager (s09)."""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.jarvis.core.teams import MessageBus, TeammateManager


@pytest.fixture
def inbox_dir():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        yield Path(td)


@pytest.fixture
def bus(inbox_dir):
    return MessageBus(inbox_dir=inbox_dir)


@pytest.fixture
def team_dir():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        yield Path(td)


class TestMessageBus:
    def test_send_and_read(self, bus):
        bus.send("lead", "alice", "Hello, review this code.")
        msgs = bus.read_inbox("alice")
        assert len(msgs) == 1
        assert msgs[0]["from"] == "lead"
        assert msgs[0]["content"] == "Hello, review this code."
        assert msgs[0]["type"] == "message"

    def test_read_drains_inbox(self, bus):
        bus.send("lead", "alice", "msg1")
        bus.send("lead", "alice", "msg2")
        msgs = bus.read_inbox("alice")
        assert len(msgs) == 2
        # Second read should be empty
        assert bus.read_inbox("alice") == []

    def test_broadcast(self, bus):
        bus.send("lead", "alice", "ignore")  # ensure inbox exists
        bus.send("lead", "bob", "ignore")
        result = bus.broadcast("lead", "status update", ["alice", "bob"])
        assert result["ok"]
        assert "alice" in result["sent_to"]
        assert "bob" in result["sent_to"]

    def test_read_nonexistent_inbox(self, bus):
        assert bus.read_inbox("ghost") == []

    def test_invalid_msg_type_rejected(self, bus):
        result = bus.send("lead", "alice", "test", msg_type="bad_type")
        assert not result["ok"]

    def test_extra_fields(self, bus):
        bus.send("lead", "alice", "plan", extra={"request_id": "abc123", "approve": True})
        msgs = bus.read_inbox("alice")
        assert msgs[0]["request_id"] == "abc123"
        assert msgs[0]["approve"] is True


class TestTeammateManager:
    def test_spawn_and_list(self, team_dir, inbox_dir):
        bus = MessageBus(inbox_dir=inbox_dir)
        mgr = TeammateManager(team_dir=team_dir, bus=bus)

        mgr.spawn("alice", "coder", "Write tests for auth module.")
        members = mgr.list_all()
        assert any(m["name"] == "alice" for m in members)
        assert any(m["role"] == "coder" for m in members)

    def test_config_persistence(self, team_dir, inbox_dir):
        bus = MessageBus(inbox_dir=inbox_dir)
        mgr1 = TeammateManager(team_dir=team_dir, bus=bus)
        mgr1.spawn("bob", "tester", "Run integration tests.")

        # New instance loads from disk
        bus2 = MessageBus(inbox_dir=inbox_dir)
        mgr2 = TeammateManager(team_dir=team_dir, bus=bus2)
        members = mgr2.list_all()
        assert any(m["name"] == "bob" for m in members)

    def test_member_names(self, team_dir, inbox_dir):
        bus = MessageBus(inbox_dir=inbox_dir)
        mgr = TeammateManager(team_dir=team_dir, bus=bus)
        mgr.spawn("alice", "coder", "task1")
        mgr.spawn("bob", "tester", "task2")
        names = mgr.member_names()
        assert "alice" in names
        assert "bob" in names

    def test_spawn_updates_existing(self, team_dir, inbox_dir):
        bus = MessageBus(inbox_dir=inbox_dir)
        mgr = TeammateManager(team_dir=team_dir, bus=bus)
        mgr.spawn("alice", "coder", "task1")
        mgr.spawn("alice", "reviewer", "task2")
        members = mgr.list_all()
        alice = next(m for m in members if m["name"] == "alice")
        assert alice["role"] == "reviewer"

    def test_no_model_client_sets_idle(self, team_dir, inbox_dir):
        bus = MessageBus(inbox_dir=inbox_dir)
        mgr = TeammateManager(team_dir=team_dir, bus=bus)
        mgr.spawn("alice", "coder", "task")
        time.sleep(0.2)  # let thread start and exit
        members = mgr.list_all()
        alice = next(m for m in members if m["name"] == "alice")
        assert alice["status"] in ("idle", "shutdown")


class TestTeammateManagerWithMockLLM:
    def test_teammate_processes_inbox(self, team_dir, inbox_dir):
        """Teammate reads inbox messages during its loop."""
        from src.jarvis.agent.types import ModelResponse, ToolCall

        bus = MessageBus(inbox_dir=inbox_dir)

        call_count = [0]

        def fake_client_factory():
            client = MagicMock()
            # First call: return tool call (send_message), second: stop
            def complete_side_effect(messages, tools=None):
                call_count[0] += 1
                if call_count[0] == 1:
                    return ModelResponse(
                        finish_reason="tool_use",
                        tool_calls=[ToolCall(
                            id="tc1", name="send_message",
                            arguments={"to": "lead", "content": "I reviewed the code."},
                        )],
                    )
                return ModelResponse(
                    finish_reason="stop",
                    assistant_text="Task complete.",
                    final_answer="Task complete.",
                )
            client.complete = MagicMock(side_effect=complete_side_effect)
            return client

        mgr = TeammateManager(
            team_dir=team_dir, bus=bus,
            model_client_factory=fake_client_factory,
        )
        mgr.spawn("alice", "coder", "Review app.py")

        time.sleep(0.3)  # let teammate run

        # Teammate should have sent a message back to lead
        lead_msgs = bus.read_inbox("lead")
        assert any(
            "I reviewed the code" in str(m.get("content", ""))
            for m in lead_msgs
        )

    def test_teammate_responds_to_shutdown(self, team_dir, inbox_dir):
        from src.jarvis.agent.types import ModelResponse

        bus = MessageBus(inbox_dir=inbox_dir)

        call_count = [0]

        def fake_client_factory():
            client = MagicMock()
            def complete_side_effect(messages, tools=None):
                call_count[0] += 1
                # Check if shutdown was received
                for m in messages:
                    content = str(m.get("content", ""))
                    if "shutdown_request" in content:
                        return ModelResponse(finish_reason="stop", final_answer="Shutting down.")
                if call_count[0] <= 2:
                    return ModelResponse(finish_reason="stop", final_answer="Working...")
                return ModelResponse(finish_reason="stop", final_answer="Done.")
            client.complete = MagicMock(side_effect=complete_side_effect)
            return client

        mgr = TeammateManager(
            team_dir=team_dir, bus=bus,
            model_client_factory=fake_client_factory,
        )
        mgr.spawn("alice", "coder", "Work on a task")

        time.sleep(0.2)
        # Send shutdown to alice
        bus.send("lead", "alice", "Please shut down.", msg_type="shutdown_request")

        time.sleep(0.3)
        members = mgr.list_all()
        alice = next(m for m in members if m["name"] == "alice")
        assert alice["status"] in ("idle", "shutdown")
