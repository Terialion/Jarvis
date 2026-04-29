from pathlib import Path

from jarvis.core.skill_harness.registry import SkillRegistry
from jarvis.core.skill_harness.selector import select_skills_for_task


def _build_registry(tmp_path: Path) -> SkillRegistry:
    auto_skill = tmp_path / "skills" / "repo-inspector"
    auto_skill.mkdir(parents=True)
    (auto_skill / "manifest.json").write_text(
        '{"id":"repo-inspector","name":"Repo Inspector","description":"Inspect repo","triggers":["repo","inspect"],"trust":"trusted","invocation":"auto"}',
        encoding="utf-8",
    )
    manual_skill = tmp_path / "skills" / "manual-secret"
    manual_skill.mkdir(parents=True)
    (manual_skill / "manifest.json").write_text(
        '{"id":"manual-secret","name":"Manual Secret","description":"Manual skill","triggers":["secret"],"trust":"trusted","invocation":"manual"}',
        encoding="utf-8",
    )
    registry = SkillRegistry()
    registry.discover(tmp_path)
    return registry


def test_manual_skill_not_auto_selected(tmp_path: Path):
    registry = _build_registry(tmp_path)
    result = select_skills_for_task("Inspect this repo", registry, {"safe_mode": True, "project_root": str(tmp_path)})
    ids = [item.id for item in result.selected]
    assert "repo-inspector" in ids
    assert "manual-secret" not in ids


def test_manual_skill_selected_when_explicitly_invoked(tmp_path: Path):
    registry = _build_registry(tmp_path)
    result = select_skills_for_task(
        "skill: manual-secret Please run it in dry-run.",
        registry,
        {"safe_mode": True, "project_root": str(tmp_path)},
    )
    ids = [item.id for item in result.selected]
    assert "manual-secret" in ids

