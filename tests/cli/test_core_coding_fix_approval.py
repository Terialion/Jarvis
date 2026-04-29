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


def test_fix_requests_approval_before_edit():
    result = run_cli(
        input_text="/fix Fix the add bug in examples/coding_fixture. Apply the smallest patch only.\n/exit\n"
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0
    assert "Approval required" in output or "approval_" in output
    assert "calculator.py" in output
    assert "Traceback" not in output
