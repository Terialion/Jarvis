from __future__ import annotations

from pathlib import Path

from src.jarvis.agent.loop import AgentLoop
from src.jarvis.agent.model import FakeModelClient
from src.jarvis.agent.store import ThreadStore
from src.jarvis.agent.types import ChatInput, ModelResponse, ToolCall


def test_agentloop_invokes_summarize_file_skill(tmp_path: Path):
    (tmp_path / "README.md").write_text("# Demo\n\nA small Jarvis test repo.", encoding="utf-8")
    loop = AgentLoop(project_root=str(tmp_path), store=ThreadStore(root=tmp_path / "threads"), auto_approve=True)

    result = loop.run_turn(ChatInput(text="总结 README.md", cwd=str(tmp_path), project_id="p", session_id="s"))

    assert result.output_type in {"answer", "tool_result"}
    assert result.skills_used == ["summarize_file"]
    assert result.skill_calls_count == 1
    assert any(call.get("name") == "repo_reader.read_file" for call in result.tool_calls)
    assert "README.md" in str(result.skill_results)
    assert {"skill_call_started", "skill_step_started", "skill_call_completed"}.issubset(
        {str(event.get("type") or "") for event in result.events}
    )


def test_agentloop_invokes_repo_overview_skill_without_file_modification(tmp_path: Path):
    (tmp_path / "README.md").write_text("# Demo\n\nA repository overview target.", encoding="utf-8")
    loop = AgentLoop(project_root=str(tmp_path), store=ThreadStore(root=tmp_path / "threads"), auto_approve=True)

    result = loop.run_turn(ChatInput(text="给我看一下这个项目是做什么的", cwd=str(tmp_path), project_id="p", session_id="s"))

    assert result.skills_used == ["repo_overview"]
    assert result.skill_calls_count == 1
    assert "Project overview" in result.final_answer
    assert not any(call.get("name") == "file_editor.replace_text" for call in result.tool_calls)


def test_agentloop_fix_test_failure_is_dry_run(tmp_path: Path):
    loop = AgentLoop(project_root=str(tmp_path), store=ThreadStore(root=tmp_path / "threads"), auto_approve=True)

    result = loop.run_turn(ChatInput(text="修复测试失败", cwd=str(tmp_path), project_id="p", session_id="s"))

    assert result.skills_used == ["fix_test_failure"]
    assert result.skill_calls_count == 1
    assert result.output_type == "partial"
    assert "Dry-run repair plan" in result.final_answer
    assert not any(call.get("name") == "file_editor.replace_text" for call in result.tool_calls)
    assert "approval_required_for_edit" in str(result.summary["machine"].get("risks") or [])


def test_model_skill_run_tool_call_uses_skill_executor(tmp_path: Path):
    (tmp_path / "README.md").write_text("# Demo\n\nModel-invoked skill.", encoding="utf-8")
    loop = AgentLoop(
        project_root=str(tmp_path),
        store=ThreadStore(root=tmp_path / "threads"),
        model_client=FakeModelClient(
            scripted=[
                ModelResponse(
                    tool_calls=[
                        ToolCall.new(
                            name="skill.run",
                            arguments={"name": "summarize_file", "arguments": {"path": "README.md"}},
                        )
                    ],
                    finish_reason="tool_calls",
                ),
                ModelResponse(final_answer="Used summarize_file.", finish_reason="stop"),
            ]
        ),
        auto_approve=True,
    )

    result = loop.run_turn(ChatInput(text="Use skill.run for README", cwd=str(tmp_path), project_id="p", session_id="s"))

    assert result.skills_used == ["summarize_file"]
    assert result.skill_calls_count == 1
    assert any(call.get("name") == "skill.run" for call in result.tool_calls)
    assert any(call.get("name") == "repo_reader.read_file" for call in result.tool_calls)
    assert "skill_call_completed" in {str(event.get("type") or "") for event in result.events}
