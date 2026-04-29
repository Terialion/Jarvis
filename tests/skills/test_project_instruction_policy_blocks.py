from pathlib import Path

from jarvis.core.skill_harness.registry import SkillRegistry
from jarvis.core.skill_harness.selector import select_skills_for_task


def test_project_instruction_blocks_skill_and_network(tmp_path: Path):
    web_skill = tmp_path / "skills" / "web-search"
    web_skill.mkdir(parents=True)
    (web_skill / "manifest.json").write_text(
        '{"id":"web-search","name":"Web Search","description":"Search the web","triggers":["web","search"],"permissions":["network.http_get"],"trust":"trusted"}',
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text(
        "Do not use network.\nBlock skill web-search.\n",
        encoding="utf-8",
    )
    registry = SkillRegistry()
    registry.discover(tmp_path)
    result = select_skills_for_task(
        "Search the web for references",
        registry,
        {"project_root": str(tmp_path), "network_enabled": True},
    )
    assert not result.selected
    reasons = {str(row.get("reason")) for row in result.rejected}
    assert "blocked_by_project_instruction" in reasons or "network_disabled" in reasons

