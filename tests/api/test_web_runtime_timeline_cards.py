from __future__ import annotations

from src.jarvis.agent.types import AgentRunResult
from src.jarvis.api.timeline import timeline_from_agent_result


def test_timeline_includes_skill_guided_web_cards():
    result = AgentRunResult(
        ok=True,
        session_id="s1",
        turn_id="t1",
        final_answer="done",
        events=[
            {
                "event_id": "e1",
                "type": "web_search_completed",
                "timestamp": "2026-01-01T00:00:00Z",
                "payload": {
                    "query": "today tech news",
                    "guided_by_skill": "multi-search-engine",
                    "invocation_path": "reference_skill_guided_tool_call",
                    "source": "skill_guided",
                },
            },
            {
                "event_id": "e2",
                "type": "web_fetch_completed",
                "timestamp": "2026-01-01T00:00:01Z",
                "payload": {
                    "url": "https://example.com",
                    "url_source": "search_result_url",
                },
            },
        ],
        summary={"machine": {}},
        stop_reason="completed",
    )
    timeline = timeline_from_agent_result(result).to_dict()
    types = [item["type"] for item in timeline["items"]]
    assert "skill_guided_search" in types
    assert "web_fetch" in types

