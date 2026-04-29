from jarvis.core.skill_harness.matcher import SkillMatcher
from jarvis.core.skill_harness.registry import SkillRegistry


def test_quarantined_skill_is_disabled_and_not_selected():
    registry = SkillRegistry()
    registry.register_skill(
        {
            "skill_id": "skill.third.risky",
            "skill_name": "Risky",
            "source": "third_party",
            "permissions": ["shell.exec_all"],
            "required_tools": [],
        }
    )
    items = registry.list_skills()["data"]["items"]
    risky = [s for s in items if s["skill_id"] == "skill.third.risky"][0]
    assert risky["status"] == "disabled"

    matched = SkillMatcher().match_skills("run risky", {}, [], items)
    assert "skill.third.risky" not in matched["data"]["selected_skills"]

