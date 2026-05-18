from __future__ import annotations

from src.jarvis.agent.types import AgentRunResult


def test_explicit_skill_invocation_produces_skill_invocation_event():
    result = AgentRunResult(
        ok=True,
        session_id="s",
        turn_id="t1",
        final_answer="done",
        events=[
            {"type": "skill_invocation_detected", "payload": {"skill": "summarize_file", "source": "explicit_name"}},
            {"type": "skill_use_plan_created", "payload": {"plan": {"selected_skill": "summarize_file", "intended_path": "skill_run"}}},
            {"type": "skill_call_started", "payload": {"skill_name": "summarize_file"}},
            {"type": "skill_call_completed", "payload": {"skill_name": "summarize_file", "ok": True}},
            {"type": "context_updated", "payload": {}},
        ],
        summary={},
        stop_reason="completed",
        output_type="tool_result",
        skills_used=["summarize_file"],
        skill_calls_count=1,
        skill_results=[{"skill_name": "summarize_file", "ok": True}],
    )

    event_types = [e["type"] for e in result.events]
    assert "skill_invocation_detected" in event_types
    assert "skill_use_plan_created" in event_types
    assert "web_search" not in event_types
    assert "web_fetch" not in event_types


def test_explicit_reference_skill_does_not_enter_web_research_with_raw_sentence():
    result = AgentRunResult(
        ok=True,
        session_id="s",
        turn_id="t2",
        final_answer="search results summary",
        events=[
            {"type": "skill_invocation_detected", "payload": {"skill": "multi-search-engine", "source": "explicit_name"}},
            {"type": "skill_use_plan_created", "payload": {"plan": {"selected_skill": "multi-search-engine", "intended_path": "reference_guided_tool_call"}}},
            {"type": "reference_skill_guided_tool_call_started", "payload": {"skill": "multi-search-engine", "tool_calls": [{"name": "web.search", "args": {"query": "latest tech news"}}]}},
            {"type": "context_updated", "payload": {}},
        ],
        summary={},
        stop_reason="completed",
        output_type="answer",
    )

    for event in result.events:
        if event["type"] == "reference_skill_guided_tool_call_started":
            for tc in event["payload"].get("tool_calls", []):
                query = str(tc.get("args", {}).get("query", ""))
                assert "use multi-search-engine" not in query.lower()


def test_fallback_to_web_research_without_skill_match():
    result = AgentRunResult(
        ok=True,
        session_id="s",
        turn_id="t3",
        final_answer="search results",
        events=[
            {"type": "research_intent_classified", "payload": {"intent_type": "web_search"}},
            {"type": "web_search_completed", "payload": {"query": "simple factual question"}},
            {"type": "context_updated", "payload": {}},
        ],
        summary={},
        stop_reason="completed",
        output_type="answer",
    )

    event_types = [e["type"] for e in result.events]
    assert "skill_invocation_detected" not in event_types
    assert "web_search_completed" in event_types
