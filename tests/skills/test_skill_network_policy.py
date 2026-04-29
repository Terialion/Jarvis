from pathlib import Path

from jarvis.core.skill_harness.executor import execute_skill
from jarvis.core.skill_harness.registry import SkillRegistry


def test_network_policy_blocks_network_skill_when_disabled(tmp_path: Path):
    skill_dir = tmp_path / "skills" / "web-search"
    skill_dir.mkdir(parents=True)
    (skill_dir / "manifest.json").write_text(
        '{"id":"web-search","name":"Web Search","description":"Search web","permissions":["network.http_get"],"trust":"trusted"}',
        encoding="utf-8",
    )
    registry = SkillRegistry()
    registry.discover(tmp_path)
    result = execute_skill(
        "web-search",
        "Search web",
        registry=registry,
        dry_run=True,
        policy={"mode": "safe", "network_enabled": False},
    )
    assert result.get("status") == "blocked"
    assert result.get("reason") == "network_disabled"

