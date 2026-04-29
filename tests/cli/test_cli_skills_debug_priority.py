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


def test_cli_skills_debug_shows_priority_and_shadowing_summary():
    result = run_cli("skills", "--debug")
    out = result.stdout + result.stderr
    assert result.returncode == 0
    assert "Skill Discovery Debug" in out
    assert "Skill roots checked" in out
    assert "Duplicates shadowed" in out

