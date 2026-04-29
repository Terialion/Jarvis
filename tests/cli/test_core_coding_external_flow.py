import json
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


def test_external_task_run_ask_mode_returns_approval():
    result = run_cli(
        "task",
        "run",
        "Fix the add bug in examples/coding_fixture with the smallest patch. Ask before editing.",
        "--mode",
        "ask",
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0
    payload = json.loads(output)
    assert payload.get("task_id")
    assert payload.get("approval_id")
