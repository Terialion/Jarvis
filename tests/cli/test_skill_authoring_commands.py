from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _run_cli(input_text: str, *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    merged["PYTHONIOENCODING"] = "utf-8"
    if env:
        merged.update(env)
    return subprocess.run(
        [sys.executable, "-m", "jarvis.cli"],
        cwd=str(ROOT),
        input=input_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=40,
        env=merged,
    )


def test_skill_create_validate_doctor_and_index(tmp_path: Path):
    create_dir = tmp_path / "created_skills"
    env = {
        "JARVIS_SKILL_CREATE_DIR": str(create_dir),
        "JARVIS_SKILL_DIRS": str(create_dir),
    }
    result = _run_cli("/skill create my_skill\n/skill validate my_skill\n/skill doctor\n/skill index\n/exit\n", env=env)
    output = (result.stdout or "") + (result.stderr or "")
    assert result.returncode == 0
    assert "Created skill template:" in output
    assert "Skill validation: my_skill" in output
    assert "## Skill Doctor Report" in output
    assert "## Skill Index" in output
    assert "# Workflow" not in output

