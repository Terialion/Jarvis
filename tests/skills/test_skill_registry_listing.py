from pathlib import Path

from jarvis.core.skill_harness.registry import SkillRegistry


def test_registry_list_skills_includes_discovered_records(tmp_path: Path):
    skill_dir = tmp_path / "skills" / "repo-inspector"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("name: Repo Inspector\ndescription: Inspect repo\n", encoding="utf-8")

    registry = SkillRegistry()
    registry.discover(tmp_path)
    result = registry.list_skills()
    assert result["ok"] is True
    ids = [item["skill_id"] for item in result["data"]["items"]]
    assert "repo-inspector" in ids


def test_duplicate_skill_ids_are_deduplicated(tmp_path: Path):
    for folder in ("one", "two"):
        skill_dir = tmp_path / "skills" / folder
        skill_dir.mkdir(parents=True)
        (skill_dir / "manifest.json").write_text('{"id":"dupe-skill","name":"Dupe"}', encoding="utf-8")
    registry = SkillRegistry()
    registry.discover(tmp_path)
    ids = [item["skill_id"] for item in registry.list_skills()["data"]["items"]]
    assert ids.count("dupe-skill") == 1

