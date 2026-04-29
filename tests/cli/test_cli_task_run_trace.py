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


def test_external_trace_flag_shows_events():
    result = run_cli(
        "task",
        "run",
        "Choose the best skill for inspecting this repo. Do not modify files.",
        "--safe",
        "--trace",
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0
    assert "skill.registry.loaded" in output
    assert "skill.policy.checked" in output or "Policy" in output


def test_web_search_trace_policy_blocks_network():
    result = run_cli(
        "task",
        "run",
        "Choose the best skill for searching the web. Do not execute network.",
        "--safe",
        "--trace",
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0
    assert "skill.policy.checked" in output or "Policy" in output
    assert "network" in output.lower() or "dry_run" in output.lower() or "blocked" in output.lower()
    assert "Traceback" not in output
