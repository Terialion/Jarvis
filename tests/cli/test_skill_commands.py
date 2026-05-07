from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def run_cli(input_text: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-m", "jarvis.cli"],
        cwd=str(ROOT),
        input=input_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        env=env,
    )


def test_skill_list_shows_builtin_skills():
    result = run_cli("/skill list\n/exit\n")
    output = (result.stdout or "") + (result.stderr or "")
    assert result.returncode == 0
    assert "repo_overview" in output
    assert "summarize_file" in output


def test_skill_show_displays_metadata():
    result = run_cli("/skill show summarize_file\n/exit\n")
    output = (result.stdout or "") + (result.stderr or "")
    assert result.returncode == 0
    assert "name: summarize_file" in output
    assert "risk_level: read_only" in output
    assert "repo_reader.read_file" in output

