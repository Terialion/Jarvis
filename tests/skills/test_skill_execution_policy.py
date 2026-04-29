from pathlib import Path

from jarvis.core.skill_harness.executor import execute_skill
from jarvis.core.skill_harness.registry import SkillRegistry


def test_skill_execution_policy_safe_mode_dry_run(tmp_path: Path):
    skill_dir = tmp_path / "skills" / "repo-inspector"
    skill_dir.mkdir(parents=True)
    (skill_dir / "manifest.json").write_text(
        '{"id":"repo-inspector","name":"Repo Inspector","description":"Inspect repository","trust":"trusted","permissions":[]}',
        encoding="utf-8",
    )
    registry = SkillRegistry()
    registry.discover(tmp_path)
    result = execute_skill(
        "repo-inspector",
        "Inspect this repo",
        registry=registry,
        dry_run=True,
        policy={"mode": "safe", "network_enabled": False, "shell_enabled": False, "file_write_enabled": False},
    )
    assert result.get("status") == "dry_run"
    assert result.get("policy_check", {}).get("allowed") is True

