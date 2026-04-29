import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from jarvis.core.skill_harness.registry import SkillRegistry


def test_generated_skill_can_enable_after_explicit_approval():
    reg = SkillRegistry()
    reg.register_skill(
        {
            "skill_id": "gen.approve",
            "skill_name": "generated2",
            "source": "generated",
            "required_tools": ["repo_reader.search_files"],
            "permissions": ["read"],
        }
    )
    enabled = reg.enable_skill("gen.approve")
    assert enabled["ok"]
    assert enabled["data"]["status"] == "enabled"
