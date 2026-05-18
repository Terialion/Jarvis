"""Tests for session continuity — conversation history injected into new turns."""

from __future__ import annotations

from pathlib import Path

from src.jarvis.agent.context import ContextBuilder
from src.jarvis.agent.prompt_builder import PromptBuilder
from src.jarvis.agent.store import ThreadStore
from src.jarvis.agent.types import ChatInput
from src.jarvis.skills.registry import SkillRegistry


def test_compacted_summary_injected(tmp_path: Path):
    """When a previous turn produced a summary, it should appear in the next turn's messages."""
    store = ThreadStore(root=tmp_path / "threads")
    session = store.create_or_resume_session(ChatInput(text="summarize this file", cwd=str(tmp_path), project_id="p"))

    # Simulate a completed turn with a summary saved
    turn1 = store.create_turn(session["session_id"])
    store.append_message(session["session_id"], turn1.turn_id, "user", "summarize this file")
    store.append_message(session["session_id"], turn1.turn_id, "assistant", "The file contains 3 functions.")
    store.save_summary(
        session["session_id"],
        turn1.turn_id,
        {"human": "Discussed a Python file with 3 functions: init, run, cleanup."}
    )

    turn2 = store.create_turn(session["session_id"])
    builder = ContextBuilder(session_store=store, skill_registry=SkillRegistry())
    prompt_builder = PromptBuilder()

    turn_context = builder.build(
        session_id=session["session_id"],
        turn_id=turn2.turn_id,
        chat_input=ChatInput(text="what did we discuss?", cwd=str(tmp_path), project_id="p"),
    )
    messages = prompt_builder.build_messages(turn_context)

    # The compacted summary should be injected
    summary_msgs = [m for m in messages if "<conversation-summary>" in str(m.get("content", ""))]
    assert len(summary_msgs) == 1
    assert "3 functions" in str(summary_msgs[0]["content"])

    # Prior assistant answer should be in history
    assert any("The file contains 3 functions" in str(m.get("content", "")) for m in messages)

    # Current user input should be the last message
    assert "what did we discuss?" in str(messages[-1].get("content", ""))


def test_no_summary_when_no_prior_compaction(tmp_path: Path):
    """When there is no compacted summary, no summary block should be injected."""
    store = ThreadStore(root=tmp_path / "threads")
    session = store.create_or_resume_session(ChatInput(text="hello", cwd=str(tmp_path), project_id="p"))

    turn = store.create_turn(session["session_id"])
    store.append_message(session["session_id"], turn.turn_id, "user", "hello")

    builder = ContextBuilder(session_store=store, skill_registry=SkillRegistry())
    prompt_builder = PromptBuilder()

    turn_context = builder.build(
        session_id=session["session_id"],
        turn_id=turn.turn_id,
        chat_input=ChatInput(text="new question", cwd=str(tmp_path), project_id="p"),
    )
    messages = prompt_builder.build_messages(turn_context)

    summary_msgs = [m for m in messages if "<conversation-summary>" in str(m.get("content", ""))]
    assert len(summary_msgs) == 0

    # User input should still appear
    assert "new question" in str(messages[-1].get("content", ""))


def test_conversation_history_excludes_current_turn(tmp_path: Path):
    """Messages from the current turn must not appear in the history feed."""
    store = ThreadStore(root=tmp_path / "threads")
    session = store.create_or_resume_session(ChatInput(text="first", cwd=str(tmp_path), project_id="p"))

    # Previous turn
    turn1 = store.create_turn(session["session_id"])
    store.append_message(session["session_id"], turn1.turn_id, "user", "first question")
    store.append_message(session["session_id"], turn1.turn_id, "assistant", "first answer")

    # Current turn — persist its user message before build (mimics run_turn flow)
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

    # "second question" should appear exactly once (as the current input)
    # Content is now combined with boundary prefix, so use substring match
    second_count = sum(1 for m in messages if "second question" in str(m.get("content", "")))
    assert second_count == 1, f"Current input appears {second_count} times"

    # "first question" and "first answer" should appear (from history, wrapped in <historical>)
    assert any("first question" in str(m.get("content", "")) for m in messages)
    assert any("first answer" in str(m.get("content", "")) for m in messages)
