from __future__ import annotations

from src.jarvis.core.policy.approval import ApprovalStore


def test_approval_store_create_approve_deny_and_redact():
    store = ApprovalStore()
    request = store.create_request(
        tool_name="command_runner.run",
        arguments_preview={"command": "python -V", "token": "sk-secret"},
        risk_level="high",
        reason="needs approval",
        session_id="s1",
    )
    assert request.arguments_preview["token"] == "***"
    assert store.list_pending()
    approved = store.approve(request.approval_id, decided_by="test")
    assert approved is not None
    assert store.get_request(request.approval_id).status == "approved"

    request2 = store.create_request(
        tool_name="web.fetch",
        arguments_preview={"url": "https://example.com"},
        risk_level="medium",
        reason="needs approval",
    )
    denied = store.deny(request2.approval_id, decided_by="test")
    assert denied is not None
    assert store.get_request(request2.approval_id).status == "denied"
