from __future__ import annotations

from src.jarvis.agent.summary import ResponseComposer
from src.jarvis.agent.types import ToolResult


def test_response_composer_outputs_human_and_machine():
    composer = ResponseComposer()
    summary = composer.compose(
        final_answer="done",
        tool_results=[
            ToolResult(
                call_id="c1",
                name="command_runner.run",
                ok=True,
                metadata={"commands_run": ["pytest -q"]},
            ),
            ToolResult(
                call_id="c2",
                name="file_editor.replace_text",
                ok=False,
                error="approval_required",
                metadata={"changed_files": ["a.py"]},
            ),
        ],
        stop_reason="approval_required",
    )
    assert "human" in summary
    assert "machine" in summary
    assert summary["machine"]["outcome"] in {"partial", "completed", "failed"}
    assert "command_runner.run" in summary["machine"]["tools_used"]


def test_accumulated_context_empty_when_no_previous_summaries():
    composer = ResponseComposer()
    summary = composer.compose(
        final_answer="done",
        tool_results=[],
        stop_reason="completed",
    )
    assert summary["machine"]["accumulated_context"] == []


def test_accumulated_context_carries_forward_cross_turn_facts():
    composer = ResponseComposer()
    previous = [
        {
            "summary": {
                "human": "Earlier work",
                "machine": {
                    "outcome": "completed",
                    "handoff_summary": {
                        "user_goal": "Fix the login bug",
                        "modified_files": ["auth.py", "login.py"],
                        "completed_work": ["Called Grep for auth module", "Edited auth.py"],
                    },
                    "accumulated_context": [],
                },
            }
        }
    ]
    summary = composer.compose(
        final_answer="done",
        tool_results=[],
        stop_reason="completed",
        previous_summaries=previous,
    )
    acc = summary["machine"]["accumulated_context"]
    assert len(acc) >= 2  # goal + at least 1 file
    goals = [f for f in acc if f["kind"] == "goal"]
    files = [f for f in acc if f["kind"] == "file"]
    assert any("login bug" in g["text"] for g in goals)
    assert any("auth.py" in f["text"] for f in files)


def test_accumulated_context_deduplicates_across_summaries():
    composer = ResponseComposer()
    previous = [
        {
            "summary": {
                "machine": {
                    "handoff_summary": {
                        "user_goal": "Fix login bug",
                        "modified_files": ["auth.py"],
                    },
                    "accumulated_context": [
                        {"kind": "goal", "text": "Fix login bug"},
                    ],
                },
            }
        }
    ]
    summary = composer.compose(
        final_answer="done",
        tool_results=[],
        stop_reason="completed",
        previous_summaries=previous,
    )
    acc = summary["machine"]["accumulated_context"]
    # "Fix login bug" goal should appear only once despite being in both
    # handoff_summary and accumulated_context
    goals = [f for f in acc if f["kind"] == "goal" and f["text"] == "Fix login bug"]
    assert len(goals) == 1

