from pathlib import Path

from jarvis.core.skill_harness.executor import execute_skill
from jarvis.core.skill_harness.registry import SkillRegistry
from jarvis.core.skill_harness.selector import select_skills_for_task


def test_openclaw_skill_defaults_to_imported_reference_and_needs_approval(tmp_path: Path):
    skill_dir = tmp_path / "openclaw" / "skills" / "web-search"
    skill_dir.mkdir(parents=True)
    (skill_dir / "manifest.json").write_text(
        '{"id":"web-search","name":"Web Search","description":"Search the web","triggers":["web","search"],"trust":"imported-reference","permissions":[],"invocation":"auto"}',
        encoding="utf-8",
    )
    registry = SkillRegistry()
    registry.discover(tmp_path)

    selection = select_skills_for_task(
        "Search the web for references",
        registry,
        {"safe_mode": True, "network_enabled": False, "project_root": str(tmp_path)},
    )
    assert not selection.selected
    assert any(str(row.get("reason")) == "approval_required_for_untrusted" for row in selection.rejected)

    result = execute_skill(
        "web-search",
        "Search the web for references",
        registry=registry,
        dry_run=False,
        policy={"mode": "ask", "network_enabled": False},
    )
    assert result.get("status") == "blocked"
    assert result.get("reason") in {"approval_required", "network_disabled"}

