from __future__ import annotations

from pathlib import Path

from src.jarvis.skills.lifecycle import SkillLifecycleManager
from src.jarvis.skills.registry import SkillRegistry


def _write_skill(root: Path, name: str) -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        f"name: {name}\n"
        'description: "Lifecycle toggle skill."\n'
        "allowed-tools: Read\n"
        "tags:\n"
        "  - test\n"
        "version: 0.1\n"
        "---\n\n"
        "# When to use\n\n- use\n\n# Do NOT use\n\n- no\n\n# Inputs\n\n- none\n\n# Workflow\n\n1. step\n\n# Decision Rules\n\n- rule\n\n# Safety Rules\n\n- safe\n\n# Output Format\n\n- short\n\n# Failure Handling\n\n- fail\n\n# Examples\n\n- example\n",
        encoding="utf-8",
    )
    return skill_dir


def test_disable_hides_skill_from_prompt_index_and_blocks_load_run(tmp_path: Path):
    skill_dir = _write_skill(tmp_path / "fixtures", "toggle_skill")
    manager = SkillLifecycleManager(project_root=tmp_path, config_path=tmp_path / ".jarvis" / "skills" / "config.json")
    assert manager.install_skill(str(skill_dir), mode="compatibility", enabled=False)["ok"] is True
    assert manager.set_enabled("toggle_skill", True)["ok"] is True
    assert manager.set_enabled("toggle_skill", False, reason="test")["ok"] is True

    registry = SkillRegistry(project_root=tmp_path)
    assert "toggle_skill" not in registry.available_names()

    try:
        registry.get_loadable("toggle_skill")
    except PermissionError as exc:
        assert str(exc) == "skill_disabled"
    else:
        raise AssertionError("disabled skill should not be loadable")


def test_quarantine_overrides_enable_and_trust(tmp_path: Path):
    skill_dir = _write_skill(tmp_path / "fixtures", "quarantine_skill")
    manager = SkillLifecycleManager(project_root=tmp_path, config_path=tmp_path / ".jarvis" / "skills" / "config.json")
    assert manager.install_skill(str(skill_dir), mode="compatibility", enabled=False)["ok"] is True
    assert manager.set_enabled("quarantine_skill", True)["ok"] is True
    assert manager.trust_skill("quarantine_skill", trusted=True)["ok"] is True
    assert manager.quarantine_skill("quarantine_skill", quarantined=True, reason="scanner")["ok"] is True

    registry = SkillRegistry(project_root=tmp_path)
    assert "quarantine_skill" not in registry.available_names()
    try:
        registry.get_runnable("quarantine_skill")
    except PermissionError as exc:
        assert str(exc) == "skill_quarantined"
    else:
        raise AssertionError("quarantined skill should not be runnable")
