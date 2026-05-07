from __future__ import annotations

from src.jarvis.core.policy.permissions import DomainRule, PermissionPolicy


def test_permission_decision_redacts_preview():
    decision = PermissionPolicy(profile="default").evaluate(
        "command_runner.run",
        {"command": "echo hi", "token": "sk-secret"},
    )
    assert decision.redacted_args_preview["token"] == "***"


def test_strict_unknown_domain_requires_approval():
    policy = PermissionPolicy(profile="strict", domain_rules=[DomainRule("nightlies.apache.org", "allow")])
    decision = policy.evaluate_domain("https://unknown.example.com/path")
    assert decision.action == "require_approval"
