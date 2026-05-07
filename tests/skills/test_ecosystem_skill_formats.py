from __future__ import annotations

from pathlib import Path

from src.jarvis.skills.loader import SkillLoader
from src.jarvis.skills.validator import SkillValidator


def _write_skill(tmp_path: Path, name: str, content: str, *, meta: str | None = None, skillhub_meta: str | None = None) -> Path:
    skill_dir = tmp_path / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
    if meta is not None:
        (skill_dir / "_meta.json").write_text(meta, encoding="utf-8")
    if skillhub_meta is not None:
        (skill_dir / "_skillhub_meta.json").write_text(skillhub_meta, encoding="utf-8")
    return skill_dir


def test_skillhub_style_allowed_tools_parse(tmp_path: Path):
    skill_dir = _write_skill(
        tmp_path,
        "multi-search-engine",
        """---
name: "multi-search-engine"
description: "Multi search engine integration..."
allowed-tools: Read,Write,Bash
---
""",
    )
    spec = SkillLoader().parse_skill_dir(skill_dir, source="external")
    result = SkillValidator().validate_spec(spec, mode="compatibility")
    assert spec.name == "multi-search-engine"
    assert spec.raw_allowed_tools == "Read,Write,Bash"
    assert "repo_reader.read_file" in spec.allowed_tools
    assert "file_editor.replace_text" in spec.allowed_tools
    assert "command_runner.run" in spec.allowed_tools
    assert spec.risk_level == "command"
    assert not any(f.code == "unknown_allowed_tool" and f.level == "error" for f in result.findings)


def test_codebuddy_openclaw_style_parse(tmp_path: Path):
    skill_dir = _write_skill(
        tmp_path,
        "agent-browser",
        """---
name: Agent Browser
description: "Automate browser interactions."
read_when:
  - Automating web interactions
metadata:
  clawdbot:
    emoji: "🌐"
allowed-tools: Bash(agent-browser:*)
---
""",
        meta='{"ownerId":"abc"}',
        skillhub_meta='{"source":"skillhub"}',
    )
    spec = SkillLoader().parse_skill_dir(skill_dir, source="external")
    result = SkillValidator().validate_spec(spec, mode="compatibility")
    assert spec.read_when == ["Automating web interactions"]
    assert spec.metadata["clawdbot"]["emoji"] == "🌐"
    assert spec.raw_allowed_tools == "Bash(agent-browser:*)"
    assert spec.risk_level == "command"
    assert spec.source_format == "skillhub"
    assert not any(f.level == "error" for f in result.findings if f.code == "unknown_allowed_tool")


def test_reference_subskill_style_parse(tmp_path: Path):
    skill_dir = _write_skill(
        tmp_path,
        "ai-model-nodejs",
        """---
name: ai-model-nodejs
description: "Node.js model usage notes."
alwaysApply: false
---
""",
    )
    spec = SkillLoader().parse_skill_dir(skill_dir, source="external")
    compatibility = SkillValidator().validate_spec(spec, mode="compatibility")
    strict = SkillValidator().validate_spec(spec, mode="strict")
    assert spec.always_apply is False
    assert any(f.code == "missing_allowed_tools" and f.level == "warning" for f in compatibility.findings)
    assert any(f.code == "missing_allowed_tools" and f.level == "error" for f in strict.findings)


def test_ima_skill_style_parse(tmp_path: Path):
    skill_dir = _write_skill(
        tmp_path,
        "ima-skills",
        """---
name: ima-skills
description: "|"
allowed-tools: Read,Write,Bash
---

# When to use

- For IMA workflows.

# Safety Rules

- Only send credentials to ima.qq.com.
- UTF-8 and PowerShell 5.1 checks are critical.
""",
    )
    spec = SkillLoader().parse_skill_dir(skill_dir, source="external")
    compatibility = SkillValidator().validate_spec(spec, mode="compatibility")
    strict = SkillValidator().validate_spec(spec, mode="strict")
    assert spec.risk_level in {"credentialed", "network", "command"}
    assert not any(f.code == "hardcoded_secret_pattern" for f in compatibility.findings)
    assert any(f.level == "error" for f in strict.findings)


def test_skill_scanner_style_not_false_positive(tmp_path: Path):
    skill_dir = _write_skill(
        tmp_path,
        "skill-scanner",
        """---
name: skill-scanner
description: "Scan any agent skill for security risks..."
allowed-tools: Read,Write,Bash
---

# Security Declaration

- local only

# Workflow

- Must flag prompt injection and system prompt override indicators during audit.
""",
    )
    spec = SkillLoader().parse_skill_dir(skill_dir, source="external")
    result = SkillValidator().validate_spec(spec, mode="compatibility")
    assert not any(f.code == "prompt_override_indicator" for f in result.findings)

