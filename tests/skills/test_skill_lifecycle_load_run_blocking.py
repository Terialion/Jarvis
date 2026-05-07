from __future__ import annotations

from pathlib import Path

from src.jarvis.skills.lifecycle import SkillLifecycleManager
from src.jarvis.skills.registry import SkillRegistry


def _write_skill(root: Path, name: str) -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: \"blocking test\"\nallowed-tools: Read\ntags:\n  - test\nversion: 0.1\n---\n\n# When to use\n\n- use\n\n# Do NOT use\n\n- no\n\n# Inputs\n\n- none\n\n# Workflow\n\n1. step\n\n# Decision Rules\n\n- rule\n\n# Safety Rules\n\n- safe\n\n# Output Format\n\n- short\n\n# Failure Handling\n\n- fail\n\n# Examples\n\n- example\n",
        encoding="utf-8",
    )
    return skill_dir


def test_disabled_and_quarantined_skills_block_load_and_run(tmp_path: Path):
    source_dir = _write_skill(tmp_path / "src", "blocked_skill")
    manager = SkillLifecycleManager(project_root=tmp_path, config_path=tmp_path / ".jarvis" / "skills" / "config.json")
    assert manager.install_skill(str(source_dir), mode="compatibility", enabled=False)["ok"] is True
    registry = SkillRegistry(project_root=tmp_path)

    try:
        registry.get_loadable("blocked_skill")
    except PermissionError as exc:
        assert str(exc) == "skill_disabled"
    else:
        raise AssertionError("disabled skill should block load")

    assert manager.quarantine_skill("blocked_skill", quarantined=True, reason="test")["ok"] is True
    registry = SkillRegistry(project_root=tmp_path)
    try:
        registry.get_runnable("blocked_skill")
    except PermissionError as exc:
        assert str(exc) == "skill_quarantined"
    else:
        raise AssertionError("quarantined skill should block run")
