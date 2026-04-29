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


def test_plan_does_not_modify_fixture():
    result = run_cli(
        input_text="/plan Fix the add bug in examples/coding_fixture. Do not modify files yet.\n/diff\n/exit\n"
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0
    assert "Plan" in output
    assert "calculator.py" in output
    assert "pytest -q" not in output
    assert "Traceback" not in output
