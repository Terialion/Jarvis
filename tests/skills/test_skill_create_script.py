from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_create_skill_script_creates_template(tmp_path: Path):
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "create_skill.py"), "my_skill", "--tools", "Read", "--tags", "example"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    assert result.returncode == 0
    skill_file = tmp_path / ".jarvis" / "skills" / "my_skill" / "SKILL.md"
    assert skill_file.exists()
    text = skill_file.read_text(encoding="utf-8")
    assert "allowed-tools: Read" in text


def test_create_skill_script_does_not_overwrite(tmp_path: Path):
    skill_dir = tmp_path / ".jarvis" / "skills" / "my_skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text("existing", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "create_skill.py"), "my_skill"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    assert result.returncode == 1
    assert "Skill already exists" in (result.stdout + result.stderr)

