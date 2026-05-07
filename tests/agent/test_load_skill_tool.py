from __future__ import annotations

from pathlib import Path

from src.jarvis.agent.loop import AgentLoop
from src.jarvis.agent.model import FakeModelClient
from src.jarvis.agent.tools import ToolCallExecutor, ToolRegistryAdapter
from src.jarvis.agent.types import ChatInput, ModelResponse, ToolCall


def test_load_skill_tool_returns_full_body(tmp_path: Path):
    registry = ToolRegistryAdapter(project_root=str(tmp_path))
    executor = ToolCallExecutor(registry_adapter=registry, auto_approve=True)
    result = executor.execute(
        ToolCall.new(name="skill.load", arguments={"name": "summarize_file"}),
        context={"cwd": str(tmp_path)},
    )
    assert result.ok is True
    assert "<skill name=\"summarize_file\"" in str(result.content)
    assert "# When to use" in str(result.content)
    assert "# Workflow" in str(result.content)


def test_load_skill_missing_returns_error(tmp_path: Path):
    registry = ToolRegistryAdapter(project_root=str(tmp_path))
    executor = ToolCallExecutor(registry_adapter=registry, auto_approve=True)
    result = executor.execute(
        ToolCall.new(name="skill.load", arguments={"name": "missing_skill"}),
        context={"cwd": str(tmp_path)},
    )
    assert result.ok is False
    assert "skill_not_found" in str(result.error)


def test_duplicate_skill_load_same_turn_reuses_observation(tmp_path: Path):
    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(
            scripted=[
                ModelResponse(
                    tool_calls=[ToolCall.new(name="skill.load", arguments={"name": "summarize_file"})],
                    finish_reason="tool_calls",
                ),
                ModelResponse(
                    tool_calls=[ToolCall.new(name="skill.load", arguments={"name": "summarize_file"})],
                    finish_reason="tool_calls",
                ),
                ModelResponse(final_answer="Loaded once.", finish_reason="stop"),
            ]
        ),
        auto_approve=True,
    )
    result = loop.run_turn(ChatInput(text="Use summarize_file skill", cwd=str(tmp_path), project_id="p"))

    assert result.loaded_skills == ["summarize_file"]
    assert result.skill_loads_count == 1
    event_types = [str(event.get("type") or "") for event in result.events]
    assert "skill_loaded" in event_types
    assert "skill_observation_reused" in event_types
