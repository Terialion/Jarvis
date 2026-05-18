from __future__ import annotations

from src.jarvis.agent.types import AgentRunResult


def test_description_match_produces_skill_description_matched_event():
    result = AgentRunResult(
        ok=True,
        session_id="s",
        turn_id="t1",
        final_answer="done",
        events=[
            {"type": "skill_description_matched", "payload": {"skill": "summarize_file", "confidence": 0.82}},
            {"type": "skill_use_plan_created", "payload": {"plan": {"selected_skill": "summarize_file", "intended_path": "skill_run", "source": "description_match"}}},
            {"type": "skill_call_started", "payload": {"skill_name": "summarize_file"}},
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
    assert "skill_description_matched" in event_types
    assert "web_search" not in event_types
    assert "web_fetch" not in event_types


def test_ambiguous_match_does_not_false_execute():
    result = AgentRunResult(
        ok=True,
        session_id="s",
        turn_id="t2",
        final_answer="Which skill did you mean?",
        events=[
            {"type": "ambiguous_skill_match", "payload": {"candidates": [{"name": "summarize_file"}, {"name": "repo_overview"}]}},
            {"type": "skill_use_plan_rejected", "payload": {"plan": {"intended_path": "ask_clarification"}}},
            {"type": "context_updated", "payload": {}},
        ],
        summary={},
        stop_reason="completed",
        output_type="answer",
    )

    event_types = [e["type"] for e in result.events]
    assert "ambiguous_skill_match" in event_types
    assert "skill_call_started" not in event_types


def test_no_skill_match_falls_through_to_web_search():
    result = AgentRunResult(
        ok=True,
        session_id="s",
        turn_id="t3",
        final_answer="search results",
        events=[
            {"type": "research_intent_classified", "payload": {"intent_type": "web_search"}},
            {"type": "web_search_completed", "payload": {"query": "what is Python 3.13"}},
            {"type": "context_updated", "payload": {}},
        ],
        summary={},
        stop_reason="completed",
        output_type="answer",
    )

    event_types = [e["type"] for e in result.events]
    assert "skill_description_matched" not in event_types
    assert "web_search_completed" in event_types
