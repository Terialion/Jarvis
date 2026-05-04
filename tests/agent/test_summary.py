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

