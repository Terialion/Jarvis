"""Tests for interactive natural-language task input behavior."""

from __future__ import annotations

from types import SimpleNamespace

from jarvis import cli as cli_mod


def test_english_repo_inspection_is_not_task(monkeypatch):
    class _DummyLoop:
        def __init__(self, *args, **kwargs):
            pass

        def run_turn(self, chat_input):
            return SimpleNamespace(
                ok=True,
                final_answer="Repository inspection summary.",
                stop_reason="completed",
                status="completed",
                output_type="tool_result",
                tool_calls=[{"name": "repo_reader.search_files", "arguments": {"pattern": "*"}}],
                events=[],
                summary={"machine": {"outcome": "completed", "tools_used": ["repo_reader.search_files"], "risks": []}},
            )

    monkeypatch.setattr("jarvis.agent.loop.AgentLoop", _DummyLoop)
    output = cli_mod.run_agent_turn_for_cli("Inspect this repo", output_mode="default")
    assert "Task task_" not in output
    assert "Repository inspection summary." in output
    assert "Traceback" not in output
