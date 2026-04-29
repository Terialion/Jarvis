from pathlib import Path

from jarvis.core.skill_harness.executor import execute_skill
from jarvis.core.skill_harness.registry import SkillRegistry


def test_imported_reference_skill_requires_approval_for_execute(tmp_path: Path):
    skill_dir = tmp_path / "openclaw" / "skills" / "repo-inspector"
    skill_dir.mkdir(parents=True)
    (skill_dir / "manifest.json").write_text(
        '{"id":"repo-inspector","name":"Repo Inspector","description":"Inspect repository","trust":"imported-reference","permissions":[]}',
        encoding="utf-8",
    )
    registry = SkillRegistry()
    registry.discover(tmp_path)
    result = execute_skill(
        "repo-inspector",
        "Inspect this repo",
        registry=registry,
        dry_run=False,
        policy={"mode": "ask", "network_enabled": False},
    )
    assert result.get("status") == "blocked"
    assert result.get("reason") == "approval_required"
    assert result.get("requires_approval") is True

