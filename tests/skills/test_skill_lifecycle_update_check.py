from __future__ import annotations

from pathlib import Path

from src.jarvis.skills.lifecycle import SkillLifecycleManager
from src.jarvis.skills.registry import SkillRegistry


def _write_skill(root: Path, name: str, *, version: str) -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: \"update test\"\nallowed-tools: Read\ntags:\n  - test\nversion: {version}\n---\n\n# When to use\n\n- use\n\n# Do NOT use\n\n- no\n\n# Inputs\n\n- none\n\n# Workflow\n\n1. step\n\n# Decision Rules\n\n- rule\n\n# Safety Rules\n\n- safe\n\n# Output Format\n\n- short\n\n# Failure Handling\n\n- fail\n\n# Examples\n\n- example\n",
        encoding="utf-8",
    )
    return skill_dir


def test_update_recomputes_hash_and_check_reports_state(tmp_path: Path):
    source_dir = _write_skill(tmp_path / "src", "update_skill", version="0.1")
    manager = SkillLifecycleManager(project_root=tmp_path, config_path=tmp_path / ".jarvis" / "skills" / "config.json")
    first = manager.install_skill(str(source_dir), mode="compatibility", enabled=False)
    first_hash = first["record"]["hash"]

    _write_skill(tmp_path / "src", "update_skill", version="0.2")
    updated = manager.update_skill("update_skill")
    assert updated["ok"] is True
    assert updated["old_hash"] == first_hash
    assert updated["new_hash"] != first_hash

    registry = SkillRegistry(project_root=tmp_path)
    checked = registry.check_skill("update_skill")
    assert checked["hash"] == updated["new_hash"]
    assert checked["validation_status"] == "ok"
    assert checked["loadable"] is False
