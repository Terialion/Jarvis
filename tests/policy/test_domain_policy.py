from __future__ import annotations

from src.jarvis.agent.tools import ToolCallExecutor, ToolRegistryAdapter
from src.jarvis.agent.types import ToolCall
from src.jarvis.core.policy import DomainRule, PermissionPolicy
from src.jarvis.web.fixtures import FLINK_OFFICIAL_URL


def test_domain_policy_blocks_and_requires_approval(tmp_path):
    adapter = ToolRegistryAdapter(project_root=str(tmp_path))
    policy = PermissionPolicy(profile="strict", domain_rules=[DomainRule("nightlies.apache.org", "allow"), DomainRule("blocked.example.com", "deny")])
    executor = ToolCallExecutor(registry_adapter=adapter, permission_policy=policy, auto_approve=False)

    blocked = executor.execute(ToolCall.new(name="web.fetch", arguments={"url": "https://blocked.example.com/path"}), context={"session_id": "s", "turn_id": "t"})
    assert not blocked.ok
    assert "domain_policy_denied" in str(blocked.error)

    approval = executor.execute(ToolCall.new(name="web.fetch", arguments={"url": FLINK_OFFICIAL_URL}), context={"session_id": "s", "turn_id": "t"})
    assert not approval.ok
    assert "approval_required" in str(approval.error)
