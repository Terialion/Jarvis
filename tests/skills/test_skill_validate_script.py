from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_validate_skill_script_json_output():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "validate_skills.py"), "--skill", "summarize_file", "--json"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    payload = json.loads(result.stdout)
    assert payload["skill_name"] == "summarize_file"
    assert "findings" in payload


def test_validate_skill_script_compatibility_mode_for_external_path(tmp_path: Path):
    skill_dir = tmp_path / "external_skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        """---
name: "multi-search-engine"
description: "Multi search engine integration..."
allowed-tools: Read,Write,Bash
---
""",
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "validate_skills.py"),
            "--mode",
            "compatibility",
            "--path",
            str(skill_dir),
            "--json",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    payload = json.loads(result.stdout)
    assert payload["mode"] == "compatibility"
    assert payload["skill_name"] == "multi-search-engine"

