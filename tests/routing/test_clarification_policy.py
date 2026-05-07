"""Clarification behavior tests for the default AgentLoop path."""

from __future__ import annotations

from pathlib import Path

from src.jarvis.agent.loop import AgentLoop
from src.jarvis.agent.model import FakeModelClient
from src.jarvis.agent.types import ChatInput, ModelResponse


def _run_turn(text: str, tmp_path: Path):
    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(
            scripted=[ModelResponse(final_answer="unused", finish_reason="stop")]
        ),
        auto_approve=True,
    )
    return loop.run_turn(ChatInput(text=text, cwd=str(tmp_path), project_id="test"))


def test_clarification_policy_handles_generic_ambiguous_input(tmp_path: Path):
    result = _run_turn("帮我弄一下", tmp_path)
    assert result.output_type == "clarification"
    assert result.stop_reason == "needs_user_clarification"
    assert result.final_answer


def test_clarification_policy_handles_missing_file_target(tmp_path: Path):
    result = _run_turn("读取那个文件", tmp_path)
    assert result.output_type == "clarification"
    assert result.stop_reason == "needs_user_clarification"
    assert "文件" in result.final_answer

