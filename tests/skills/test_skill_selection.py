from pathlib import Path

from jarvis.core.skill_harness.registry import SkillRegistry
from jarvis.core.skill_harness.selector import select_skills_for_task


def _build_registry(tmp_path: Path) -> SkillRegistry:
    web_skill = tmp_path / "skills" / "web-search"
    web_skill.mkdir(parents=True)
    (web_skill / "manifest.json").write_text(
        '{"id":"web-search","name":"Web Search","description":"Search the web","triggers":["web","search"],"permissions":[],"trust":"trusted"}',
        encoding="utf-8",
    )
    repo_skill = tmp_path / "skills" / "repo-inspector"
    repo_skill.mkdir(parents=True)
    (repo_skill / "manifest.json").write_text(
        '{"id":"repo-inspector","name":"Repo Inspector","description":"Inspect repository structure","triggers":["repo","project structure"],"permissions":[],"trust":"trusted"}',
        encoding="utf-8",
    )
    registry = SkillRegistry()
    registry.discover(tmp_path)
    return registry


def test_web_search_prompt_selects_web_skill(tmp_path: Path):
    registry = _build_registry(tmp_path)
    result = select_skills_for_task("Search the web for Jarvis UI references", registry, {"safe_mode": True})
    assert any("web" in skill.id for skill in result.selected)


def test_repo_prompt_selects_repo_skill(tmp_path: Path):
    registry = _build_registry(tmp_path)
    result = select_skills_for_task("Inspect this repo structure", registry, {"safe_mode": True})
    assert any(("repo" in skill.id or "inspect" in skill.id) for skill in result.selected)


def test_quarantined_skill_not_selected(tmp_path: Path):
    registry = _build_registry(tmp_path)
    registry.mark_quarantined("web-search", reason="test")
    result = select_skills_for_task("Search the web", registry, {"safe_mode": True})
    assert all(skill.id != "web-search" for skill in result.selected)

