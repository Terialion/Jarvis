from __future__ import annotations

from pathlib import Path

from src.jarvis.agent.context import ContextBuilder
from src.jarvis.agent.prompt_builder import PromptBuilder
from src.jarvis.agent.store import ThreadStore
from src.jarvis.agent.types import ChatInput
from src.jarvis.skills.registry import SkillRegistry


def test_prompt_builder_includes_prior_turn_messages(tmp_path: Path):
    """Prior turn messages should appear in context; current turn messages should NOT."""
    store = ThreadStore(root=tmp_path / "threads")
    session = store.create_or_resume_session(ChatInput(text="hello", cwd=str(tmp_path), project_id="p"))

    # First turn — simulates a completed previous exchange
    turn1 = store.create_turn(session["session_id"])
    store.append_message(session["session_id"], turn1.turn_id, "user", "hello")
    store.append_message(session["session_id"], turn1.turn_id, "assistant", "previous answer")

    # Second turn — simulates the current request
    turn2 = store.create_turn(session["session_id"])
    builder = ContextBuilder(session_store=store, skill_registry=SkillRegistry())
    prompt_builder = PromptBuilder()

    turn_context = builder.build(
        session_id=session["session_id"],
        turn_id=turn2.turn_id,
        chat_input=ChatInput(text="new question", cwd=str(tmp_path), project_id="p"),
    )
    messages = prompt_builder.build_messages(turn_context)

    # Prior turn messages should be present (wrapped in <historical> tags)
    assert any("previous answer" in str(row.get("content") or "") for row in messages)
    # Current input should be the final message (now includes boundary prefix)
    assert "new question" in str(messages[-1]["content"] or "")


def test_current_user_input_appears_exactly_once(tmp_path: Path):
    """The current user input must NOT appear twice (regression test for duplicate bug)."""
    store = ThreadStore(root=tmp_path / "threads")
    session = store.create_or_resume_session(ChatInput(text="first", cwd=str(tmp_path), project_id="p"))

    # Previous turn
    turn1 = store.create_turn(session["session_id"])
    store.append_message(session["session_id"], turn1.turn_id, "user", "first")
    store.append_message(session["session_id"], turn1.turn_id, "assistant", "got it")

    # Current turn — user message is persisted before build (simulating run_turn flow)
    turn2 = store.create_turn(session["session_id"])
    store.append_message(session["session_id"], turn2.turn_id, "user", "second question")

    builder = ContextBuilder(session_store=store, skill_registry=SkillRegistry())
    prompt_builder = PromptBuilder()

    turn_context = builder.build(
        session_id=session["session_id"],
        turn_id=turn2.turn_id,
        chat_input=ChatInput(text="second question", cwd=str(tmp_path), project_id="p"),
    )
    messages = prompt_builder.build_messages(turn_context)

    # Count occurrences of the current input in all messages
    # Content is now combined with boundary prefix, so use substring match
    current_input_count = sum(
        1 for row in messages
        if "second question" in str(row.get("content") or "")
    )
    assert current_input_count == 1, (
        f"Current user input appears {current_input_count} times, should be exactly 1"
    )

    # The prior turn's user message should still be present (wrapped in <historical>)
    assert any("first" in str(row.get("content") or "") for row in messages)
    # The prior turn's assistant message should still be present (wrapped in <historical>)
    assert any("got it" in str(row.get("content") or "") for row in messages)


def test_prompt_builder_includes_skill_metadata_not_full_body(tmp_path: Path):
    store = ThreadStore(root=tmp_path / "threads")
    session = store.create_or_resume_session(ChatInput(text="hello", cwd=str(tmp_path), project_id="p"))
    turn = store.create_turn(session["session_id"])
    builder = ContextBuilder(session_store=store, skill_registry=SkillRegistry())
    prompt_builder = PromptBuilder()

    turn_context = builder.build(
        session_id=session["session_id"],
        turn_id=turn.turn_id,
        chat_input=ChatInput(text="summarize README.md", cwd=str(tmp_path), project_id="p"),
    )
    rendered = "\n".join(str(row.get("content") or "") for row in prompt_builder.build_messages(turn_context))

    assert "summarize_file" in rendered
    assert "Summarize a specific file" in rendered
    assert "# Steps" not in rendered


def test_empty_history_does_not_duplicate_input(tmp_path: Path):
    """When no prior messages exist, the user input still appears exactly once."""
    store = ThreadStore(root=tmp_path / "threads")
    session = store.create_or_resume_session(ChatInput(text="first ever", cwd=str(tmp_path), project_id="p"))
    turn = store.create_turn(session["session_id"])
    store.append_message(session["session_id"], turn.turn_id, "user", "first ever")

    builder = ContextBuilder(session_store=store, skill_registry=SkillRegistry())
    prompt_builder = PromptBuilder()

    turn_context = builder.build(
        session_id=session["session_id"],
        turn_id=turn.turn_id,
        chat_input=ChatInput(text="first ever", cwd=str(tmp_path), project_id="p"),
    )
    messages = prompt_builder.build_messages(turn_context)

    count = sum(1 for row in messages if "first ever" in str(row.get("content") or ""))
    assert count == 1, f"Input appears {count} times on first message, should be 1"
