import os
import subprocess
import sys


def run_cli(*args, input_text=None, timeout=30):
    env = os.environ.copy()
    return subprocess.run(
        [sys.executable, "-m", "jarvis.cli", *args],
        input=input_text,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
        cwd="d:/jarvis",
        env=env,
    )


def test_task_gc_dry_run_no_delete():
    result = run_cli("task", "gc", "--dry-run")
    output = result.stdout + result.stderr
    assert result.returncode == 0
    assert "dry" in output.lower() or "gc_candidates" in output.lower() or "would" in output.lower()
    assert "Traceback" not in output


def test_slash_tasks_gc_no_crash():
    result = run_cli(input_text="/tasks gc\n/exit\n")
    output = result.stdout + result.stderr
    assert result.returncode == 0
    assert "gc" in output.lower() or "candidate" in output.lower()
    assert "Traceback" not in output
