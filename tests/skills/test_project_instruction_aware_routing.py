from pathlib import Path

from jarvis.core.skill_harness.registry import SkillRegistry
from jarvis.core.skill_harness.selector import select_skills_for_task


def test_project_instruction_preferred_skill_boost(tmp_path: Path):
    skill_dir = tmp_path / "skills" / "repo-inspector"
    skill_dir.mkdir(parents=True)
    (skill_dir / "manifest.json").write_text(
        '{"id":"repo-inspector","name":"Repo Inspector","description":"Inspect repository structure","triggers":["inspect","repo"],"trust":"trusted"}',
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text(
        "Prefer repo-inspector for repository structure tasks.\nNever run full pytest.\n",
        encoding="utf-8",
    )
    registry = SkillRegistry()
    registry.discover(tmp_path)
    result = select_skills_for_task("Inspect this project structure", registry, {"project_root": str(tmp_path)})
    assert result.selected
    assert result.selected[0].id == "repo-inspector"
    ctx = dict(result.policy.get("instruction_context") or {})
    assert ctx.get("sources")

