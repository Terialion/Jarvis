from __future__ import annotations

from pathlib import Path

from src.jarvis.agent.loop import AgentLoop
from src.jarvis.agent.model import FakeModelClient
from src.jarvis.agent.store import ThreadStore
from src.jarvis.agent.types import ChatInput, ModelResponse, ToolCall


def _summarize_skill_script():
    """Scripted responses: call summarize_file skill then stop."""
    return [
        ModelResponse(
            tool_calls=[
                ToolCall.new(
                    name="skill.run",
                    arguments={"name": "summarize_file", "arguments": {"path": "README.md"}},
                )
            ],
            finish_reason="tool_calls",
        ),
        ModelResponse(final_answer="README.md summarizes the project.", finish_reason="stop"),
    ]


def _repo_overview_script():
    """Scripted responses: call repo_overview skill then stop."""
    return [
        ModelResponse(
            tool_calls=[
                ToolCall.new(
                    name="skill.run",
                    arguments={"name": "repo_overview", "arguments": {"root": "."}},
                )
            ],
            finish_reason="tool_calls",
        ),
        ModelResponse(final_answer="Project overview: a demo repository.", finish_reason="stop"),
    ]


def test_skill_result_writes_observation_and_handoff_summary(tmp_path: Path):
    (tmp_path / "README.md").write_text("# Demo\n\nContext write-back target.", encoding="utf-8")
    loop = AgentLoop(
        project_root=str(tmp_path),
        store=ThreadStore(root=tmp_path / "threads"),
        model_client=FakeModelClient(scripted=_summarize_skill_script()),
        auto_approve=True,
    )

    result = loop.run_turn(ChatInput(text="总结 README.md", cwd=str(tmp_path), project_id="p", session_id="ctx"))

    stored = loop.context_store.retrieve_skill_observation("ctx", skill_name="summarize_file")
    assert stored is not None
    assert stored.skill_name == "summarize_file"
    assert "README.md" in stored.related_files
    machine = result.summary["machine"]
    assert machine["active_task"]["skills_used"] == ["summarize_file"]
    assert "remaining_work" in machine["handoff_summary"]
    assert machine["skill_observations"]


def test_multi_turn_reference_reuses_previous_skill_observation(tmp_path: Path):
    (tmp_path / "README.md").write_text("# Demo\n\nPrevious file reference target.", encoding="utf-8")
    loop = AgentLoop(
        project_root=str(tmp_path),
        store=ThreadStore(root=tmp_path / "threads"),
        model_client=FakeModelClient(
            scripted=_summarize_skill_script()
            + [
                ModelResponse(
                    assistant_text="README.md 是项目的说明文档。",
                    final_answer="README.md 是项目的说明文档。",
                    finish_reason="stop",
                ),
            ]
        ),
        auto_approve=True,
    )

    loop.run_turn(ChatInput(text="总结 README.md", cwd=str(tmp_path), project_id="p", session_id="ctx"))
    followup = loop.run_turn(ChatInput(text="刚才那个文件主要讲什么？", cwd=str(tmp_path), project_id="p", session_id="ctx"))

    assert followup.output_type == "answer"
    assert followup.summary["machine"]["context_reuse"] is True
    assert "README.md" in followup.final_answer
    assert "context_observation_reused" in {str(event.get("type") or "") for event in followup.events}


def test_project_overview_observation_reuse(tmp_path: Path):
    (tmp_path / "README.md").write_text("# Demo\n\nProject facts.", encoding="utf-8")
    loop = AgentLoop(
        project_root=str(tmp_path),
        store=ThreadStore(root=tmp_path / "threads"),
        model_client=FakeModelClient(
            scripted=_repo_overview_script()
            + [
                ModelResponse(
                    assistant_text="基于项目结构，建议添加测试和文档。",
                    final_answer="基于项目结构，建议添加测试和文档。",
                    finish_reason="stop",
                ),
            ]
        ),
        auto_approve=True,
    )

    loop.run_turn(ChatInput(text="分析项目结构", cwd=str(tmp_path), project_id="p", session_id="ctx"))
    followup = loop.run_turn(ChatInput(text="基于刚才的项目结构给我下一步建议", cwd=str(tmp_path), project_id="p", session_id="ctx"))

    assert followup.summary["machine"]["context_reuse"] is True
    assert "context_observation_reused" in {str(event.get("type") or "") for event in followup.events}
    assert not followup.skills_used
