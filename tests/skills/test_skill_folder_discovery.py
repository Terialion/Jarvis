from pathlib import Path

from jarvis.core.skill_harness.loader import SkillLoader


def test_skill_folder_with_skill_md_is_discovered(tmp_path: Path):
    skill_dir = tmp_path / "skills" / "repo-inspector"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "# Repo Inspector\ndescription: Inspect repository structure\ntriggers: repo, structure\n",
        encoding="utf-8",
    )
    loader = SkillLoader()
    discovered = loader.discover_skill_records(tmp_path)
    ids = [record.id for record in discovered["records"]]
    assert "repo-inspector" in ids


def test_empty_folder_is_ignored(tmp_path: Path):
    (tmp_path / "skills" / "empty").mkdir(parents=True)
    loader = SkillLoader()
    discovered = loader.discover_skill_records(tmp_path)
    assert discovered["records"] == []

