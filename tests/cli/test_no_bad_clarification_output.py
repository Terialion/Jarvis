"""Tests that the old generic clarification sentence is NOT emitted.

Phase 2-3: Verifies that the old default clarification sentence
'我需要再确认一下：你可以具体告诉我你想让我做什么吗？例如：读项目、解释代码、改文件、运行命令，或者聊天。'
never appears as output for any non-truly-ambiguous input.
"""

from __future__ import annotations

from pathlib import Path

from src.jarvis.agent.loop import AgentLoop
from src.jarvis.agent.model import FakeModelClient
from src.jarvis.agent.types import ChatInput, ModelResponse


OLD_DEFAULT_CLARIFY = "我需要再确认一下：你可以具体告诉我你想让我做什么吗？例如：读项目、解释代码、改文件、运行命令，或者聊天。"


def _run_and_check_no_bad_clarify(text: str, tmp_path: Path) -> None:
    """Helper: run AgentLoop and assert old clarify sentence is not in final_answer."""
    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(
            scripted=[ModelResponse(final_answer="Response.", finish_reason="stop")]
        ),
        auto_approve=True,
    )
    result = loop.run_turn(ChatInput(text=text, cwd=str(tmp_path), project_id="test"))
    assert OLD_DEFAULT_CLARIFY not in result.final_answer, f"Old clarify sentence found in: {result.final_answer}"


def test_no_bad_clarify_model_question(tmp_path: Path):
    """'你是什么模型' does not emit old default clarification."""
    _run_and_check_no_bad_clarify("你是什么模型", tmp_path)


def test_no_bad_clarify_capability_question(tmp_path: Path):
    """'你能帮我写代码吗' does not emit old default clarification."""
    _run_and_check_no_bad_clarify("你能帮我写代码吗", tmp_path)


def test_no_bad_clarify_greeting(tmp_path: Path):
    """Greeting does not emit old default clarification."""
    _run_and_check_no_bad_clarify("下午好", tmp_path)


def test_no_bad_clarify_who_are_you(tmp_path: Path):
    """'你是谁' does not emit old default clarification."""
    _run_and_check_no_bad_clarify("你是谁", tmp_path)


def test_no_bad_clarify_tell_joke(tmp_path: Path):
    """Joke request does not emit old default clarification."""
    _run_and_check_no_bad_clarify("给我讲个笑话", tmp_path)


def test_no_bad_clarify_evening_greeting(tmp_path: Path):
    """Evening greeting does not emit old default clarification."""
    _run_and_check_no_bad_clarify("晚上好", tmp_path)


def test_no_bad_clarify_hi(tmp_path: Path):
    """'Hi' does not emit old default clarification."""
    _run_and_check_no_bad_clarify("hi", tmp_path)


def test_no_bad_clarify_what_can_you_do(tmp_path: Path):
    """'你能做什么' does not emit old default clarification."""
    _run_and_check_no_bad_clarify("你能做什么", tmp_path)
