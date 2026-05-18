from __future__ import annotations

from src.jarvis.agent.types import AgentRunResult
from src.jarvis.skills.usage import SkillUsageObservation, SkillUsageTracker


def test_skill_usage_observation_to_dict():
    obs = SkillUsageObservation(
        event_type="skill_executed",
        skill_name="summarize_file",
        skill_type="executable",
        invocation_source="explicit_invocation",
        invocation_path="skill_run",
        confidence=0.95,
        user_instruction="summarize README",
        success=True,
    )
    d = obs.to_dict()
    assert d["event_type"] == "skill_executed"
    assert d["skill_name"] == "summarize_file"
    assert d["success"] is True
    assert d["invocation_path"] == "skill_run"


def test_tracker_records_loaded():
    tracker = SkillUsageTracker()
    obs = tracker.record_loaded("summarize_file", "executable")
    assert len(tracker.observations) == 1
    assert obs.event_type == "skill_loaded"
    assert obs.skill_name == "summarize_file"


def test_tracker_records_executed():
    tracker = SkillUsageTracker()
    obs = tracker.record_executed(
        skill_name="summarize_file",
        skill_type="executable",
        invocation_path="deterministic",
        success=True,
    )
    assert obs.event_type == "skill_executed"
    assert obs.success is True


def test_tracker_records_reference_used():
    tracker = SkillUsageTracker()
    obs = tracker.record_reference_used(
        skill_name="multi-search-engine",
        tool_calls=[{"name": "web.search", "args": {"query": "news"}}],
        success=True,
    )
    assert obs.event_type == "reference_skill_used"
    assert obs.invocation_path == "reference_guided_tool_call"


def test_tracker_records_fallback():
    tracker = SkillUsageTracker()
    obs = tracker.record_fallback(
        skill_name="none",
        reason="no_skill_match_web_research_fallback",
        instruction="random question",
    )
    assert obs.event_type == "fallback_used"
    assert obs.blocked_reason == "no_skill_match_web_research_fallback"


def test_agent_run_result_carries_skill_telemetry_fields():
    result = AgentRunResult(
        ok=True,
        session_id="s",
        turn_id="t",
        final_answer="done",
        events=[{"type": "telemetry_flushed", "payload": {"records": 3}}],
        summary={},
        stop_reason="completed",
        output_type="tool_result",
        skills_used=["summarize_file"],
        skill_calls_count=1,
        loaded_skills=["summarize_file"],
        skill_loads_count=1,
        skill_results=[{"skill_name": "summarize_file", "ok": True}],
    )

    assert len(result.skills_used) == 1
    assert result.skill_calls_count == 1
    assert result.skill_loads_count == 1
    assert len(result.skill_results) == 1
    assert any(e["type"] == "telemetry_flushed" for e in result.events)
