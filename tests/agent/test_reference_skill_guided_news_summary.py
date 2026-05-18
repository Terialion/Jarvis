from __future__ import annotations

from src.jarvis.agent.types import AgentRunResult


def test_reference_skill_sets_intended_path_to_reference_guided():
    result = AgentRunResult(
        ok=True,
        session_id="s",
        turn_id="t1",
        final_answer="Here are today's tech news...",
        events=[
            {"type": "skill_invocation_detected", "payload": {"skill": "multi-search-engine", "source": "explicit_name"}},
            {"type": "skill_use_plan_created", "payload": {"plan": {"selected_skill": "multi-search-engine", "intended_path": "reference_guided_tool_call", "source": "explicit_invocation"}}},
            {"type": "reference_skill_guided_tool_call_started", "payload": {"skill": "multi-search-engine", "tool_calls": [{"name": "web.search", "args": {"query": "today tech news"}}]}},
            {"type": "web_search_completed", "payload": {"query": "today tech news"}},
            {"type": "context_updated", "payload": {}},
        ],
        summary={},
        stop_reason="completed",
        output_type="answer",
    )

    event_types = [e["type"] for e in result.events]
    assert "skill_invocation_detected" in event_types
    assert "skill_use_plan_created" in event_types
    assert "skill_call_started" not in event_types


def test_news_summary_reference_skill_uses_extracted_query():
    result = AgentRunResult(
        ok=True,
        session_id="s",
        turn_id="t2",
        final_answer="news summarized",
        events=[
            {"type": "skill_invocation_detected", "payload": {"skill": "multi-search-engine"}},
            {"type": "reference_skill_guided_tool_call_started", "payload": {"skill": "multi-search-engine", "tool_calls": [{"name": "web.search", "args": {"query": "today tech news"}}, {"name": "web.fetch", "args": {"url": "https://example.com/news"}}]}},
            {"type": "context_updated", "payload": {}},
        ],
        summary={},
        stop_reason="completed",
        output_type="answer",
    )

    for event in result.events:
        if event["type"] == "reference_skill_guided_tool_call_started":
            for tc in event["payload"].get("tool_calls", []):
                if tc.get("name") == "web.search":
                    query = str(tc.get("args", {}).get("query", ""))
                    assert "use multi-search-engine" not in query.lower()


def test_reference_skill_never_claims_execution():
    result = AgentRunResult(
        ok=True,
        session_id="s",
        turn_id="t3",
        final_answer="results",
        events=[
            {"type": "skill_invocation_detected", "payload": {"skill": "multi-search-engine"}},
            {"type": "reference_skill_guided_tool_call_started", "payload": {"skill": "multi-search-engine"}},
            {"type": "context_updated", "payload": {}},
        ],
        summary={},
        stop_reason="completed",
        output_type="answer",
        skill_results=[],
    )

    assert len(result.skill_results) == 0
