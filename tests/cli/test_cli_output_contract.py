"""Tests for CLI JSON output contract.

Phase 2: Verifies that the CLI renderer produces valid JSON with
all required fields: ok, output_type, stop_reason, final_answer,
tool_calls_count, tools_used, model_backend, model_provider, model_name.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.jarvis.agent.loop import AgentLoop
from src.jarvis.agent.model import FakeModelClient
from src.jarvis.agent.types import ChatInput, ModelResponse, ToolCall


def test_json_output_has_ok_field(tmp_path: Path):
    """JSON mode output includes top-level 'ok' field."""
    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(
            scripted=[ModelResponse(final_answer="hello", finish_reason="stop")]
        ),
        auto_approve=True,
    )
    result = loop.run_turn(ChatInput(text="hi", cwd=str(tmp_path), project_id="test"))

    from src.jarvis.cli_agent_output import render_agent_result

    rendered = render_agent_result(
        result=result,
        provider_line="LLM provider: fake model=fake-agent-v0",
        output_mode="json",
        mask_fn=lambda x: x,
    )
    parsed = json.loads(rendered)
    assert "ok" in parsed
    assert isinstance(parsed["ok"], bool)


def test_json_output_has_output_type(tmp_path: Path):
    """JSON mode output includes 'output_type' field in result."""
    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(
            scripted=[ModelResponse(final_answer="hello", finish_reason="stop")]
        ),
        auto_approve=True,
    )
    result = loop.run_turn(ChatInput(text="hi", cwd=str(tmp_path), project_id="test"))

    from src.jarvis.cli_agent_output import render_agent_result

    rendered = render_agent_result(
        result=result,
        provider_line="LLM provider: fake model=fake-agent-v0",
        output_mode="json",
        mask_fn=lambda x: x,
    )
    parsed = json.loads(rendered)
    assert "result" in parsed
    assert "output_type" in parsed["result"]
    assert parsed["result"]["output_type"] == "answer"


def test_json_output_has_tools_used(tmp_path: Path):
    """JSON mode output includes 'tools_used' field."""
    readme = tmp_path / "README.md"
    readme.write_text("test", encoding="utf-8")

    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(
            scripted=[
                ModelResponse(
                    tool_calls=[ToolCall.new(name="repo_reader.read_file", arguments={"path": str(readme)})],
                    finish_reason="tool_calls",
                ),
                ModelResponse(final_answer="Done reading.", finish_reason="stop"),
            ]
        ),
        auto_approve=True,
    )
    result = loop.run_turn(ChatInput(text="read it", cwd=str(tmp_path), project_id="test"))

    from src.jarvis.cli_agent_output import render_agent_result

    rendered = render_agent_result(
        result=result,
        provider_line="LLM provider: fake model=fake-agent-v0",
        output_mode="json",
        mask_fn=lambda x: x,
    )
    parsed = json.loads(rendered)
    assert "result" in parsed
    assert "tools_used" in parsed["result"]
    assert isinstance(parsed["result"]["tools_used"], list)


def test_json_output_has_model_fields(tmp_path: Path):
    """JSON mode output includes model_backend, model_provider, model_name."""
    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(
            scripted=[ModelResponse(final_answer="hello", finish_reason="stop")]
        ),
        auto_approve=True,
    )
    result = loop.run_turn(ChatInput(text="hi", cwd=str(tmp_path), project_id="test"))

    from src.jarvis.cli_agent_output import render_agent_result

    rendered = render_agent_result(
        result=result,
        provider_line="LLM provider: fake model=fake-agent-v0",
        output_mode="json",
        mask_fn=lambda x: x,
    )
    parsed = json.loads(rendered)
    assert "model_backend" in parsed["result"]
    assert "model_provider" in parsed["result"]
    assert "model_name" in parsed["result"]


def test_json_output_pure_json(tmp_path: Path):
    """JSON mode output is valid JSON that can be json.loads()."""
    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(
            scripted=[ModelResponse(final_answer="hello", finish_reason="stop")]
        ),
        auto_approve=True,
    )
    result = loop.run_turn(ChatInput(text="hi", cwd=str(tmp_path), project_id="test"))

    from src.jarvis.cli_agent_output import render_agent_result

    rendered = render_agent_result(
        result=result,
        provider_line="LLM provider: fake",
        output_mode="json",
        mask_fn=lambda x: x,
    )
    # Must not raise
    parsed = json.loads(rendered)
    assert isinstance(parsed, dict)


def test_verbose_output_shows_output_type(tmp_path: Path):
    """Verbose mode includes output_type in Runtime section."""
    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(
            scripted=[ModelResponse(final_answer="hello", finish_reason="stop")]
        ),
        auto_approve=True,
    )
    result = loop.run_turn(ChatInput(text="hi", cwd=str(tmp_path), project_id="test"))

    from src.jarvis.cli_agent_output import render_agent_result

    rendered = render_agent_result(
        result=result,
        provider_line="LLM provider: fake",
        output_mode="verbose",
        mask_fn=lambda x: x,
    )
    assert "output_type=answer" in rendered


def test_trace_output_shows_events(tmp_path: Path):
    """Trace mode includes event list."""
    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(
            scripted=[ModelResponse(final_answer="hello", finish_reason="stop")]
        ),
        auto_approve=True,
    )
    result = loop.run_turn(ChatInput(text="hi", cwd=str(tmp_path), project_id="test"))

    from src.jarvis.cli_agent_output import render_agent_result

    rendered = render_agent_result(
        result=result,
        provider_line="LLM provider: fake",
        output_mode="trace",
        mask_fn=lambda x: x,
    )
    assert "Trace" in rendered
    assert "turn_started" in rendered or "model_call_started" in rendered
