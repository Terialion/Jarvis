from __future__ import annotations

from pathlib import Path

from src.jarvis.skills.loader import SkillLoader


def test_skill_loader_parses_frontmatter():
    skill_path = Path("src/jarvis/skills/builtin/summarize_file/SKILL.md")
    spec = SkillLoader().parse_skill_file(skill_path)

    assert spec.name == "summarize_file"
    assert spec.description
    assert spec.risk_level == "read_only"
    assert "repo_reader.read_file" in spec.allowed_tools

