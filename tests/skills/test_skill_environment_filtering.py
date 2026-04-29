from jarvis.core.skill_harness.loader import SkillLoader


def test_skill_filter_when_required_tool_missing():
    loader = SkillLoader(available_tools=["repo_reader"])
    res = loader.load_bundled_skills()
    assert res["ok"] is True
    assert len(res["data"]["filtered_skills"]) >= 1

