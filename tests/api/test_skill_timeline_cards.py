from __future__ import annotations

from src.jarvis.api.timeline import _event_title


def test_skill_invocation_event_maps_to_skill_invocation_card():
    item_type, title, summary = _event_title("skill_invocation_detected", {"skill": "summarize_file", "source": "explicit_name"})
    assert item_type == "skill_invocation"
    assert "summarize_file" in title


def test_skill_match_event_maps_to_skill_match_card():
    item_type, title, summary = _event_title("skill_description_matched", {"skill": "summarize_file", "confidence": 0.82})
    assert item_type == "skill_match"


def test_skill_use_plan_event_maps_to_skill_use_plan_card():
    item_type, title, summary = _event_title("skill_use_plan_created", {"plan": {"selected_skill": "summarize_file", "intended_path": "skill_run"}})
    assert item_type == "skill_use_plan"


def test_reference_skill_tool_call_event_maps_to_reference_card():
    item_type, title, summary = _event_title("reference_skill_guided_tool_call_started", {"skill": "multi-search-engine", "tool_calls": [{"name": "web.search"}]})
    assert item_type == "skill_reference_call"


def test_telemetry_flushed_event_maps_to_telemetry_card():
    item_type, title, summary = _event_title("telemetry_flushed", {"records": 3})
    assert item_type == "skill_telemetry"


def test_ambiguous_skill_match_maps_to_ambiguity_card():
    item_type, title, summary = _event_title("ambiguous_skill_match", {"candidates": [{"name": "a"}, {"name": "b"}]})
    assert item_type == "skill_ambiguity"


def test_skill_loaded_on_demand_maps_to_load_card():
    item_type, title, summary = _event_title("skill_loaded_on_demand", {"skill": "summarize_file", "skill_type": "executable"})
    assert item_type == "skill_load_on_demand"


def test_skill_load_blocked_maps_to_blocked_card():
    item_type, title, summary = _event_title("skill_load_blocked", {"skill": "bad_skill", "reason": "quarantined"})
    assert item_type == "skill_blocked"
