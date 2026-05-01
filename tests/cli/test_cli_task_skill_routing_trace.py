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


def test_cli_non_interactive_repo_inspection_is_not_task_trace():
    result = run_cli("-p", "Choose the best skill for inspecting this repo. Do not modify files.")
    out = result.stdout + result.stderr
    assert result.returncode == 0
    assert "Task task_" not in out
    # Now routed through AgentToolLoop
    assert "llm provider" in out.lower() or "无法连接" in out or "repository inspection" in out.lower()
