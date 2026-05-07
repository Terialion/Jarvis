from __future__ import annotations

import json
from types import SimpleNamespace

from jarvis.cli_agent_output import render_agent_result


def _result(**overrides):
    base = {
        "ok": True,
        "final_answer": "done",
        "stop_reason": "completed",
        "status": "completed",
        "output_type": "tool_result",
        "tool_calls": [{"name": "repo_reader.read_file", "arguments": {"path": "README.md"}}],
        "events": [{"type": "tool_call_started", "payload": {"step": 1}}],
        "summary": {
            "machine": {
                "outcome": "completed",
                "tools_used": ["repo_reader.read_file"],
                "model_backend": "fake",
                "model_provider": "fake",
                "model_name": "fake-agent-v0",
                "risks": [],
            }
        },
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_json_output_uses_agent_runresult_contract():
    rendered = render_agent_result(
        result=_result(),
        provider_line="LLM provider: fake model=fake-agent-v0",
        output_mode="json",
        mask_fn=lambda text: text,
    )
    payload = json.loads(rendered)
    assert payload["ok"] is True
    assert payload["result"]["output_type"] == "tool_result"
    assert payload["result"]["tool_calls_count"] == 1
    assert payload["result"]["tools_used"] == ["repo_reader.read_file"]


def test_trace_output_includes_tool_events():
    rendered = render_agent_result(
        result=_result(),
        provider_line="LLM provider: fake model=fake-agent-v0",
        output_mode="trace",
        mask_fn=lambda text: text,
    )
    assert "tool_call_started" in rendered
    assert "repo_reader.read_file" in rendered


def test_refusal_output_stays_redacted():
    rendered = render_agent_result(
        result=_result(
            final_answer="不能打印 OPENAI_API_KEY:[REDACTED]",
            output_type="refusal",
            tool_calls=[],
            events=[],
            summary={"machine": {"outcome": "completed", "tools_used": [], "risks": ["secret_redacted"]}},
        ),
        provider_line="LLM provider: fake model=fake-agent-v0",
        output_mode="json",
        mask_fn=lambda text: text,
    )
    assert "OPENAI_API_KEY=" not in rendered
    assert "OPENAI_API_KEY:[REDACTED]" in rendered
