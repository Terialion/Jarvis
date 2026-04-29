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


def test_cli_doctor_reports_instruction_summary():
    result = run_cli("doctor")
    out = result.stdout + result.stderr
    assert result.returncode == 0
    assert "instruction sources" in out.lower()

