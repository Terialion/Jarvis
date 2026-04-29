from pathlib import Path

from jarvis.core.skill_harness.executor import execute_skill
from jarvis.core.skill_harness.registry import SkillRegistry
from jarvis.core.skill_harness.selector import select_skills_for_task


def test_imported_reference_requires_approval_in_ask_mode(tmp_path: Path):
    skill_dir = tmp_path / "openclaw" / "skills" / "openclaw-research"
    skill_dir.mkdir(parents=True)
    (skill_dir / "manifest.json").write_text(
        '{"id":"openclaw-research","name":"OpenClaw Research","description":"Search external references","triggers":["search","web"],"trust":"imported-reference","permissions":["network.http_get"]}',
        encoding="utf-8",
    )
    registry = SkillRegistry()
    registry.discover(tmp_path)

    selection = select_skills_for_task(
        "Use an imported reference skill if relevant. Ask before execution.",
        registry,
        {"mode": "ask", "safe_mode": False, "network_enabled": False, "project_root": str(tmp_path)},
    )
    assert not selection.selected or any(str(row.get("reason")) in {"approval_required_for_untrusted", "network_disabled"} for row in selection.rejected)

    outcome = execute_skill(
        "openclaw-research",
        "Use imported skill",
        registry=registry,
        dry_run=False,
        policy={"mode": "ask", "network_enabled": False, "shell_enabled": False, "file_write_enabled": False},
    )
    assert outcome.get("status") == "blocked"
    assert outcome.get("reason") in {"approval_required", "network_disabled"}

