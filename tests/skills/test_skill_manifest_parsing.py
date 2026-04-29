from pathlib import Path

from jarvis.core.skill_harness.loader import SkillLoader


def test_skill_folder_with_manifest_json_is_discovered(tmp_path: Path):
    skill_dir = tmp_path / "skills" / "web-search"
    skill_dir.mkdir(parents=True)
    (skill_dir / "manifest.json").write_text(
        '{"id":"web-search","name":"Web Search","description":"Search the web","triggers":["web","search"],"permissions":["network.read"],"trust":"trusted"}',
        encoding="utf-8",
    )
    loader = SkillLoader()
    discovered = loader.discover_skill_records(tmp_path)
    assert any(record.id == "web-search" and record.name == "Web Search" for record in discovered["records"])


def test_invalid_manifest_does_not_crash_loader(tmp_path: Path):
    skill_dir = tmp_path / "skills" / "broken"
    skill_dir.mkdir(parents=True)
    (skill_dir / "manifest.json").write_text("{invalid", encoding="utf-8")
    loader = SkillLoader()
    discovered = loader.discover_skill_records(tmp_path)
    assert len(discovered["records"]) == 1
    assert discovered["records"][0].status == "invalid"

