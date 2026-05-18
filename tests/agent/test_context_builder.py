from __future__ import annotations

from pathlib import Path

from src.jarvis.agent.context import ContextBuilder
from src.jarvis.agent.store import ThreadStore
from src.jarvis.agent.types import ChatInput
from src.jarvis.skills.registry import SkillRegistry


def test_context_builder_basic(tmp_path: Path):
    store = ThreadStore(root=tmp_path / "threads")
    builder = ContextBuilder(
        session_store=store,
        skill_registry=SkillRegistry(),
        model_info={"model_provider": "fake", "model_name": "fake-agent-v0", "model_backend": "fake"},
    )
    session = store.create_or_resume_session(ChatInput(text="你是什么模型", cwd=str(tmp_path), project_id="p"))
    turn = store.create_turn(session["session_id"])

    turn_context = builder.build(
        session_id=session["session_id"],
        turn_id=turn.turn_id,
        chat_input=ChatInput(text="你是什么模型", cwd=str(tmp_path), project_id="p"),
    )

    assert turn_context.user_input == "你是什么模型"
    assert turn_context.cwd
    assert turn_context.context_pack is not None
    assert turn_context.context_pack.project.cwd


def test_context_builder_project_context_reads_instructions(tmp_path: Path):
    (tmp_path / "README.md").write_text("# Demo\nhello", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("Be careful.", encoding="utf-8")
    store = ThreadStore(root=tmp_path / "threads")
    builder = ContextBuilder(session_store=store, skill_registry=SkillRegistry())
    session = store.create_or_resume_session(ChatInput(text="hi", cwd=str(tmp_path), project_id="p"))
    turn = store.create_turn(session["session_id"])

    turn_context = builder.build(
        session_id=session["session_id"],
        turn_id=turn.turn_id,
        chat_input=ChatInput(text="hi", cwd=str(tmp_path), project_id="p"),
    )

    project = turn_context.context_pack.project
    assert "README.md" in project.project_files_hint
    assert project.project_instructions

