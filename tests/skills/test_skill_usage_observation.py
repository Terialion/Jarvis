from __future__ import annotations

from src.jarvis.skills.usage import SkillUsageObservation


def test_skill_usage_observation_fields_match_spec():
    obs = SkillUsageObservation(
        event_type="skill_selected",
        skill_name="summarize_file",
        skill_type="executable",
        invocation_source="description_match",
        invocation_path="description_match",
        confidence=0.88,
        user_instruction="summarize README.md",
        tool_calls=[],
        success=True,
        error=None,
        blocked_reason=None,
    )

    d = obs.to_dict()
    assert "event_type" in d
    assert "skill_name" in d
    assert "skill_type" in d
    assert "invocation_source" in d
    assert "invocation_path" in d
    assert "confidence" in d
    assert "user_instruction" in d
    assert "tool_calls" in d
    assert "success" in d
    assert "error" in d
    assert "blocked_reason" in d
    assert "timestamp" in d


def test_skill_usage_observation_truncates_long_instruction():
    obs = SkillUsageObservation(
        event_type="skill_selected",
        skill_name="s",
        user_instruction="x" * 300,
    )
    d = obs.to_dict()
    assert len(d["user_instruction"]) <= 200


def test_blocked_observation_has_reason():
    obs = SkillUsageObservation(
        event_type="blocked",
        skill_name="bad_skill",
        blocked_reason="quarantined",
    )
    d = obs.to_dict()
    assert d["blocked_reason"] == "quarantined"
    assert d["event_type"] == "blocked"


def test_executed_observation_has_success_flag():
    obs = SkillUsageObservation(
        event_type="skill_executed",
        skill_name="summarize_file",
        success=True,
    )
    assert obs.success is True

    obs2 = SkillUsageObservation(
        event_type="skill_executed",
        skill_name="bad_skill",
        success=False,
        error="execution failed",
    )
    assert obs2.success is False
    assert obs2.error == "execution failed"
