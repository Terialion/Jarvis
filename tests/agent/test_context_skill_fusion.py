from __future__ import annotations

from pathlib import Path

from src.jarvis.agent.loop import AgentLoop
from src.jarvis.agent.store import ThreadStore
from src.jarvis.agent.types import ChatInput


def test_skill_result_writes_observation_and_handoff_summary(tmp_path: Path):
    (tmp_path / "README.md").write_text("# Demo\n\nContext write-back target.", encoding="utf-8")
    loop = AgentLoop(project_root=str(tmp_path), store=ThreadStore(root=tmp_path / "threads"), auto_approve=True)

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
    loop = AgentLoop(project_root=str(tmp_path), store=ThreadStore(root=tmp_path / "threads"), auto_approve=True)

    loop.run_turn(ChatInput(text="总结 README.md", cwd=str(tmp_path), project_id="p", session_id="ctx"))
    followup = loop.run_turn(ChatInput(text="刚才那个文件主要讲什么？", cwd=str(tmp_path), project_id="p", session_id="ctx"))

    assert followup.output_type == "answer"
    assert followup.summary["machine"]["context_reuse"] is True
    assert "README.md" in followup.final_answer
    assert "context_observation_reused" in {str(event.get("type") or "") for event in followup.events}


def test_project_overview_observation_reuse(tmp_path: Path):
    (tmp_path / "README.md").write_text("# Demo\n\nProject facts.", encoding="utf-8")
    loop = AgentLoop(project_root=str(tmp_path), store=ThreadStore(root=tmp_path / "threads"), auto_approve=True)

    loop.run_turn(ChatInput(text="分析项目结构", cwd=str(tmp_path), project_id="p", session_id="ctx"))
    followup = loop.run_turn(ChatInput(text="基于刚才的项目结构给我下一步建议", cwd=str(tmp_path), project_id="p", session_id="ctx"))

    assert followup.summary["machine"]["context_reuse"] is True
    assert "context_observation_reused" in {str(event.get("type") or "") for event in followup.events}
    assert not followup.skills_used
