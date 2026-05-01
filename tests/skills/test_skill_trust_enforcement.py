import os
import sys


from jarvis.core.skill_harness.registry import SkillRegistry


def test_generated_skill_disabled_by_default():
    reg = SkillRegistry()
    res = reg.register_skill(
        {
            "skill_id": "gen.one",
            "skill_name": "generated",
            "source": "generated",
            "required_tools": ["repo_reader.search_files"],
            "permissions": ["read"],
        }
    )
    assert res["ok"]
    got = reg.get_skill("gen.one")
    assert got["data"]["status"] == "disabled"
    assert got["data"]["metadata"]["trust"]["quarantined"] is True
