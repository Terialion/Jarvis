from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _write_skill(root: Path, name: str) -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: \"cli lifecycle\"\nallowed-tools: Read\ntags:\n  - test\nversion: 0.1\n---\n\n# When to use\n\n- use\n\n# Do NOT use\n\n- no\n\n# Inputs\n\n- none\n\n# Workflow\n\n1. step\n\n# Decision Rules\n\n- rule\n\n# Safety Rules\n\n- safe\n\n# Output Format\n\n- short\n\n# Failure Handling\n\n- fail\n\n# Examples\n\n- example\n",
        encoding="utf-8",
    )
    return skill_dir


def _run_cli(input_text: str, *, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    merged["PYTHONIOENCODING"] = "utf-8"
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


def test_skill_lifecycle_commands_round_trip(tmp_path: Path):
    skill_dir = _write_skill(tmp_path / "skills_src", "cli_lifecycle_skill")
    source_root = tmp_path / "source_root"
    source_root.mkdir(parents=True, exist_ok=True)
    env = {
        "JARVIS_SKILL_CONFIG_PATH": str(tmp_path / ".jarvis" / "skills" / "config.json"),
        "JARVIS_SKILL_CREATE_DIR": str(tmp_path / ".jarvis" / "skills"),
        "JARVIS_SKILL_DIRS": str(source_root),
    }
    result = _run_cli(
        f"/skill install {skill_dir}\n/skill enable cli_lifecycle_skill\n/skill check cli_lifecycle_skill\n/skill disable cli_lifecycle_skill\n/skill trust cli_lifecycle_skill\n/skill quarantine cli_lifecycle_skill\n/skill source add extra {source_root}\n/skill source list\n/skill source remove extra\n/exit\n",
        env=env,
    )
    output = (result.stdout or "") + (result.stderr or "")
    assert result.returncode == 0
    assert "Skill installed: cli_lifecycle_skill" in output
    assert "Skill enabled: cli_lifecycle_skill" in output
    assert "Validation: ok" in output or "validation_status: ok" in output
    assert "Skill disabled: cli_lifecycle_skill" in output
    assert "Skill trust updated: cli_lifecycle_skill -> trusted" in output
    assert "Skill quarantined: cli_lifecycle_skill" in output
    assert "Skill source added: extra" in output
    assert "Skill source removed: extra" in output
