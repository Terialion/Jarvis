from __future__ import annotations

from src.jarvis.agent.types import AgentRunResult


def test_explicit_url_fetch_is_handled_before_web_research():
    result = AgentRunResult(
        ok=True,
        session_id="s",
        turn_id="t",
        final_answer="content fetched",
        events=[
            {"type": "explicit_url_fetch_detected", "payload": {"url": "https://docs.python.org/3/"}},
            {"type": "web_fetch_completed", "payload": {"url": "https://docs.python.org/3/"}},
            {"type": "context_updated", "payload": {}},
        ],
        summary={},
        stop_reason="completed",
        output_type="answer",
    )

    event_types = [e["type"] for e in result.events]
    assert "explicit_url_fetch_detected" in event_types
    assert "web_search_completed" not in event_types


def test_sensitive_url_is_blocked():
    result = AgentRunResult(
        ok=False,
        session_id="s",
        turn_id="t",
        final_answer="blocked",
        events=[
            {"type": "web_fetch_blocked", "payload": {"url": "https://example.com/secrets", "reason": "sensitive_url"}},
            {"type": "context_updated", "payload": {}},
        ],
        summary={},
        stop_reason="refusal",
        output_type="refusal",
    )

    event_types = [e["type"] for e in result.events]
    assert "web_fetch_blocked" in event_types
    assert not result.ok
