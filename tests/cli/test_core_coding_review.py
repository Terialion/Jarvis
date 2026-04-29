import subprocess
import sys


def run_cli(*args, input_text=None, timeout=30):
    return subprocess.run(
        [sys.executable, "-m", "jarvis.cli", *args],
        input=input_text,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
        cwd="d:/jarvis",
    )


def test_review_outputs_summary():
    result = run_cli(input_text="/review\n/exit\n")
    output = result.stdout + result.stderr
    assert result.returncode == 0
    assert "Review" in output
    assert "Risk" in output or "Changed files" in output
    assert "Traceback" not in output
