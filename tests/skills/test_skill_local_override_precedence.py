from jarvis.core.skill_harness.loader import SkillLoader


def test_override_skills_can_be_loaded():
    loader = SkillLoader(available_tools=["repo_reader"])
    res = loader.load_override_skills(
        [
            {
                "skill_id": "skill.local.custom",
                "skill_name": "Custom",
                "source": "override",
                "required_tools": ["repo_reader"],
            }
        ]
    )
    assert res["ok"] is True
    assert res["data"]["loaded_skills"][0]["source"] == "override"

