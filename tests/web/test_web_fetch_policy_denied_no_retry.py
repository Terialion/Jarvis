from __future__ import annotations

from pathlib import Path

from src.jarvis.agent.tools import ToolCallExecutor, ToolRegistryAdapter
from src.jarvis.agent.types import ToolCall


def test_domain_policy_denied_does_not_retry(tmp_path: Path):
    registry = ToolRegistryAdapter(project_root=str(tmp_path), permission_mode="workspace_write")
    executor = ToolCallExecutor(
        registry_adapter=registry,
        permission_mode="workspace_write",
        auto_approve=True,
    )
    call = ToolCall.new(
        name="web.fetch",
        arguments={
            "url": "http://127.0.0.1/private",
            "max_chars": 100,
            "provenance": {"url_source": "user_explicit_url"},
        },
    )
    result = executor.execute(call, context={"cwd": str(tmp_path), "session_id": "s", "turn_id": "t"})
    event_types = [str(e.get("type")) for e in list((result.metadata or {}).get("agent_events") or []) if isinstance(e, dict)]
    assert result.ok is False
    assert "policy_denied_retried" not in event_types

