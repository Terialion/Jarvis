import subprocess
import sys


def run_cli(*args, timeout=25):
    return subprocess.run(
        [sys.executable, "-m", "jarvis.cli", *args],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
        cwd="d:/jarvis",
    )


def test_cli_skill_insights_command_outputs_summary():
    result = run_cli("skills", "insights")
    out = result.stdout + result.stderr
    assert result.returncode == 0
    assert "Skill Insights" in out
    assert "total_records" in out

