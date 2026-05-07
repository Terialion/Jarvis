from __future__ import annotations

from pathlib import Path

from src.jarvis.skills.loader import SkillLoader
from src.jarvis.skills.registry import SkillRegistry
from src.jarvis.skills.validator import SkillValidator


def _skill_dir(tmp_path: Path, name: str, text: str) -> Path:
    skill_dir = tmp_path / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(text, encoding="utf-8")
    return skill_dir


def test_missing_name_or_description_is_error(tmp_path: Path):
    skill_dir = _skill_dir(tmp_path, "missing", "---\nname: sample\n---\n")
    result = SkillValidator().validate_path(skill_dir, mode="compatibility")
    assert any(f.code == "missing_description" and f.level == "error" for f in result.findings)


def test_unknown_allowed_tool_warning_vs_error(tmp_path: Path):
    skill_dir = _skill_dir(
        tmp_path,
        "unknown_tool",
        """---
name: unknown_tool
description: "test"
allowed-tools: UnknownTool
---
""",
    )
    loader = SkillLoader()
    spec = loader.parse_skill_dir(skill_dir, source="external")
    compatibility = SkillValidator().validate_spec(spec, mode="compatibility")
    strict = SkillValidator().validate_spec(spec, mode="strict")
    assert any(f.code == "unknown_allowed_tool" and f.level == "warning" for f in compatibility.findings)
    assert any(f.code == "unknown_allowed_tool" and f.level == "error" for f in strict.findings)


def test_risk_tool_mismatch(tmp_path: Path):
    skill_dir = _skill_dir(
        tmp_path,
        "mismatch",
        """---
name: mismatch
description: "test"
risk_level: read_only
allowed-tools: Bash
---

# Safety Rules
- test
""",
    )
    spec = SkillLoader().parse_skill_dir(skill_dir, source="user")
    strict = SkillValidator().validate_spec(spec, mode="strict")
    assert any(f.code == "risk_tool_mismatch" and f.level == "error" for f in strict.findings)


def test_hardcoded_secret_is_detected(tmp_path: Path):
    skill_dir = _skill_dir(
        tmp_path,
        "secret_skill",
        """---
name: secret_skill
description: "test"
allowed-tools: Read
---

DEEPSEEK_API_KEY=abc
""",
    )
    result = SkillValidator().validate_path(skill_dir, mode="strict")
    assert any(f.code == "hardcoded_secret_pattern" and f.level == "error" for f in result.findings)


def test_duplicate_skill_name_is_deterministic(tmp_path: Path, monkeypatch):
    user_root = tmp_path / ".jarvis" / "skills"
    project_root = tmp_path / "skills"
    _skill_dir(user_root, "dup", "---\nname: same\ndescription: user\nallowed-tools: Read\n---\n")
    _skill_dir(project_root, "dup", "---\nname: same\ndescription: project\nallowed-tools: Read\n---\n")
    monkeypatch.delenv("JARVIS_SKILL_DIRS", raising=False)
    registry = SkillRegistry(project_root=tmp_path)
    spec = registry.get("same")
    warnings = registry.warnings()
    assert spec.description == "user"
    assert any(w.get("code") == "duplicate_skill_name" for w in warnings)


def test_path_traversal_rejected_by_registry_roots(tmp_path: Path):
    registry = SkillRegistry(project_root=tmp_path)
    outside = (tmp_path.parent / "outside-skill").resolve()
    outside.mkdir(parents=True, exist_ok=True)
    assert registry._is_within_allowed_roots(outside) is False
