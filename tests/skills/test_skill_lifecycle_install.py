from __future__ import annotations

import json
from pathlib import Path

from src.jarvis.skills.lifecycle import SkillLifecycleManager


def _write_skill(root: Path, name: str, *, valid: bool = True) -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    if valid:
        text = (
            "---\n"
            f"name: {name}\n"
            'description: "Lifecycle test skill."\n'
            "allowed-tools: Read\n"
            "tags:\n"
            "  - test\n"
            "version: 0.1\n"
            "---\n\n"
            "# When to use\n\n- use\n\n# Do NOT use\n\n- no\n\n# Inputs\n\n- none\n\n# Workflow\n\n1. step\n\n# Decision Rules\n\n- rule\n\n# Safety Rules\n\n- safe\n\n# Output Format\n\n- short\n\n# Failure Handling\n\n- fail\n\n# Examples\n\n- example\n"
        )
    else:
        text = "---\nname: invalid\ndescription: bad\n---\n\n# Overview\nbad\n"
    (skill_dir / "SKILL.md").write_text(text, encoding="utf-8")
    return skill_dir


def test_install_local_skill_directory_and_invalid_skill_not_enabled(tmp_path: Path):
    valid_dir = _write_skill(tmp_path / "src", "my_lifecycle_skill", valid=True)
    invalid_dir = _write_skill(tmp_path / "src", "invalid_lifecycle_skill", valid=False)
    manager = SkillLifecycleManager(project_root=tmp_path, config_path=tmp_path / ".jarvis" / "skills" / "config.json")

    result = manager.install_skill(str(valid_dir), mode="compatibility", enabled=False)
    assert result["ok"] is True
    assert result["record"]["name"] == "my_lifecycle_skill"
    assert result["record"]["enabled"] is False
    assert result["record"]["validation_status"] == "ok"
    assert result["validation"]["mode"] == "compatibility"

    invalid = manager.install_skill(str(invalid_dir), mode="strict", enabled=False)
    assert invalid["ok"] is False
    assert invalid["record"]["enabled"] is False
    assert invalid["record"]["validation_status"] == "error"


def test_install_skill_md_file_and_config_is_redacted(tmp_path: Path):
    skill_dir = _write_skill(tmp_path / "src", "skill_file_install", valid=True)
    manager = SkillLifecycleManager(project_root=tmp_path, config_path=tmp_path / ".jarvis" / "skills" / "config.json")

    result = manager.install_skill(str(skill_dir / "SKILL.md"), mode="strict", enabled=False)
    assert result["ok"] is True

    payload = json.loads((tmp_path / ".jarvis" / "skills" / "config.json").read_text(encoding="utf-8"))
    assert "installed" in payload
    assert "sk-" not in json.dumps(payload, ensure_ascii=False)
