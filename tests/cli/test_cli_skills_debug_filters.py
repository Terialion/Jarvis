import subprocess
import sys


def run_cli(*args, timeout=30):
    return subprocess.run(
        [sys.executable, "-m", "jarvis.cli", *args],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
        cwd="d:/jarvis",
    )


def test_skills_debug_limit():
    result = run_cli("skills", "--debug", "--limit", "5")
    output = result.stdout + result.stderr
    assert result.returncode == 0
    assert "Skill roots checked" in output or "Skills discovered" in output
    assert "Traceback" not in output


def test_skills_debug_source_filter():
    result = run_cli("skills", "--debug", "--source", "openclaw", "--limit", "5")
    output = result.stdout + result.stderr
    assert result.returncode == 0
    assert "openclaw" in output.lower() or "No matching skills" in output
    assert "Traceback" not in output

