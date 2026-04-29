from jarvis.core.skill_harness.registry import SkillRegistry


def test_generated_skill_disabled_by_default():
    registry = SkillRegistry()
    out = registry.register_skill(
        {
            "skill_id": "skill.generated.one",
            "skill_name": "Generated One",
            "source": "generated",
            "required_tools": [],
        }
    )
    assert out["ok"] is True
    entry = registry.get_skill("skill.generated.one")["data"]
    assert entry["status"] == "disabled"
    registry.enable_skill("skill.generated.one")
    assert registry.get_skill("skill.generated.one")["data"]["status"] == "enabled"

