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


def test_test_command_is_scoped_and_not_full_pytest():
    result = run_cli(input_text="/test examples/coding_fixture\n/exit\n")
    output = result.stdout + result.stderr
    assert result.returncode == 0
    assert "examples/coding_fixture" in output
    assert "shell: pytest -q" not in output
    assert "python -m pytest examples/coding_fixture -q" in output


def test_no_silent_full_regression_for_run_tests():
    result = run_cli(input_text="Run tests\n/exit\n")
    output = result.stdout + result.stderr
    assert result.returncode == 0
    assert "shell: pytest -q" not in output
    assert "python -m pytest examples/coding_fixture -q" in output
    assert "Traceback" not in output
