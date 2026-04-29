from pathlib import Path

from jarvis.core.skill_harness.registry import SkillRegistry
from jarvis.core.skill_harness.selector import select_skills_for_task


def test_quarantined_skill_appears_but_not_selectable(tmp_path: Path):
    skill_dir = tmp_path / "skills" / "dangerous"
    skill_dir.mkdir(parents=True)
    (skill_dir / "manifest.json").write_text(
        '{"id":"dangerous","name":"Dangerous Skill","description":"dangerous","triggers":["dangerous"],"permissions":["shell.exec_all"],"trust":"trusted"}',
        encoding="utf-8",
    )
    registry = SkillRegistry()
    registry.discover(tmp_path)
    listed = registry.list_skills()["data"]["items"]
    entry = [item for item in listed if item["skill_id"] == "dangerous"][0]
    assert entry["status"] == "disabled"
    selected = select_skills_for_task("use dangerous", registry, {"safe_mode": True})
    assert all(skill.id != "dangerous" for skill in selected.selected)


def test_untrusted_skill_requires_approval_policy(tmp_path: Path):
    skill_dir = tmp_path / "skills" / "untrusted-web"
    skill_dir.mkdir(parents=True)
    (skill_dir / "manifest.json").write_text(
        '{"id":"untrusted-web","name":"Untrusted Web","triggers":["web"],"permissions":["network.read"],"trust":"untrusted"}',
        encoding="utf-8",
    )
    registry = SkillRegistry()
    registry.discover(tmp_path)
    result = select_skills_for_task(
        "search the web",
        registry,
        {"safe_mode": True, "require_approval_for_untrusted": True, "network_enabled": True},
    )
    rejected_reasons = {item["reason"] for item in result.rejected}
    assert rejected_reasons.intersection({"approval_required_for_untrusted", "quarantined"})
