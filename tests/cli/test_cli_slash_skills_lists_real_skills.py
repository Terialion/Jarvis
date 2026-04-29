import os
import subprocess
import sys


def test_cli_slash_skills_lists_real_skills():
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        [sys.executable, "-m", "jarvis.cli"],
        cwd="d:/jarvis",
        input="/skills\n/exit\n",
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
        timeout=30,
        env=env,
    )
    output = (result.stdout or "") + (result.stderr or "")
    assert result.returncode == 0
    assert "Jarvis Skills" in output or "Skills" in output

