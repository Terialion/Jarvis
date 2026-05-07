from __future__ import annotations

from src.jarvis.agent.tools import ToolCallExecutor, ToolRegistryAdapter
from src.jarvis.agent.types import ToolCall
from src.jarvis.core.policy import PermissionPolicy


def test_ssrf_cannot_be_bypassed_even_in_dangerous_profile(tmp_path):
    executor = ToolCallExecutor(
        registry_adapter=ToolRegistryAdapter(project_root=str(tmp_path)),
        permission_policy=PermissionPolicy(profile="dangerous"),
        auto_approve=True,
    )
    result = executor.execute(
        ToolCall.new(name="web.fetch", arguments={"url": "http://127.0.0.1/private"}),
        context={"session_id": "s", "turn_id": "t"},
    )
    assert not result.ok
    assert "ssrf_blocked" in str(result.error)
