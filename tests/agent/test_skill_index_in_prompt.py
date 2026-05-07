from __future__ import annotations

from pathlib import Path

from src.jarvis.agent.context import ContextBuilder
from src.jarvis.agent.prompt_builder import PromptBuilder
from src.jarvis.agent.store import ThreadStore
from src.jarvis.agent.types import ChatInput
from src.jarvis.skills.registry import SkillRegistry


def test_prompt_contains_skill_index_metadata_only(tmp_path: Path):
    store = ThreadStore(root=tmp_path / "threads")
    session = store.create_or_resume_session(ChatInput(text="总结 README.md", cwd=str(tmp_path), project_id="p"))
    turn = store.create_turn(session["session_id"])
    turn_context = ContextBuilder(thread_store=store, skill_registry=SkillRegistry()).build(
        session_id=session["session_id"],
        turn_id=turn.turn_id,
        chat_input=ChatInput(text="总结 README.md", cwd=str(tmp_path), project_id="p"),
    )
    rendered = "\n".join(str(row.get("content") or "") for row in PromptBuilder().build_messages(turn_context))

    assert "Available skills:" in rendered
    assert "repo_overview" in rendered
    assert "fix_test_failure" in rendered
    assert "skill_scanner" in rendered
    assert "source=builtin" in rendered
    assert "allowed_tools=repo_reader.read_file" in rendered
    assert "# Goal" not in rendered
    assert "# Steps" not in rendered
