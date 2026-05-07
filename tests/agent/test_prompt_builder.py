from __future__ import annotations

from pathlib import Path

from src.jarvis.agent.context import ContextBuilder
from src.jarvis.agent.prompt_builder import PromptBuilder
from src.jarvis.agent.store import ThreadStore
from src.jarvis.agent.types import ChatInput
from src.jarvis.skills.registry import SkillRegistry


def test_prompt_builder_includes_recent_messages(tmp_path: Path):
    store = ThreadStore(root=tmp_path / "threads")
    session = store.create_or_resume_session(ChatInput(text="hello", cwd=str(tmp_path), project_id="p"))
    turn = store.create_turn(session["session_id"])
    store.append_message(session["session_id"], turn.turn_id, "assistant", "previous answer")
    builder = ContextBuilder(thread_store=store, skill_registry=SkillRegistry())
    prompt_builder = PromptBuilder()

    turn_context = builder.build(
        session_id=session["session_id"],
        turn_id=turn.turn_id,
        chat_input=ChatInput(text="new question", cwd=str(tmp_path), project_id="p"),
    )
    messages = prompt_builder.build_messages(turn_context)

    assert any(str(row.get("content") or "") == "previous answer" for row in messages)
    assert messages[-1]["content"] == "new question"


def test_prompt_builder_includes_skill_metadata_not_full_body(tmp_path: Path):
    store = ThreadStore(root=tmp_path / "threads")
    session = store.create_or_resume_session(ChatInput(text="hello", cwd=str(tmp_path), project_id="p"))
    turn = store.create_turn(session["session_id"])
    builder = ContextBuilder(thread_store=store, skill_registry=SkillRegistry())
    prompt_builder = PromptBuilder()

    turn_context = builder.build(
        session_id=session["session_id"],
        turn_id=turn.turn_id,
        chat_input=ChatInput(text="总结 README.md", cwd=str(tmp_path), project_id="p"),
    )
    rendered = "\n".join(str(row.get("content") or "") for row in prompt_builder.build_messages(turn_context))

    assert "summarize_file" in rendered
    assert "Summarize a specific file" in rendered
    assert "# Steps" not in rendered

