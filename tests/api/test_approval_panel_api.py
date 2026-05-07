from __future__ import annotations

from src.jarvis.api.server import JarvisApiState, route_request
from src.jarvis.core.policy import get_approval_store


def test_approval_panel_api_resolves_without_direct_tool_execution():
    get_approval_store().reset()
    state = JarvisApiState()
    approval_id = "approval_panel_test"
    state.approvals[approval_id] = {
        "approval_id": approval_id,
        "risk_tier": "high",
        "reason": "test approval",
        "safe_alternative": "retry later",
        "status": "pending",
        "created_at": "2026-05-07T00:00:00+00:00",
    }
    status_list, payload_list = route_request(state, "GET", "/api/approvals")
    assert status_list == 200
    assert any(row["approval_id"] == approval_id for row in payload_list["data"])

    status_approve, payload_approve = route_request(state, "POST", f"/api/approvals/{approval_id}/approve")
    assert status_approve == 200
    assert payload_approve["data"]["status"] == "approved"
    assert payload_approve["data"]["retry_required"] is True
    assert "retry" in payload_approve["data"]["message"]
