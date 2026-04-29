from pathlib import Path

from jarvis.core.skill_harness.executor import execute_skill
from jarvis.core.skill_harness.registry import SkillRegistry


def test_denied_tool_blocks_skill_execution(tmp_path: Path):
    skill_dir = tmp_path / "skills" / "shell-helper"
    skill_dir.mkdir(parents=True)
    (skill_dir / "manifest.json").write_text(
        '{"id":"shell-helper","name":"Shell Helper","description":"Run shell commands","tools":["shell"],"permissions":[],"trust":"trusted"}',
        encoding="utf-8",
    )
    registry = SkillRegistry()
    registry.discover(tmp_path)
    result = execute_skill(
        "shell-helper",
        "Run a shell command",
        registry=registry,
        dry_run=True,
        policy={"mode": "safe", "denied_tools": ["shell"]},
    )
    assert result.get("status") == "blocked"
    assert result.get("reason") == "denied_tool"

