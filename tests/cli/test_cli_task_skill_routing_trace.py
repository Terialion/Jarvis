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


def test_cli_non_interactive_task_includes_skill_routing_trace():
    result = run_cli("-p", "Choose the best skill for inspecting this repo. Do not modify files.")
    out = result.stdout + result.stderr
    assert result.returncode == 0
    assert "skill.registry.loaded" in out
    assert "skill.routing.context_loaded" in out
    assert "skill.usage.recorded" in out

