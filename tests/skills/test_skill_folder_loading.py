from jarvis.core.skill_harness.loader import SkillLoader


def test_bundled_skill_loading_contract():
    loader = SkillLoader(available_tools=["repo_reader", "file_editor", "test_runner", "command_runner"])
    res = loader.load_bundled_skills()
    assert res["ok"] is True
    assert len(res["data"]["loaded_skills"]) >= 1

