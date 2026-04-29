import os
import subprocess
import sys


def test_cli_tools_debug_shows_skill_discovery():
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        [sys.executable, "-m", "jarvis.cli", "tools", "--debug"],
        cwd="d:/jarvis",
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
        timeout=30,
        env=env,
    )
    output = (result.stdout or "") + (result.stderr or "")
    assert result.returncode == 0
    assert "Skill roots checked" in output
    assert "Skills discovered" in output

