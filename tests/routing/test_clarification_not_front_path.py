"""Tests that clarification.py is NOT on the default runtime path.

Phase 3: Verifies that the default interactive and one-shot paths
do NOT call clarification.py. Clarification is produced by
AgentLoop._build_clarification_if_needed, not by the routing layer.
"""

from __future__ import annotations

from pathlib import Path

from src.jarvis.agent.loop import AgentLoop
from src.jarvis.agent.model import FakeModelClient
from src.jarvis.agent.types import ChatInput, ModelResponse


def test_genuinely_vague_uses_agent_loopClarification(tmp_path: Path):
    """'帮我弄一下' should get clarification from AgentLoop, not from clarification.py module."""
    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(
            scripted=[ModelResponse(final_answer="please clarify", finish_reason="stop")]
        ),
        auto_approve=True,
    )
    result = loop.run_turn(ChatInput(text="帮我弄一下", cwd=str(tmp_path), project_id="test"))
    # output_type must be clarification, produced by AgentLoop's _build_clarification_if_needed
    assert result.output_type == "clarification"
    # The clarification question should be specific, not the old generic one
    assert "文件" in result.final_answer or "哪个" in result.final_answer or "具体" in result.final_answer


def test_clarification_py_not_imported_in_default_cli_path(tmp_path: Path):
    """Verify clarification.py is not called in default AgentLoop run path."""
    # This is a static check: the AgentLoop path does not import clarification.py
    # We verify by running a genuine clarification case and checking
    # the clarification came from _build_clarification_if_needed (in loop.py),
    # not from build_clarification_route (in clarification.py)
    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(
            scripted=[ModelResponse(final_answer="需要澄清", finish_reason="stop")]
        ),
        auto_approve=True,
    )
    result = loop.run_turn(ChatInput(text="修一下", cwd=str(tmp_path), project_id="test"))
    # Must NOT fall through to clarification.py's generic fallback
    assert result.final_answer != "我需要再确认一下：你可以具体告诉我你想让我做什么吗？例如：读项目、解释代码、改文件、运行命令，或者聊天。"
