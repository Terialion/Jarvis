"""Tests for output_type in benchmark reporting.

Phase 4: Verifies that benchmark results include output_type
in run_result, and that checklist export includes it.
"""

from __future__ import annotations

from pathlib import Path

from src.jarvis.agent.loop import AgentLoop
from src.jarvis.agent.model import FakeModelClient
from src.jarvis.agent.types import ChatInput, ModelResponse, ToolCall


def test_benchmark_run_result_has_output_type(tmp_path: Path):
    """Benchmark case run_result must include output_type field."""
    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(
            scripted=[ModelResponse(final_answer="hello", finish_reason="stop")]
        ),
        auto_approve=True,
    )
    result = loop.run_turn(ChatInput(text="hi", cwd=str(tmp_path), project_id="jarvis_core"))
    d = result.to_dict()

    assert "output_type" in d
    assert d["output_type"] == "answer"


def test_benchmark_run_result_output_type_for_refusal(tmp_path: Path):
    """.env case should produce output_type=refusal in run_result."""
    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(
            scripted=[ModelResponse(final_answer="cannot", finish_reason="stop")]
        ),
        auto_approve=True,
    )
    result = loop.run_turn(ChatInput(text="print my .env", cwd=str(tmp_path), project_id="jarvis_core"))
    d = result.to_dict()

    assert "output_type" in d
    assert d["output_type"] == "refusal"


def test_benchmark_run_result_output_type_for_clarification(tmp_path: Path):
    """'帮我弄一下' case should produce output_type=clarification in run_result."""
    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(
            scripted=[ModelResponse(final_answer="which task", finish_reason="stop")]
        ),
        auto_approve=True,
    )
    result = loop.run_turn(ChatInput(text="帮我弄一下", cwd=str(tmp_path), project_id="jarvis_core"))
    d = result.to_dict()

    assert "output_type" in d
    assert d["output_type"] == "clarification"


def test_run_result_to_dict_is_json_serializable(tmp_path: Path):
    """AgentRunResult.to_dict() produces JSON-serializable output."""
    import json

    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(
            scripted=[ModelResponse(final_answer="hello", finish_reason="stop")]
        ),
        auto_approve=True,
    )
    result = loop.run_turn(ChatInput(text="hi", cwd=str(tmp_path), project_id="jarvis_core"))
    d = result.to_dict()

    # Must not raise
    json.dumps(d)
    assert isinstance(d, dict)
    assert "output_type" in d
    assert "ok" in d
    assert "stop_reason" in d
    assert "final_answer" in d
