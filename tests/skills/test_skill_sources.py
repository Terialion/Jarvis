from __future__ import annotations

from pathlib import Path

from src.jarvis.skills.lifecycle import SkillLifecycleManager
from src.jarvis.skills.registry import SkillRegistry


def _write_skill(root: Path, name: str) -> None:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: \"source test\"\nallowed-tools: Read\ntags:\n  - test\nversion: 0.1\n---\n\n# When to use\n\n- use\n\n# Do NOT use\n\n- no\n\n# Inputs\n\n- none\n\n# Workflow\n\n1. step\n\n# Decision Rules\n\n- rule\n\n# Safety Rules\n\n- safe\n\n# Output Format\n\n- short\n\n# Failure Handling\n\n- fail\n\n# Examples\n\n- example\n",
        encoding="utf-8",
    )


def test_source_add_list_remove_updates_registry(tmp_path: Path):
    source_root = tmp_path / "external_sources"
    _write_skill(source_root, "source_visible_skill")
    manager = SkillLifecycleManager(project_root=tmp_path, config_path=tmp_path / ".jarvis" / "skills" / "config.json")

    source = manager.store.add_source("ext", str(source_root))
    assert source.name == "ext"
    assert any(row.name == "ext" for row in manager.store.list_sources())

    registry = SkillRegistry(project_root=tmp_path)
    assert "source_visible_skill" in [row["name"] for row in registry.export_index(include_inactive=True)]

    assert manager.store.remove_source("ext") is True
    registry = SkillRegistry(project_root=tmp_path)
    assert "source_visible_skill" not in [row["name"] for row in registry.export_index(include_inactive=True)]
