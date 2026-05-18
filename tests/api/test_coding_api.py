from __future__ import annotations

from src.jarvis.api.server import JarvisApiState, route_request
from src.jarvis.core.policy import get_approval_store


def test_coding_review_api_returns_timeline():
    status, payload = route_request(
        JarvisApiState(),
        "POST",
        "/api/coding/review",
        {"path": "benchmarks/suites/coding/fixtures/calculator_bug", "project_root": ".", "session_id": "api_review"},
    )

    assert status == 200
    data = payload["data"]
    assert data["action"] == "review"
    assert data["timeline"]["items"]


def test_coding_fix_api_requires_approval_for_apply():
    get_approval_store().reset()
    status, payload = route_request(
        JarvisApiState(),
        "POST",
        "/api/coding/fix",
        {"input": "Fix calculator bug", "project_root": "benchmarks/suites/coding/fixtures/calculator_bug", "session_id": "api_fix", "apply": True},
    )

    assert status == 200
    data = payload["data"]
    assert data["approval_required"] is True
    assert data["result"]["stop_reason"] == "approval_required"
