from __future__ import annotations

from pathlib import Path

from src.jarvis.agent.loop import AgentLoop
from src.jarvis.agent.model import FakeModelClient
from src.jarvis.agent.types import ChatInput, ModelResponse, ToolCall


def test_agent_loop_smoke_no_tool(tmp_path: Path):
    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(
            scripted=[
                ModelResponse(
                    assistant_text="hello",
                    final_answer="hello",
                    finish_reason="stop",
                )
            ]
        ),
        auto_approve=True,
    )
    result = loop.run_turn(ChatInput(text="hi", cwd=str(tmp_path), project_id="p"))
    assert result.ok is True
    assert result.final_answer == "hello"
    assert result.stop_reason == "completed"
    assert result.events


def test_agent_loop_tool_call_then_final(tmp_path: Path):
    readme = tmp_path / "README.md"
    readme.write_text("hello world", encoding="utf-8")

    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(
            scripted=[
                ModelResponse(
                    reasoning_summary="need read file",
                    tool_calls=[ToolCall.new(name="repo_reader.read_file", arguments={"path": str(readme)})],
                    finish_reason="tool_calls",
                ),
                ModelResponse(
                    assistant_text="read complete",
                    final_answer="read complete",
                    finish_reason="stop",
                ),
            ]
        ),
        auto_approve=True,
    )
    result = loop.run_turn(ChatInput(text="read file", cwd=str(tmp_path), project_id="p2"))
    assert result.ok is True
    assert result.final_answer == "read complete"
    assert len(result.tool_calls) >= 1
    assert len(result.tool_results) >= 1

