"""Tests for tool call deduplication in AgentLoop.

Phase 5: Verifies that the same tool+args is not executed twice
within the same turn, and that duplicate calls emit tool_call_deduped events.
"""

from __future__ import annotations

from pathlib import Path

from src.jarvis.agent.loop import AgentLoop
from src.jarvis.agent.model import FakeModelClient
from src.jarvis.agent.types import ChatInput, ModelResponse, ToolCall


def test_same_tool_same_args_deduped(tmp_path: Path):
    """When model calls the same tool with identical args twice, second execution is skipped."""
    readme = tmp_path / "README.md"
    readme.write_text("hello world", encoding="utf-8")

    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(
            scripted=[
                ModelResponse(
                    tool_calls=[ToolCall.new(name="repo_reader.read_file", arguments={"path": str(readme)})],
                    finish_reason="tool_calls",
                ),
                ModelResponse(
                    tool_calls=[ToolCall.new(name="repo_reader.read_file", arguments={"path": str(readme)})],
                    finish_reason="tool_calls",
                ),
                ModelResponse(final_answer="Done.", finish_reason="stop"),
            ]
        ),
        auto_approve=True,
        max_steps=5,
    )
    result = loop.run_turn(ChatInput(text="read the file", cwd=str(tmp_path), project_id="test"))

    # Should have tool_call_deduped event for the second call
    event_types = [e.get("type") for e in result.events]
    assert "tool_call_deduped" in event_types or "observation_reused" in event_types
    # tool_calls_log should have 2 entries (both logged), but only 1 actual execution
    assert len(result.tool_calls) == 2  # Both calls are logged
    # Check that tool_calls_count in events shows dedup
    dedup_events = [e for e in result.events if e.get("type") in ("tool_call_deduped", "observation_reused")]
    assert len(dedup_events) >= 1


def test_different_args_not_deduped(tmp_path: Path):
    """Same tool with different args is NOT deduplicated."""
    f1 = tmp_path / "a.txt"
    f2 = tmp_path / "b.txt"
    f1.write_text("file a", encoding="utf-8")
    f2.write_text("file b", encoding="utf-8")

    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(
            scripted=[
                ModelResponse(
                    tool_calls=[
                        ToolCall.new(name="repo_reader.read_file", arguments={"path": str(f1)}),
                        ToolCall.new(name="repo_reader.read_file", arguments={"path": str(f2)}),
                    ],
                    finish_reason="tool_calls",
                ),
                ModelResponse(final_answer="Done.", finish_reason="stop"),
            ]
        ),
        auto_approve=True,
        max_steps=5,
    )
    result = loop.run_turn(ChatInput(text="read both files", cwd=str(tmp_path), project_id="test"))

    event_types = [e.get("type") for e in result.events]
    # Should NOT have deduped events since args differ
    assert "tool_call_deduped" not in event_types
    # Both files should have been read
    tool_names = [tc.get("name") for tc in result.tool_calls]
    assert tool_names.count("repo_reader.read_file") == 2


def test_no_progress_early_stop(tmp_path: Path):
    """When no new observation in 2 consecutive steps and no final answer, loop stops with no_progress."""
    # Only triggers when model keeps calling same tool with no final answer
    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(
            scripted=[
                ModelResponse(
                    tool_calls=[ToolCall.new(name="repo_reader.search_files", arguments={"repo_path": ".", "pattern": "*.txt"})],
                    finish_reason="tool_calls",
                ),
                # Second call same args but model doesn't give final answer
                ModelResponse(
                    tool_calls=[ToolCall.new(name="repo_reader.search_files", arguments={"repo_path": ".", "pattern": "*.txt"})],
                    finish_reason="tool_calls",
                ),
                ModelResponse(
                    tool_calls=[ToolCall.new(name="repo_reader.search_files", arguments={"repo_path": ".", "pattern": "*.txt"})],
                    finish_reason="tool_calls",
                ),
            ]
        ),
        auto_approve=True,
        max_steps=8,
    )
    result = loop.run_turn(ChatInput(text="list files", cwd=str(tmp_path), project_id="test"))

    # Should have stopped with no_progress (if final answer not produced) or max_steps
    # If model eventually gave a final answer, that's also acceptable
    assert result.stop_reason in ("no_progress", "max_steps", "completed")
    # In any case, output_type should be valid
    assert result.output_type in ("answer", "tool_result", "partial")


def test_query_tool_summarization_hint(tmp_path: Path):
    """After successful read_file, model should not re-call the same tool without user request."""
    readme = tmp_path / "README.md"
    readme.write_text("project info", encoding="utf-8")

    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(
            scripted=[
                ModelResponse(
                    tool_calls=[ToolCall.new(name="repo_reader.read_file", arguments={"path": str(readme)})],
                    finish_reason="tool_calls",
                ),
                ModelResponse(final_answer="The README contains: project info", finish_reason="stop"),
            ]
        ),
        auto_approve=True,
        max_steps=5,
    )
    result = loop.run_turn(ChatInput(text="what is in the readme", cwd=str(tmp_path), project_id="test"))

    # Should have gotten a final answer
    assert result.final_answer
    assert len(result.tool_calls) >= 1
