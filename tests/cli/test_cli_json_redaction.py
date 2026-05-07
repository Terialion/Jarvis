from __future__ import annotations

import json
from types import SimpleNamespace

from jarvis.cli_agent_output import render_agent_result


def test_cli_json_masks_secret_like_final_answer():
    result = SimpleNamespace(
        ok=True,
        final_answer="token=abc sk-live-secret Authorization: Bearer xyz",
        stop_reason="completed",
        status="completed",
        output_type="answer",
        tool_calls=[],
        events=[],
        summary={"machine": {"outcome": "completed", "tools_used": [], "risks": ["secret_redacted"]}},
    )
    rendered = render_agent_result(
        result=result,
        provider_line="LLM provider: fake model=fake-agent-v0",
        output_mode="json",
        mask_fn=lambda text: text.replace("token=abc", "token:[REDACTED]").replace("sk-live-secret", "[REDACTED_SECRET]").replace("Authorization: Bearer xyz", "Authorization:[REDACTED]"),
    )
    payload = json.loads(rendered)
    answer = payload["result"]["final_answer"]
    assert "token=abc" not in answer
    assert "sk-live-secret" not in answer
    assert "Authorization: Bearer xyz" not in answer
    assert "sk-" not in answer
    assert "Authorization: Bearer" not in answer
