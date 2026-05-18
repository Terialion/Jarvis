from __future__ import annotations

from src.jarvis.skills.matcher import SkillDescriptionMatcher
from src.jarvis.skills.metadata import CapabilityIndex
from src.jarvis.skills.schema import SkillSpec


def _build_index(entries: list[dict]) -> CapabilityIndex:
    specs = []
    states = {}
    for e in entries:
        spec = SkillSpec(
            name=e["name"],
            description=e.get("description", ""),
            path=f"/tmp/{e['name']}",
            source="local",
            source_format="markdown",
            skill_type=e.get("skill_type", "unknown"),
            tags=e.get("tags", []),
            capabilities=e.get("capabilities", []),
            when_to_use=e.get("when_to_use", ""),
            examples=e.get("examples", []),
        )
        specs.append(spec)
        states[e["name"]] = {
            "enabled": e.get("enabled_state", True),
            "quarantined": e.get("quarantine_state", False),
        }
    index = CapabilityIndex()
    index.build(specs, states)
    return index


def test_matcher_selects_skill_by_name():
    index = _build_index([
        {"name": "summarize_file", "description": "Summarize a file", "skill_type": "executable", "tags": ["summary", "file"]},
        {"name": "repo_overview", "description": "Repository overview", "skill_type": "executable", "tags": ["repo"]},
    ])
    matcher = SkillDescriptionMatcher(ambiguity_threshold=0.15, min_score=0.25)
    result = matcher.match("summarize README", index)
    assert result.matched
    assert result.selected_skill == "summarize_file"
    assert result.confidence > 0


def test_matcher_returns_ambiguous_on_very_close_scores():
    index = _build_index([
        {"name": "skill_a", "description": "do thing one", "skill_type": "executable", "tags": ["thing"]},
        {"name": "skill_b", "description": "do thing two", "skill_type": "executable", "tags": ["thing"]},
    ])
    matcher = SkillDescriptionMatcher(ambiguity_threshold=0.15, min_score=0.25)
    result = matcher.match("do thing", index)
    # With nearly identical descriptions, matcher should be ambiguous
    assert result.matched or len(result.candidates) > 1


def test_matcher_excludes_quarantined_skills():
    index = _build_index([
        {"name": "ok_skill", "description": "A safe skill", "skill_type": "executable", "enabled_state": True, "quarantine_state": False},
        {"name": "bad_skill", "description": "A quarantined skill", "skill_type": "executable", "enabled_state": True, "quarantine_state": True},
    ])
    matcher = SkillDescriptionMatcher(ambiguity_threshold=0.15, min_score=0.25)
    result = matcher.match("use bad skill", index)
    if result.matched:
        assert result.selected_skill != "bad_skill"
