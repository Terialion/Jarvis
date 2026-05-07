from __future__ import annotations

from src.jarvis.agent.tools import ToolCallExecutor, ToolRegistryAdapter
from src.jarvis.agent.types import ToolCall
from src.jarvis.core.policy import PermissionPolicy, get_approval_store


def test_approval_required_does_not_execute_tool(tmp_path):
    get_approval_store().reset()
    adapter = ToolRegistryAdapter(project_root=str(tmp_path))
    executor = ToolCallExecutor(
        registry_adapter=adapter,
        permission_policy=PermissionPolicy(profile="strict"),
        auto_approve=False,
    )
    result = executor.execute(
        ToolCall.new(name="command_runner.run", arguments={"command": "python -V"}),
        context={"session_id": "s1", "turn_id": "t1"},
    )
    assert not result.ok
    assert result.metadata.get("approval_required") is True
    assert "approval_id" in result.metadata


def test_approved_retry_can_execute_safe_fetch(tmp_path):
    store = get_approval_store()
    store.reset()
    adapter = ToolRegistryAdapter(project_root=str(tmp_path))
    executor = ToolCallExecutor(
        registry_adapter=adapter,
        permission_policy=PermissionPolicy(profile="strict"),
        auto_approve=False,
        approval_store=store,
    )
    first = executor.execute(
        ToolCall.new(name="command_runner.run", arguments={"command": "python -V"}),
        context={"session_id": "s1", "turn_id": "t1"},
    )
    approval_id = str(first.metadata.get("approval_id"))
    store.approve(approval_id, decided_by="test")
    second = executor.execute(
        ToolCall.new(name="command_runner.run", arguments={"command": "python -V"}),
        context={"session_id": "s1", "turn_id": "t2"},
    )
    assert second.ok or "handler_error" in str(second.error) or "result_code" in str(second.metadata)
