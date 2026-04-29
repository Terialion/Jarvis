import subprocess
import sys


def run_cli(*args, input_text=None, timeout=25):
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


def test_no_mock_safe_wording_for_greeting():
    result = run_cli(input_text="hello\n/exit\n")
    output = result.stdout + result.stderr
    assert result.returncode == 0
    assert "mock-safe" not in output.lower()
    assert "Handled in mock-safe mode" not in output
