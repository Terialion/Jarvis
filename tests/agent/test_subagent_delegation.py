from __future__ import annotations

from pathlib import Path

from src.jarvis.agent.loop import AgentLoop
from src.jarvis.agent.model import FakeModelClient, ModelResponse
from src.jarvis.agent.store import ThreadStore
from src.jarvis.agent.types import ChatInput, ToolCall


def test_agentloop_delegates_subtask_via_task_delegate(tmp_path: Path):
    """LLM calls task.delegate to research a file; sub-agent runs and returns result."""
    (tmp_path / "README.md").write_text("# Test Project\n\nA test repository.", encoding="utf-8")

    loop = AgentLoop(
        project_root=str(tmp_path),
        store=ThreadStore(root=tmp_path / "threads"),
        model_client=FakeModelClient(scripted=[
            ModelResponse(
                tool_calls=[
                    ToolCall.new(
                        name="task.delegate",
                        arguments={
                            "task": "Read and summarize README.md",
                            "budget_steps": 2,
                        },
                    )
                ],
                finish_reason="tool_calls",
            ),
            ModelResponse(
                assistant_text="The sub-agent found that this is a test project repository.",
                final_answer="The sub-agent found that this is a test project repository.",
                finish_reason="stop",
            ),
        ]),
        auto_approve=True,
    )

    result = loop.run_turn(
        ChatInput(text="Research the README", cwd=str(tmp_path), project_id="p", session_id="s")
    )

    assert result.output_type in {"answer", "tool_result"}
    assert result.ok is True
    assert any(call.get("name") == "task.delegate" for call in result.tool_calls)


def test_task_delegate_returns_error_for_empty_task(tmp_path: Path):
    """task.delegate with empty task should return an error."""
    loop = AgentLoop(
        project_root=str(tmp_path),
        store=ThreadStore(root=tmp_path / "threads"),
        model_client=FakeModelClient(scripted=[
            ModelResponse(
                tool_calls=[
                    ToolCall.new(
                        name="task.delegate",
                        arguments={"task": ""},
                    )
                ],
                finish_reason="tool_calls",
            ),
        ]),
        auto_approve=True,
    )

    result = loop.run_turn(
        ChatInput(text="Delegate something", cwd=str(tmp_path), project_id="p", session_id="s")
    )

    assert any(
        call.get("name") == "task.delegate" for call in result.tool_calls
    )
    # Should have an error observation for the failed delegation
    observation_texts = [
        str(r.get("content") or "")
        for r in result.tool_results
        if r.get("name") == "task.delegate"
    ]
    assert any("requires a non-empty" in str(t) for t in observation_texts) or any(
        not r.get("ok") for r in result.tool_results if r.get("name") == "task.delegate"
    )


def test_subagent_runner_with_fake_model_client(tmp_path: Path):
    """SubagentRunner runs a real AgentLoop when given a FakeModelClient."""
    from src.jarvis.core.subagents.models import SubagentRun
    from src.jarvis.core.subagents.runner import SubagentRunner
    from src.jarvis.agent.tools import ToolRegistryAdapter

    (tmp_path / "README.md").write_text("# Test\n\nContent.", encoding="utf-8")

    registry = ToolRegistryAdapter(project_root=str(tmp_path))
    model_client = FakeModelClient()
    runner = SubagentRunner(
        project_root=str(tmp_path),
        model_client=model_client,
        tool_registry=registry,
    )

    result = runner.run_subtask(
        SubagentRun(
            subagent_id="test_sub",
            parent_run_id="test_parent",
            task="hello",
            budget_steps=2,
        )
    )

    assert result["status"] == "completed"
    assert "final_answer" in result["result"]
    assert len(result["trace"]) > 0
